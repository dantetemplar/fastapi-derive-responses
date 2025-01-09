from fastapi import FastAPI
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute
from tests.exceptions import ImportedCustomException


def test_custom_exception_in_source():
    from fastapi import HTTPException

    class CustomException(HTTPException):
        ...

    app = FastAPI(title="Custom Exception App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/")
    def raise_custom_exception():
        raise CustomException(status_code=601, detail="CustomException!")

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/"]["get"]["responses"]
    assert responses.get("601") == {"description": "CustomException!"}


def test_imported_custom_exception_in_source():
    app = FastAPI(title="Custom Exception App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/")
    def raise_custom_exception():
        raise ImportedCustomException(status_code=601, detail="CustomException!")

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/"]["get"]["responses"]
    assert responses.get("601") == {"description": "CustomException!"}
