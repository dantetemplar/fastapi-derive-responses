__all__ = ["AutoDeriveResponsesAPIRoute"]

import ast
import importlib
import inspect
import logging
import re
import textwrap
from collections import defaultdict
from typing import Any, Callable

from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

logger = logging.getLogger("fastapi-derive-responses")


def _inspect_function_source(function: Callable[..., Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    """
    Parse the function's source code and inspect all imported and defined classes
    to check if they are subclasses of HTTPException.
    Return a tuple: 
        - dict: {class_name: bool, ...} where `True` indicates the class is a subclass of HTTPException
        - dict: {class_name: class_object, ...} mapping class names to their actual class objects
    """
    # Get file contents and AST parsing
    path = inspect.getfile(function)
    with open(path, "r") as file:
        content = file.read()

    file_ast = ast.parse(content)

    # Inspecting imports for subclasses of HTTPException
    import_details: list[tuple[str, list[str]]] = []
    for node in ast.walk(file_ast):
        if isinstance(node, ast.ImportFrom):
            module_path = node.module
            imported_names = [alias.name for alias in node.names]
            import_details.append((module_path, imported_names))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                module_path = alias.name
                import_details.append((module_path, [alias.name]))

    inspected_subclasses = defaultdict(bool)
    exception_class_objects = {}
    for module_path, imported_names in import_details:
        try:
            # Import module and accessing inspected names
            module = importlib.import_module(module_path)
            for name in imported_names:
                imported_object = getattr(module, name)
                # Check if the imported object is a subclass of HTTPException
                if isinstance(imported_object, type) and issubclass(imported_object, HTTPException):
                    inspected_subclasses[name] = True
                    exception_class_objects[name] = imported_object
                    logger.debug(f"{name} is a subclass of HTTPException")
        except (AttributeError, ModuleNotFoundError, ImportError) as e:
            logger.debug(f"Error importing {module_path}: {str(e)}")

    # Inspect defined classes - try to get their actual class objects from function's globals
    defined_classes: list[ast.ClassDef] = [node for node in ast.walk(file_ast) if isinstance(node, ast.ClassDef)]

    for classDef in defined_classes:
        # Check inheritance
        for baseClass in classDef.bases:
            if inspected_subclasses.get(baseClass.id):
                inspected_subclasses[classDef.name] = True
                logger.debug(f"{classDef.name} is a subclass of HTTPException")
                # Try to get the actual class object from the function's global scope
                try:
                    if hasattr(function, '__globals__') and classDef.name in function.__globals__:
                        exception_class_objects[classDef.name] = function.__globals__[classDef.name]
                except Exception as e:
                    logger.debug(f"Could not get class object for {classDef.name}: {e}")
                break

    return inspected_subclasses, exception_class_objects


def _extract_status_code_from_exception_class(exception_class: type) -> tuple[int | None, str | None]:
    """
    Try to extract the status_code and description from a custom exception class.
    Looks for:
    1. A `responses` class attribute with status codes and descriptions
    2. A default `status_code` class attribute
    
    Returns a tuple (status_code, description) where either can be None.
    """
    try:
        # Check for responses attribute (e.g., responses = {404: {"description": "..."}})
        if hasattr(exception_class, 'responses') and isinstance(exception_class.responses, dict):
            for status_code, response_data in exception_class.responses.items():
                if isinstance(status_code, int):
                    description = None
                    if isinstance(response_data, dict) and "description" in response_data:
                        description = response_data["description"]
                    logger.debug(f"Found status code {status_code} with description '{description}' in {exception_class.__name__}.responses")
                    return status_code, description
        
        # Check for status_code class attribute
        if hasattr(exception_class, 'status_code'):
            status_code = exception_class.status_code
            if isinstance(status_code, int):
                logger.debug(f"Found status code {status_code} in {exception_class.__name__}.status_code")
                return status_code, None
    except Exception as e:
        logger.debug(f"Error extracting status code from {exception_class}: {e}")
    
    return None, None


def _responses_from_raise_in_source(function: Callable[..., Any]) -> dict:
    """
    Parse the endpoint's source code and extract all HTTPExceptions raised.
    Return a dict: {status_code: [{"description": str, "headers": dict}, ...], ...}
    """
    derived = defaultdict(list)

    exception_classes, exception_class_objects = _inspect_function_source(function)
    source = textwrap.dedent(inspect.getsource(function))
    as_ast = ast.parse(source)
    exceptions = [node for node in ast.walk(as_ast) if isinstance(node, ast.Raise)]

    # Get function location for better error messages
    func_file = inspect.getfile(function)
    func_name = function.__name__
    
    for exception in exceptions:
        logger.debug(f"Exception in endpoint AST: {ast.dump(exception)}")

        try:
            match exception.exc:
                case ast.Call(func=ast.Name(func_id, func_ctx), args=call_args, keywords=keywords):
                    if not exception_classes[func_id]:
                        logger.debug(f"Exception (Call) is not subclass of HTTPException: func={func_id}")
                        continue

                    status_code = detail = headers = None
                    status_code_ast = detail_ast = headers_ast = None
                    status_code_ast: ast.AST | None
                    detail_ast: ast.AST | None
                    headers_ast: ast.AST | None

                    # Handle positional arguments
                    for i, arg in enumerate(call_args):
                        if i == 0:
                            status_code_ast = arg
                        elif i == 1:
                            detail_ast = arg
                        elif i == 2:
                            headers_ast = arg
                    # Handle keyword arguments
                    for keyword in keywords:
                        if keyword.arg == "status_code":
                            status_code_ast = status_code_ast or keyword.value
                        elif keyword.arg == "detail":
                            detail_ast = detail_ast or keyword.value
                        elif keyword.arg == "headers":
                            headers_ast = headers_ast or keyword.value

                    # Extract values from AST nodes
                    statuses = importlib.import_module("starlette.status")

                    match status_code_ast:
                        case ast.Constant(value):
                            # Only accept integers as status codes
                            if isinstance(value, int):
                                status_code = value
                        # Name(id='HTTP_400_BAD_REQUEST', ctx=Load())
                        case ast.Name(id):
                            if hasattr(statuses, id):
                                status_code = getattr(statuses, id)
                        # Attribute(value=Name(id='status', ctx=Load()), attr='HTTP_400_BAD_REQUEST', ctx=Load())
                        case ast.Attribute(ast.Name("status"), attr):
                            if hasattr(statuses, attr):
                                status_code = getattr(statuses, attr)
                        # Attribute(value=Attribute(value=Name(id='starlette', ctx=Load()), attr='status', ctx=Load()),
                        #  attr='HTTP_400_BAD_REQUEST', ctx=Load())
                        case ast.Attribute(ast.Attribute(ast.Name("starlette"), "status"), attr):
                            if hasattr(statuses, attr):
                                status_code = getattr(statuses, attr)
                    
                    if isinstance(detail_ast, ast.Constant) and isinstance(detail_ast.value, str):
                        detail = detail_ast.value
                    elif hasattr(detail_ast, "s"):
                        detail = detail_ast.s
                    elif isinstance(detail_ast, ast.JoinedStr):
                        # Handle f-strings: detail=f"user_id = {id}" -> detail="user_id = {id}"
                        detail = ast.unparse(detail_ast).removeprefix("f'").removesuffix("'")


                    if isinstance(headers_ast, ast.Dict):
                        headers = {}
                        for k, v in zip(headers_ast.keys, headers_ast.values):
                            # Skip None keys or values (e.g., from dictionary unpacking)
                            if k is None or v is None:
                                continue
                            if isinstance(v, ast.Constant):
                                headers[k.value] = v.value
                            elif isinstance(v, ast.JoinedStr):
                                # Handle f-strings: headers={"X-Header": f"{value}"}
                                headers[k.value] = ast.unparse(v).removeprefix("f'").removesuffix("'")
                            elif isinstance(v, ast.Call):
                                # Handle function calls: headers={"X-Header": some_function() or str(some_function())}
                                headers[k.value] = ast.unparse(v).removeprefix("str(").removesuffix(")")
                            else:
                                logger.debug(f"Unhandled header value type: {ast.dump(v)}")
                                headers[k.value] = ast.unparse(v)

                    logger.debug(f"HTTPException: {status_code=} {detail=} {headers=}")

                    # If status_code couldn't be parsed, try to extract it from the exception class
                    if not status_code and func_id in exception_class_objects:
                        extracted_status, extracted_description = _extract_status_code_from_exception_class(exception_class_objects[func_id])
                        if extracted_status:
                            status_code = extracted_status
                            # Use extracted description if we don't have one from the raise statement
                            if not detail and extracted_description:
                                detail = extracted_description
                            logger.debug(f"Extracted status code {status_code} from exception class {func_id}")

                    if status_code:
                        derived[status_code].append({"description": detail, "headers": headers})
                    else:
                        # Build informative warning message
                        line_no = exception.lineno if hasattr(exception, 'lineno') else 'unknown'
                        warning_parts = [
                            f"[fastapi-derive-responses]",
                            f"Could not determine status code for exception in function '{func_name}'",
                            f"at {func_file}:{line_no}.",
                        ]
                        
                        if status_code_ast is not None:
                            # Only show technical details at debug level
                            logger.debug(f"Status code AST: {ast.dump(status_code_ast)}")
                            warning_parts.append(f"Exception class: {func_id}.")
                        else:
                            warning_parts.append(f"Exception class '{func_id}' raises with no explicit status_code argument.")
                        
                        warning_parts.append("This exception will not appear in OpenAPI documentation.")
                        logger.warning(" ".join(warning_parts))
                case ast.Name(id=exc_id, ctx=ctx):
                    logger.debug(f"Exception (Name): id={exc_id}, ctx={ctx}")
                case None:
                    logger.debug("Exception has no specific expression (bare `raise`).")
                case _:
                    logger.debug(f"Unhandled exception type: {exception.exc}")
        except Exception as e:
            logger.error(f"Error parsing exception: {e}", exc_info=True)
    return dict(derived)


def _from_dependencies(dependencies) -> dict:
    """
    Look at each dependency and extract all responses based on the exceptions raised in docstrings or source code.

    Returns a dict: {status_code: [{"description": str, "headers": None}, ...], ...}
    """
    derived = defaultdict(list)

    for subdependant in dependencies:
        if not subdependant.call:
            continue
        try:
            for status_code, responses in _responses_from_docstring_exceptions(subdependant.call).items():
                derived[status_code].extend(responses)
        except Exception as e:
            logger.error(f"Error parsing docstring exceptions: {e}", exc_info=True)
        try:
            for status_code, responses in _responses_from_raise_in_source(subdependant.call).items():
                derived[status_code].extend(responses)
        except Exception as e:
            logger.error(f"Error parsing source exceptions: {e}", exc_info=True)
    return dict(derived)


def _responses_from_docstring_exceptions(function) -> dict:
    """
    Parse the endpoint's docstring and extract all HTTPExceptions raised.
    Each exception should be formatted as
    >>> ":raises HTTPException: <status_code> <description>"

    Return a dict: {status_code: [{"description": str, "headers": dict}, ...], ...}
    """
    derived = defaultdict(list)

    doc = inspect.cleandoc(function.__doc__ or "")
    if not doc:
        return dict(derived)

    # Pattern: :raises HTTPException: 401 Some message
    pattern = r":raises?\s+HTTPException:\s+(\d+)\s+(.*?)(?=\n\S|$)"
    for match_obj in re.finditer(pattern, doc, re.DOTALL):
        try:
            status_code_str, detail = match_obj.groups()
            status_code = int(status_code_str)
            derived[status_code].append({"description": detail, "headers": None})
        except Exception as e:
            logger.error(f"Error parsing docstring exceptions: {e}", exc_info=True)

    return dict(derived)


def _merge_derived_exceptions(*derived_dicts) -> dict:
    """
    Merge multiple derived dictionaries into a single dictionary of responses.
    If multiple entries exist for the same status code, merge them by:
      - Joining descriptions with " OR "
      - Updating/combining headers
    """
    merged = defaultdict(list)

    # Collect all items into merged
    for derived in derived_dicts:
        for status_code, responses in derived.items():
            merged[status_code].extend(responses)

    # Collapse lists for each status code
    collapsed = {}
    for status_code, response_list in merged.items():
        if len(response_list) == 1:
            collapsed[status_code] = response_list[0]
        else:
            # Merge multiple responses for the same status_code
            all_descriptions = [r["description"] for r in response_list if r["description"]]
            combined_description = " OR ".join(set(all_descriptions)) if all_descriptions else ""

            combined_headers = {}
            for r in response_list:
                if r["headers"]:
                    combined_headers.update(r["headers"])

            collapsed[status_code] = {"description": combined_description, "headers": combined_headers or None}

    return collapsed


class AutoDeriveResponsesAPIRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Parse the endpoint source to derive potential HTTPExceptions
        try:
            derived_from_source = _responses_from_raise_in_source(self.endpoint)
        except Exception as e:
            logger.error(f"Error parsing source exceptions: {e}", exc_info=True)
            derived_from_source = {}

        # 2. Parse endpoint dependencies to derive potential HTTPExceptions
        try:
            derived_from_dependencies = _from_dependencies(self.dependant.dependencies)
        except Exception as e:
            logger.error(f"Error parsing dependencies: {e}", exc_info=True)
            derived_from_dependencies = {}
        # 3. Merge the two sources of derived exceptions
        merged_responses = _merge_derived_exceptions(derived_from_source, derived_from_dependencies)

        logger.debug(f"Merged derived responses: {merged_responses}")

        # 4. Update route responses
        for status_code, response in merged_responses.items():
            if status_code not in self.responses:
                self.responses[status_code] = response
