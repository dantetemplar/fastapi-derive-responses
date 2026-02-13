"""Test case to reproduce the issue with messy warnings."""
from fastapi import FastAPI, status
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute


class CustomHTTPException(HTTPException):
    """Base custom exception."""
    pass


class ObjectNotFound(CustomHTTPException):
    """HTTP_404_NOT_FOUND"""

    def __init__(self, detail: str | None = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or self.responses[404]["description"],
        )

    responses = {404: {"description": "Object not found"}}


def test_custom_exception_with_init_status_code():
    """Test that custom exceptions with status_code in __init__ work correctly.
    
    This reproduces the issue where many warnings are printed without context.
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

    # This should work without too many messy warnings
    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    assert "paths" in actual_dict
    
    # The warnings should be informative and not messy
    print("OpenAPI generated successfully!")


if __name__ == "__main__":
    test_custom_exception_with_init_status_code()
