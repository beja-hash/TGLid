from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_application_status() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
    assert response.headers["x-request-id"]


def test_readiness_reports_available_dependencies(monkeypatch) -> None:
    async def ready() -> dict[str, str]:
        return {"postgres": "ok", "redis": "ok"}

    with TestClient(app) as client:
        monkeypatch.setattr(client.app.state.health_service, "readiness", ready)
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"postgres": {"status": "ok"}, "redis": {"status": "ok"}},
    }


def test_readiness_hides_dependency_details_when_unavailable(monkeypatch) -> None:
    async def unavailable() -> dict[str, str]:
        return {"postgres": "unavailable", "redis": "ok"}

    with TestClient(app) as client:
        monkeypatch.setattr(client.app.state.health_service, "readiness", unavailable)
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"postgres": {"status": "unavailable"}, "redis": {"status": "ok"}},
    }
    assert "postgresql" not in response.text.lower()
