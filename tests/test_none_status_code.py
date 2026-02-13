"""Test for handling None status code in HTTPException."""
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute


def test_none_status_code_no_crash():
    """Test that None status codes don't crash with ast.dump error."""
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/test")
    def test_endpoint():
        # This simulates a case where status_code_ast might be None
        # For example, when HTTPException is called without positional args
        # or with only keyword args that don't include status_code
        raise HTTPException(detail="Error without status code")

    # This should not crash during route initialization
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    # The OpenAPI schema should be generated without errors
    actual_dict = response.json()
    assert "paths" in actual_dict


def test_exception_without_args():
    """Test that exceptions without arguments don't crash."""
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/test2")
    def test_endpoint():
        # HTTPException can be raised without arguments in some edge cases
        exc = HTTPException()
        raise exc

    # This should not crash during route initialization
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
