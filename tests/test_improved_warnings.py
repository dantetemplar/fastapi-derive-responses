"""Test improved warning messages."""
import logging
import io
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute


def test_informative_warning_for_unparseable_status_code():
    """Test that unparseable status codes produce informative warnings."""
    # Capture log output
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("fastapi-derive-responses")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    
    app = FastAPI(title="Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/test")
    def test_endpoint():
        # Use a computed value that AST can't evaluate
        some_condition = True
        status = 400 if some_condition else 500
        raise HTTPException(status_code=status, detail="Error")

    client = TestClient(app)
    
    # Verify OpenAPI generation works
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    # Check warning message content
    log_content = log_stream.getvalue()
    logger.removeHandler(handler)
    
    # The warning should be informative
    assert "[fastapi-derive-responses]" in log_content
    assert "test_endpoint" in log_content or "Could not determine status code" in log_content
    # Should NOT contain technical AST dumps at warning level
    assert "status_code_ast is None" not in log_content


if __name__ == "__main__":
    test_informative_warning_for_unparseable_status_code()
    print("✅ Warning message test passed!")
