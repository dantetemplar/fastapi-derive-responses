# Summary of Changes

This PR addresses the issue described in [Issue: Warnings log looks messy](https://github.com/dantetemplar/fastapi-derive-responses/issues/XX).

## Problem Statement

Users were experiencing messy warning logs when using custom exception classes that set `status_code` in `__init__` rather than as a class attribute:

```
Invalid status code: status_code_ast is None
Invalid status code: status_code_ast is None
Invalid status code: JoinedStr(values=[Constant(value='User with id '), FormattedValue(value=Name(id='user_id', ctx=Load()), conversion=-1), Constant(value=' not found')])
...
```

Issues with the old warnings:
1. No indication they were from fastapi-derive-responses
2. No information about which endpoint or line was causing the issue
3. Technical AST dumps were not helpful for end users
4. Many repeated warnings cluttered the logs

## Solution

### 1. Support for Custom Exceptions with `responses` Attribute

The library now extracts status codes and descriptions from exception class attributes:

```python
class ObjectNotFound(CustomHTTPException):
    def __init__(self, detail: str | None = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or self.responses[404]["description"],
        )
    
    responses = {404: {"description": "Object not found"}}
```

This pattern is now fully supported, and the status code and description are automatically extracted for OpenAPI documentation.

### 2. Improved Warning Messages

When a status code cannot be determined, the warning now includes:
- Library name prefix: `[fastapi-derive-responses]`
- Function name and file location
- Line number where the exception occurs
- Helpful context about the issue
- Technical AST details moved to DEBUG level

Example of new warning:
```
[fastapi-derive-responses] Could not determine status code for exception in function 'get_user' at /path/to/file.py:42. Exception class 'CustomException' raises with no explicit status_code argument. This exception will not appear in OpenAPI documentation.
```

### 3. Bug Fix: String Constants Treated as Status Codes

Fixed a critical bug where string constants (like detail messages) were being mistaken for status codes:

**Before:**
```python
raise Unauthorized('Token required')  # 'Token required' treated as status_code!
```

**After:**
```python
raise Unauthorized('Token required')  # Correctly identified as detail, status_code extracted from class
```

This fix prevents `ValueError: invalid literal for int() with base 10: 'Token required'` errors during OpenAPI generation.

## Changes Made

### Core Changes in `fastapi_derive_responses/__init__.py`

1. **Modified `_inspect_function_source()`**:
   - Now returns a tuple: `(exception_classes_dict, exception_class_objects_dict)`
   - Collects actual class objects for status code extraction

2. **Added `_extract_status_code_from_exception_class()`**:
   - New helper function to extract status code and description from exception classes
   - Checks both `responses` attribute and `status_code` attribute
   - Returns tuple of `(status_code, description)`

3. **Enhanced `_responses_from_raise_in_source()`**:
   - Captures function location (file, name) for better error messages
   - Only treats integer constants as status codes (not strings)
   - Attempts to extract status code from exception class if not found in AST
   - Generates informative warnings with context

### New Tests

1. **`tests/test_custom_exception_with_responses.py`**:
   - Tests for custom exceptions with `responses` attribute
   - Tests for multiple custom exceptions in the same endpoint
   - Tests for dynamic detail messages

2. **`tests/test_improved_warnings.py`**:
   - Verifies that warnings are informative
   - Ensures technical details are not at WARNING level

### Demonstration

Run `demo_improvements.py` to see the improvements in action:

```bash
python demo_improvements.py
```

## Testing

All existing tests continue to pass, and 3 new test files were added:
- 14 total tests, all passing
- No security vulnerabilities detected by CodeQL

## Backward Compatibility

This change is fully backward compatible:
- Existing code continues to work without modification
- Warnings are only shown when status codes cannot be determined
- All existing test cases pass without changes

## Security Summary

No security vulnerabilities were introduced. CodeQL analysis found 0 alerts.
