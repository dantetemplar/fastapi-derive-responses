from fastapi import FastAPI
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

def test_fake_http_exception_in_source():
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            pass

    app = FastAPI(title="Custom Exception App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/")
    def raise_custom_exception():
        raise HTTPException(status_code=601, detail="CustomException!")

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/"]["get"]["responses"]
    assert responses.get("601") is None