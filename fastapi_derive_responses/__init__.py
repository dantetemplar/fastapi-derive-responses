__all__ = ["AutoDeriveResponsesAPIRoute"]

import ast
import importlib
import inspect
import logging
import re
import textwrap
from collections import defaultdict

from fastapi.routing import APIRoute

logger = logging.getLogger("fastapi-derive-responses")


def _responses_from_raise_in_source(function) -> dict:
    """
    Parse the endpoint's source code and extract all HTTPExceptions raised.
    Return a dict: {status_code: [{"description": str, "headers": dict}, ...], ...}
    """
    derived = defaultdict(list)

    source = textwrap.dedent(inspect.getsource(function))
    as_ast = ast.parse(source)
    exceptions = [node for node in ast.walk(as_ast) if isinstance(node, ast.Raise)]

    for exception in exceptions:
        logger.debug(f"Exception in endpoint AST: {ast.dump(exception)}")

        try:
            match exception.exc:
                case ast.Call(func=ast.Name(func_id, func_ctx), args=call_args, keywords=keywords):
                    if func_id != "HTTPException":
                        logger.debug(f"Exception (Call) is not HTTPException: func={func_id}")
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

                    if isinstance(detail_ast, ast.Constant):
                        detail = detail_ast.s
                    elif isinstance(detail_ast, ast.JoinedStr):
                        # Handle f-strings: detail=f"user_id = {id}" -> detail="user_id = {id}"
                        detail = ast.unparse(detail_ast).removeprefix("f'").removesuffix("'")

                    if isinstance(headers_ast, ast.Dict):
                        headers = {}
                        for k, v in zip(headers_ast.keys, headers_ast.values):
                            headers[k.value] = v.value

                    logger.debug(f"HTTPException: {status_code=} {detail=} {headers=}")

                    if status_code:
                        derived[status_code].append({"description": detail, "headers": headers})
                    else:
                        logger.warning(f"Invalid status code: {ast.dump(status_code_ast)}")
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
        for status_code, responses in _responses_from_docstring_exceptions(subdependant.call).items():
            derived[status_code].extend(responses)
        for status_code, responses in _responses_from_raise_in_source(subdependant.call).items():
            derived[status_code].extend(responses)
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
        status_code_str, detail = match_obj.groups()
        status_code = int(status_code_str)
        derived[status_code].append({"description": detail, "headers": None})

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
        derived_from_source = _responses_from_raise_in_source(self.endpoint)

        # 2. Parse endpoint dependencies to derive potential HTTPExceptions
        derived_from_dependencies = _from_dependencies(self.dependant.dependencies)

        # 3. Merge the two sources of derived exceptions
        merged_responses = _merge_derived_exceptions(derived_from_source, derived_from_dependencies)

        logger.debug(f"Merged derived responses: {merged_responses}")

        # 4. Update route responses
        for status_code, response in merged_responses.items():
            if status_code not in self.responses:
                self.responses[status_code] = response
