"""Test custom exceptions with responses attribute."""
from fastapi import FastAPI, status
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute


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


class BadRequest(CustomHTTPException):
    """Custom 400 exception."""
    
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    
    responses = {400: {"description": "Bad request"}}


class Unauthorized(CustomHTTPException):
    """Custom 401 exception."""
    
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    
    responses = {401: {"description": "Unauthorized"}}


def test_custom_exception_with_responses_attribute():
    """Test that custom exceptions with responses attribute work correctly.
    
    This tests the fix for the issue where many warnings were printed without context
    when custom exceptions had status_code set in __init__ rather than as a class attribute.
    """
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/user/{user_id}")
    def get_user(user_id: int):
        if user_id == 0:
            raise ObjectNotFound(f"User with id {user_id} not found")
        return {"id": user_id, "name": "John"}

    @app.get("/calendar/{linked_alias}")
    def get_calendar(linked_alias: str):
        if linked_alias == "invalid":
            raise ObjectNotFound(f"Linked calendar with alias {linked_alias} not found")
        return {"alias": linked_alias}

    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    assert "paths" in actual_dict
    
    # Check that 404 responses are included with proper descriptions
    user_responses = actual_dict["paths"]["/user/{user_id}"]["get"]["responses"]
    calendar_responses = actual_dict["paths"]["/calendar/{linked_alias}"]["get"]["responses"]
    
    # Verify 404 is present with correct description
    assert "404" in user_responses
    assert "404" in calendar_responses
    assert user_responses["404"]["description"] == "Object not found"
    assert calendar_responses["404"]["description"] == "Object not found"


def test_custom_exception_with_dynamic_detail():
    """Test that custom exceptions with dynamic details preserve f-string patterns."""
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/user/{user_id}")
    def get_user(user_id: int):
        if user_id == 0:
            raise UserNotFound(user_id)
        return {"id": user_id, "name": "John"}

    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    
    # Check that 404 response is included
    user_responses = actual_dict["paths"]["/user/{user_id}"]["get"]["responses"]
    assert "404" in user_responses
    # When detail is passed dynamically, we should still get the description from responses
    assert user_responses["404"]["description"] == "User not found"


def test_multiple_custom_exceptions():
    """Test multiple custom exceptions in the same endpoint."""
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/protected")
    def protected_endpoint(token: str | None = None):
        if not token:
            raise Unauthorized("Token required")
        if token != "valid":
            raise BadRequest("Invalid token format")
        return {"message": "Success"}

    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    
    # Check that both status codes are included
    endpoint_responses = actual_dict["paths"]["/protected"]["get"]["responses"]
    assert "400" in endpoint_responses
    assert "401" in endpoint_responses
    assert endpoint_responses["400"]["description"] == "Bad request"
    assert endpoint_responses["401"]["description"] == "Unauthorized"
