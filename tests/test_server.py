from fastapi.testclient import TestClient

from jarvis import server, tools

client = TestClient(server.app)
AUTH = {"Authorization": f"Bearer {server.TOKEN}"}


def test_app_files_are_public_and_installable():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"
    assert client.get("/sw.js").headers["content-type"].startswith("text/javascript")
    for icon in manifest.json()["icons"]:
        assert client.get(icon["src"]).headers["content-type"] == "image/png"


def test_every_api_route_requires_token():
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/quick/mute").status_code == 401
    assert client.post("/api/chat", json={"message": "hola"}).status_code == 401
    assert client.post("/api/transcribe", content=b"x").status_code == 401
    assert client.post("/api/speak", json={"text": "hola"}).status_code == 401
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/listener", json={"enabled": False}).status_code == 401


def test_new_page_gets_no_history_then_follows_new_events():
    server.events.publish("user", text="antiguo")
    first = client.get("/api/events", headers=AUTH).json()
    assert first["events"] == []
    server.events.publish("user", text="nuevo")
    second = client.get(f"/api/events?after={first['last']}", headers=AUTH).json()
    assert [event["text"] for event in second["events"]] == ["nuevo"]


def test_page_from_before_a_restart_resyncs():
    data = client.get("/api/events?after=999999", headers=AUTH).json()
    assert data["events"] == [] and data["last"] < 999999


def test_listener_can_be_paused(monkeypatch):
    monkeypatch.setattr(server.listener, "enabled", True)
    data = client.post("/api/listener", headers=AUTH, json={"enabled": False}).json()
    assert data["enabled"] is False
    assert client.get("/api/events", headers=AUTH).json()["listener"]["enabled"] is False
    assert client.post("/api/confirm/x", json={"approved": True}).status_code == 401


def test_quick_action_runs_only_known_actions(monkeypatch):
    pressed = []
    monkeypatch.setitem(tools.ALL_TOOLS, "media_key", lambda key: pressed.append(key) or "ok")
    assert client.post("/api/quick/mute", headers=AUTH).status_code == 200
    assert pressed == ["mute"]
    assert client.post("/api/quick/shutdown_pc", headers=AUTH).status_code == 404
    assert client.post("/api/quick/run_powershell", headers=AUTH).status_code == 404


def test_token_file_is_not_served():
    assert client.get("/static/../../data/token.txt").status_code == 404
    assert client.get("/static/%2e%2e/%2e%2e/data/token.txt").status_code == 404
