"""Test for handling None status code in HTTPException."""
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute


def test_invalid_status_code_expression():
    """Test that invalid status code expressions don't crash with ast.dump error.
    
    This test ensures that when the AST parser encounters a status_code_ast that
    evaluates to None (e.g., complex expressions that can't be resolved), it doesn't
    crash but instead logs a warning.
    """
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    # Use a variable for status code which the AST parser can't resolve at parse time
    @app.get("/test")
    def test_endpoint():
        # This uses a computed value that AST can't evaluate
        some_condition = True
        status = 400 if some_condition else 500
        raise HTTPException(status_code=status, detail="Error")

    # This should not crash during route initialization
    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    assert "paths" in actual_dict


def test_dict_unpacking_in_headers():
    """Test that dictionary unpacking in headers doesn't crash.
    
    This test ensures that when the AST parser encounters dictionary unpacking
    operations like {**dict}, where keys and values can be None, it doesn't
    crash but handles them gracefully.
    """
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/test2")
    def test_endpoint():
        # Dictionary unpacking creates None keys/values in the AST
        extra_headers = {"X-Custom": "value"}
        raise HTTPException(
            status_code=400,
            detail="Error",
            headers={**extra_headers, "X-Another": "another"}
        )

    # This should not crash during route initialization
    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200


