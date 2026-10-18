import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "X-Request-ID" in response.headers


def test_ready_reports_missing_config(client):
    response = client.get("/api/health/ready")
    body = response.json()

    assert response.status_code == 503
    assert body["checks"]["database"] == "ok"
    assert "GROQ_API_KEY" in body["checks"]["config"]


def test_full_flow_over_http(client):
    draft = client.post("/api/travel", json={"message": "Plan 3 days in Tokyo"})
    assert draft.status_code == 200
    body = draft.json()
    assert body["success"] is True
    assert body["requires_approval"] is True

    final = client.post(
        "/api/travel/approve",
        json={"thread_id": body["thread_id"], "approved": True},
    )
    assert final.status_code == 200
    assert final.json()["answer"] == "FINAL PLAN (approved)"


def test_empty_message_is_rejected(client):
    response = client.post("/api/travel", json={"message": "   "})
    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "Message cannot be empty.",
        "code": "invalid_request",
    }


def test_rejection_requires_feedback(client):
    response = client.post("/api/travel/approve", json={"thread_id": "trip_x", "approved": False})
    assert response.status_code == 400
    assert "feedback" in response.json()["error"]


def test_resume_unknown_thread_returns_404(client):
    response = client.post(
        "/api/travel/approve", json={"thread_id": "trip_missing", "approved": True}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "thread_not_found"


def test_stream_endpoint_emits_sse(client):
    response = client.post("/api/travel/stream", json={"message": "Plan 3 days in Tokyo"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(response.text)
    assert events[0][0] == "step"
    assert events[-1][0] == "result"
    draft = "".join(data["text"] for kind, data in events if kind == "token")
    assert draft == events[-1][1]["itinerary"]

    thread_id = events[-1][1]["thread_id"]
    resumed = client.post(
        "/api/travel/approve/stream",
        json={"thread_id": thread_id, "approved": False, "feedback": "Cheaper hotels"},
    )
    final = _sse_events(resumed.text)[-1]
    assert final[0] == "result"
    assert final[1]["answer"] == "FINAL PLAN (revised)"


def test_provider_rate_limit_maps_to_503(client, llm):
    class RateLimitError(Exception):
        pass

    llm.fail_with = RateLimitError("Error code: 413 - rate_limit_exceeded")
    response = client.post("/api/travel", json={"message": "Plan a trip"})

    assert response.status_code == 503
    assert response.json()["code"] == "llm_rate_limited"


def test_stream_error_becomes_error_event(client, llm):
    llm.fail_with = RuntimeError("secret internal detail")
    response = client.post("/api/travel/stream", json={"message": "Plan a trip"})
    event, data = _sse_events(response.text)[-1]

    assert event == "error"
    assert data["code"] == "internal_error"
    assert "secret" not in data["error"]


def test_rate_limit_returns_429(service):
    settings = Settings(_env_file=None, rate_limit_requests=1, environment="test")

    with TestClient(create_app(settings=settings, travel_service=service)) as client:
        assert client.post("/api/travel", json={"message": "Plan a trip"}).status_code == 200
        limited = client.post("/api/travel", json={"message": "Plan a trip"})

    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert int(limited.headers["Retry-After"]) >= 1
