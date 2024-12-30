from unittest import TestCase

import starlette.status
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from starlette.testclient import TestClient

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

TestCase.maxDiff = None


def test_no_side_effects():
    # Default FastAPI
    app = FastAPI(title="My Test App")

    class Item(BaseModel):
        id: int
        name: str
        description: str = None

    @app.get("/items/{item_id}", response_model=Item)
    def read_item(item_id: int):
        return {"id": item_id, "name": "Foo", "description": "A very nice item"}

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    expected_openapi_data = response.json()

    # Patch FastAPI to use AutoDeriveResponsesAPIRoute
    app_with_patch = FastAPI(title="My Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app_with_patch.get("/items/{item_id}", response_model=Item)
    def read_item(item_id: int):  # noqa: F811
        return {"id": item_id, "name": "Foo", "description": "A very nice item"}

    client = TestClient(app_with_patch)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()

    TestCase().assertDictEqual(expected_openapi_data, actual_dict)


def test_from_exception_in_source():
    app = FastAPI(title="My Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/items/{item_id}")
    def read_item(item_id: int):
        if item_id == 0:
            raise HTTPException(status_code=601, detail="First")
        if item_id == 1:
            raise HTTPException(602, detail="Second")
        if item_id == 2:
            raise HTTPException(603, "Third")
        if item_id == 3:
            raise HTTPException(604, "Fourth", headers={"X-Error": "There was an error"})
        return {"id": item_id, "name": "Foo", "description": "A very nice item"}

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/items/{item_id}"]["get"]["responses"]
    assert responses.get("601") == {"description": "First"}
    assert responses.get("602") == {"description": "Second"}
    assert responses.get("603") == {"description": "Third"}
    assert responses.get("604") == {"description": "Fourth", "headers": {"X-Error": "There was an error"}}


def test_from_dependencies():
    app = FastAPI(title="My Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    def dep() -> None:
        """
        Some description

        :raise HTTPException: 601 First
        :raises HTTPException: 602 Second
        :raises HTTPException: 603
         Third
        """
        pass

    @app.get("/items/{item_id}")
    def read_item(item_id: int, _: None = Depends(dep)):
        return {"id": item_id, "name": "Foo", "description": "A very nice item"}

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/items/{item_id}"]["get"]["responses"]
    assert responses.get("601") == {"description": "First"}
    assert responses.get("602") == {"description": "Second"}
    assert responses.get("603") == {"description": "Third"}


def test_format_strings():
    app = FastAPI(title="My Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/items/{item_id}")
    def read_item(item_id: int):
        raise HTTPException(404, f"Item with id {item_id} not found")

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/items/{item_id}"]["get"]["responses"]
    assert responses.get("404") == {"description": "Item with id {item_id} not found"}


def test_constants_status_code():
    app = FastAPI(title="My Test App")
    app.router.route_class = AutoDeriveResponsesAPIRoute

    @app.get("/items/{item_id}")
    def read_item(item_id: int):
        raise HTTPException(starlette.status.HTTP_404_NOT_FOUND, "Item not found")

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    actual_dict = response.json()
    responses = actual_dict["paths"]["/items/{item_id}"]["get"]["responses"]
    assert responses.get("404") == {"description": "Item not found"}
