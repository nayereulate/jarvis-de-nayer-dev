import time

from PySide6.QtCore import QRectF

from jarvis import holoviz, server
from tests.test_features import AUTH, client


def panels_with_pending():
    actions = []
    panels = holoviz.SidePanels(lambda kind, value: actions.append((kind, value)))
    panels.add_events([{"type": "user", "text": "borra el archivo"},
                       {"type": "jarvis", "text": "¿Lo borro?", "pending": {"id": "p1", "actions": []}}])
    return panels, actions


def test_a_quick_pinch_never_approves_something_delicate(monkeypatch):
    panels, actions = panels_with_pending()
    token = ("approve", "p1")
    panels.press(token, (0, 0))
    panels.drag(token, (0, 0))
    panels.release(token)
    assert actions == [] and panels.pending()["id"] == "p1"


def test_holding_the_pinch_approves_once(monkeypatch):
    panels, actions = panels_with_pending()
    token = ("approve", "p1")
    clock = [100.0]
    monkeypatch.setattr(holoviz.time, "monotonic", lambda: clock[0])
    panels.press(token, (0, 0))
    clock[0] += holoviz.HOLD_TO_APPROVE + 0.1
    panels.drag(token, (0, 0))
    panels.drag(token, (0, 0))
    assert actions == [("confirm", ("p1", True))]
    assert panels.pending() is None


def test_deny_and_quick_buttons_act_immediately():
    panels, actions = panels_with_pending()
    panels.press(("deny", "p1"), (0, 0))
    panels.press(("quick", "mute"), (0, 0))
    assert actions == [("confirm", ("p1", False)), ("quick", "mute")]


def test_dock_only_answers_when_it_is_showing():
    pressed = []
    dock = holoviz.Dock(pressed.append, lambda: pressed.append("start"), lambda: pressed.append("desktop"))
    dock.cards = [(QRectF(100, 900, 170, 100), ("window", 42))]
    assert dock.hit((150, 950)) is None  # escondida
    for _ in range(30):
        dock.update((500, 1000), 1080, pinned=False)  # la mano baja al borde
    token = dock.hit((150, 950))
    dock.press(token)
    assert pressed == [42]
    dock.last_near = time.monotonic() - 5
    for _ in range(30):
        dock.update((500, 200), 1080, pinned=False)
    assert dock.hit((150, 950)) is None


def test_new_windows_get_the_recent_conversation():
    server.events.publish("user", text="hola holograma")
    data = client.get("/api/events?history=5", headers=AUTH).json()
    assert data["events"][-1]["text"] == "hola holograma"
    assert client.get("/api/events", headers=AUTH).json()["events"] == []


def test_approving_from_the_hologram_publishes_the_reply(monkeypatch):
    monkeypatch.setattr(server.brain, "resolve", lambda pending_id, approved: {"say": "Hecho.", "pending": None})
    monkeypatch.setattr(server.speaker, "say", lambda text, **kwargs: None)
    last = client.get("/api/events", headers=AUTH).json()["last"]
    client.post("/api/confirm/abc?announce_reply=true", json={"approved": True}, headers=AUTH)
    published = client.get(f"/api/events?after={last}", headers=AUTH).json()["events"]
    assert published[-1]["text"] == "Hecho."


def test_orders_from_the_hologram_show_up_everywhere(monkeypatch):
    monkeypatch.setattr(server.brain, "chat", lambda message: {"say": "Todo en orden.", "pending": None})
    monkeypatch.setattr(server.speaker, "say", lambda text, **kwargs: None)
    last = client.get("/api/events", headers=AUTH).json()["last"]
    client.post("/api/chat?announce_reply=true", json={"message": "Dime el estado"}, headers=AUTH)
    published = client.get(f"/api/events?after={last}", headers=AUTH).json()["events"]
    assert [(e["type"], e["text"]) for e in published] == [("user", "Dime el estado"), ("jarvis", "Todo en orden.")]


def test_side_panel_offers_every_hologram_and_system_switch():
    import os

    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])  # dibujar texto necesita una app de Qt
    panels = holoviz.SidePanels(lambda kind, value: None)
    panels.status = {"listener": {"enabled": True, "state": "wake"}, "modes": {}, "presence": {}, "recording": {}}
    image = QImage(2560, 1440, QImage.Format_ARGB32)
    painter = QPainter(image)
    panels.draw(painter, 2560, 1440, None)
    painter.end()
    tokens = [token for _, token in panels.buttons]
    for name in ("scanner", "effects", "draw", "globe", "solar", "earth", "keyboard", "notes", "visualizer", "taskbar"):
        assert ("toggle", (name, True)) in tokens, name
    assert ("presence", True) in tokens and ("dictation", True) in tokens and ("hologram_off", None) in tokens
    assert ("chat", "Apaga la PC.") in tokens and ("chat", "estado de la PC") in tokens
