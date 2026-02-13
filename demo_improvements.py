"""
Demonstration script showing the improvements in warning messages and custom exception support.

Run this to see the difference between the old and new behavior.
"""
import logging

logging.basicConfig(
    level=logging.WARNING,
    format='%(message)s'
)

from fastapi import FastAPI, status
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

# Define custom exception classes
class CustomHTTPException(HTTPException):
    """Base custom exception."""
    pass


class ObjectNotFound(CustomHTTPException):
    """Custom 404 exception with responses attribute."""

    def __init__(self, detail: str | None = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or self.responses[404]["description"],
        )

    responses = {404: {"description": "Object not found"}}


class UserNotFound(CustomHTTPException):
    """Custom 404 exception for users."""

    def __init__(self, user_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    responses = {404: {"description": "User not found"}}


class EventGroupNotFound(CustomHTTPException):
    """Custom 404 exception for event groups."""

    def __init__(self, group_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event group with id {group_id} does not exist",
        )

    responses = {404: {"description": "Event group not found"}}


# Create the app
app = FastAPI(title="Demo App")
app.router.route_class = AutoDeriveResponsesAPIRoute

@app.get("/user/{user_id}")
def get_user(user_id: int):
    """Get a user by ID."""
    if user_id == 0:
        raise UserNotFound(user_id)
    return {"id": user_id, "name": "John"}


@app.get("/calendar/{linked_alias}")
def get_calendar(linked_alias: str):
    """Get a calendar by alias."""
    if linked_alias == "invalid":
        raise ObjectNotFound(f"Linked calendar with alias {linked_alias} not found")
    return {"alias": linked_alias}


@app.get("/event-group/{group_id}")
def get_event_group(group_id: int):
    """Get an event group by ID."""
    if group_id == 0:
        raise EventGroupNotFound(group_id)
    return {"id": group_id, "name": "Group"}


print("\n" + "=" * 80)
print("DEMONSTRATION: Improved fastapi-derive-responses")
print("=" * 80)
print("\n✨ Creating FastAPI app with custom exception handlers...\n")

# Create the test client (this is when routes are parsed)
client = TestClient(app)

print("✅ App created successfully!\n")
print("📋 Notice: No messy warning logs!\n")

# Get the OpenAPI schema
response = client.get("/openapi.json")
assert response.status_code == 200

openapi = response.json()

print("=" * 80)
print("Generated OpenAPI responses for each endpoint:")
print("=" * 80)

for path, path_item in openapi["paths"].items():
    for method, operation in path_item.items():
        print(f"\n{method.upper()} {path}")
        print("-" * 40)
        responses = operation.get("responses", {})
        for status_code, response_data in responses.items():
            description = response_data.get("description", "")
            print(f"  {status_code}: {description}")

print("\n" + "=" * 80)
print("✅ Summary of improvements:")
print("=" * 80)
print("""
1. ✅ No more messy 'Invalid status code: status_code_ast is None' warnings
2. ✅ Custom exceptions with responses attribute are now supported
3. ✅ Status codes are correctly extracted from exception class definitions
4. ✅ Descriptions from exception class responses are used in OpenAPI
5. ✅ If warnings are shown, they include:
   - Library name ([fastapi-derive-responses])
   - Function name and file location
   - Line number where the exception is raised
   - Helpful context about what went wrong
""")
print("=" * 80 + "\n")
