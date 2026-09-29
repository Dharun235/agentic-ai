from fastapi.testclient import TestClient

from web_app import app


def test_ui_and_observability_routes_are_available():
    client = TestClient(app)

    page = client.get("/")
    status = client.get("/observability")

    assert page.status_code == 200
    assert "ROS2 Agent" in page.text
    assert status.status_code == 200
    assert "project" in status.json()


def test_unknown_run_returns_not_found():
    response = TestClient(app).get("/runs/does-not-exist")

    assert response.status_code == 404
