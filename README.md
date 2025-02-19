# FastAPI Derive Responses Plugin

`fastapi-derive-responses` is a Python library that extends FastAPI by automatically generating OpenAPI responses based
on your endpoint's source code.
This plugin helps you reduce boilerplate code by deriving response statuses and descriptions directly from your code.

With `fastapi-derive-responses` you can omit ~4 lines on endpoint definition:

```diff
@app.get(
    "/add_user",
    responses={
         200: {"description": "User added successfully"},
-        400: {"description": "User already exists"},
-        401: {"description": "Invalid token"},
-        403: {"description": "Only admins and moderators can add users or You are banned"},
-        404: {"description": "Invalid role or User not found"},
    },
)
def add_user(
    current_user_id: Annotated[int, Depends(auth_user)],
    new_user_id: int,
    user_role: str
):
    if statuses[current_user_id] not in ("admin", "moderator"):
        raise HTTPException(403, "Only admins and moderators can add users")
    if new_user_id in statuses:
        raise HTTPException(400, "User already exists")
    if user_role not in ROLES:
        raise HTTPException(400, "Invalid role")
    statuses[new_user_id] = user_role
    return {"message": "User added successfully"}
```

## TODO

- [x] `raise HTTPException(401, detail="Invalid token")` in endpoint source -> `{401: {description: "Invalid token"}}`
- [x] `raise HTTPException(404, detail=f"User with id={id} not found")` in endpoint source -> `{404: {description: "User
  with id={id} not found"}}`
- [x] `raise HTTPException(404, headers={"X-Error": "User not found"})` in endpoint source -> `{404: {headers: {"X-Error": "User not found"}}}`
- [x] Multiple derived responses for the same endpoint merged into one -> `{401: {description: "Invalid token OR Token is
  expired"}}`
- [x] Don't override manually defined responses in decorators
- [x] ^ Same behavior for dependency functions ^
- [x] `:raises HTTPException: 401 Invalid token` in dependency function docstring parses -> `{401: {description: "Invalid
  token"}}`
- [x] Avoid false positives (e.g., `raise HTTPException(401)` where `HTTPException` is not from `starlette` or
  `fastapi`)
- [x] Parse custom classes that inherit from `HTTPException`
- [ ] Check for custom response models
- [ ] Allow to omit some responses from parsing
- [ ] Code analysis for complex structures in detail and headers

## Known Issues

Plugin works through AST parsing, so it may not work correctly with complex code structures or runtime generated code.
Also, it may produce false positives: for example, if you raise an exception with name `HTTPException` yet not from `starlette` or `fastapi` and you have imported `starlette.HTTPException` in the same module but in some isolated scope then your exception will be considered as `starlette.HTTPException`. 

## Installation

```bash
pip install fastapi-derive-responses
```

## Quick Start

### Basic Usage

You can just raise subclasses of `starlette.HTTPException` in endpoint.

It will propagate `{404: {"description": "Item not found"}, 400:  {"description": "Invalid item id"}}` to OpenAPI schema.

```python
from fastapi import FastAPI, HTTPException
from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

app = FastAPI()
app.router.route_class = AutoDeriveResponsesAPIRoute

class CustomExeption(HTTPException):
    ...

@app.get("/items/{item_id}")
def read_item(item_id: int):
    if item_id == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    if item_id == -1:
        raise CustomExeption(status_code=400, detail="Invalid item id")
    return {"id": item_id, "name": "Item Name"}
```

### Example with Dependencies

It will propagate `{401: {"description": "Invalid token"}}`, `{403: {"description": "You are banned"}}` and `{404: {
"description": "User not found"}}` to OpenAPI schema.

```python
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

app = FastAPI()
app.router.route_class = AutoDeriveResponsesAPIRoute


def auth_user(token: int) -> int:
    """
    Authenticate user

    :raises HTTPException: 401 Invalid token
    :raises HTTPException: 403 You are banned
    :raises HTTPException: 404 User not found
    """
    call_some_func_that_may_raise()
    return token


@app.get("/users/me")
def get_current_user(user_id: Annotated[int, Depends(auth_user)]):
    return {"id": user_id, "role": "admin"}
```

Also, you can just raise subclasses of `starlette.HTTPException` in your dependency function:

```python
class CustomException(HTTPException):
    ...

def auth_user(token: int) -> int:
    if token < 100:
        raise HTTPException(401, "Invalid token")
    user_id = token - 100
    if user_id not in statuses:
        raise CustomException(404, "User not found")
    if user_id in banlist:
        raise HTTPException(403, "You are banned")
    return user_id
```


Also, it works then you import your custom exception from other modules:

```python
# exceptions.py
from starlette.exceptions import HTTPException

class ImportedCustomException(HTTPException):
    ...
```
```python
# main.py
from exceptions import ImportedCustomException
...

app = FastAPI(title="Custom Exception App")
app.router.route_class = AutoDeriveResponsesAPIRoute

@app.get("/")
def raise_custom_exception():
    raise ImportedCustomException(status_code=601, detail="CustomException!")

```
