from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jarvis import brain, briefing, files, server, tools
from jarvis.listener import STOP_DICTATION, dictation_text
from jarvis.memory import memory
from jarvis.presence import ARRIVE_SECONDS, AWAY_SECONDS, PresenceTracker
from jarvis.reminders import Reminders, parse_when, reminders
from jarvis.routines import routines

client = TestClient(server.app)
AUTH = {"Authorization": f"Bearer {server.TOKEN}"}
NOW = datetime(2026, 11, 4, 15, 30)


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "path", tmp_path / "memory.json")
    monkeypatch.setattr(reminders, "path", tmp_path / "reminders.json")
    monkeypatch.setattr(routines, "path", tmp_path / "routines.json")
    monkeypatch.setattr(files, "SHARE_DIR", tmp_path / "share")
    from jarvis.notes import notes
    monkeypatch.setattr(notes, "path", tmp_path / "notes.json")
    monkeypatch.setattr(tools, "hologram_on", lambda: "ok")
    monkeypatch.setattr(tools, "settings", {**tools.settings})


def test_memory_remembers_and_forgets():
    memory.remember("Se llama Ana")
    memory.remember("Prefiere   el modo oscuro")
    memory.remember("Se llama Ana")
    assert memory.facts() == ["Se llama Ana", "Prefiere el modo oscuro"]
    assert "Se llama Ana" in brain.system_prompt()
    memory.forget("oscuro")
    assert memory.facts() == ["Se llama Ana"]
    with pytest.raises(ValueError):
        memory.forget("nada parecido")


def test_messages_carry_the_current_time():
    assert brain.stamp("hola", NOW) == "[miércoles 04/11/2026 15:30] hola"


def test_reminder_times():
    assert parse_when(minutes=20, now=NOW) == NOW + timedelta(minutes=20)
    assert parse_when(at="16:00", now=NOW) == datetime(2026, 11, 4, 16, 0)
    assert parse_when(at="09:00", now=NOW) == datetime(2026, 11, 5, 9, 0)  # ya pasó: mañana
    assert parse_when(at="2026-12-24T20:00", now=NOW) == datetime(2026, 12, 24, 20, 0)
    for bad in ({"minutes": -5}, {"at": "ayer"}, {"at": "2020-01-01T10:00"}, {}):
        with pytest.raises(ValueError):
            parse_when(**bad, now=NOW)


def test_reminders_fire_once_when_due(tmp_path):
    store = Reminders(tmp_path / "r.json")
    soon = store.add("sacar la comida", NOW + timedelta(minutes=5))
    later = store.add("llamar a mamá", NOW + timedelta(hours=2), alarm=True)
    assert store.pop_due(NOW) == []
    assert store.pop_due(NOW + timedelta(minutes=6)) == [soon]
    assert store.pop_due(NOW + timedelta(minutes=7)) == []
    store.cancel(later["id"])
    assert store.all() == []


def test_reminder_tool_and_list():
    outcome = tools.execute("set_reminder", {"text": "estirar", "minutes": 10})
    assert outcome["ok"] and outcome["result"]["text"] == "estirar"
    assert tools.execute("list_reminders")["result"][0]["text"] == "estirar"
    assert tools.execute("cancel_reminder", {"id": outcome["result"]["id"]})["ok"]


def test_routines_run_safe_steps_and_defer_sensitive_ones(monkeypatch):
    ran = []
    monkeypatch.setitem(tools.ALL_TOOLS, "media_key", lambda key: ran.append(key) or "ok")
    tools.execute("save_routine", {"name": "Modo prueba", "say": "Listo", "actions": [
        {"tool": "media_key", "args": {"key": "mute"}},
        {"tool": "run_powershell", "args": {"command": "Remove-Item C:\\temp\\x.txt"}},
    ]})
    result = tools.execute("run_routine", {"name": "modo prueba"})["result"]
    assert ran == ["mute"]
    assert result["say"] == "Listo"
    assert result["needs_approval"] == [{"tool": "run_powershell", "args": {"command": "Remove-Item C:\\temp\\x.txt"}}]
    assert not tools.execute("save_routine", {"name": "mala", "actions": [{"tool": "hackear", "args": {}}]})["ok"]


def test_default_routines_exist():
    assert {"trabajo", "juego", "descanso"} <= set(tools.execute("list_routines")["result"])


def test_briefing_text():
    status = {"cpu_percent": 12.4, "ram_percent": 40, "disk_percent": 97}
    items = [{"due": "2026-11-04T18:00:00", "text": "gimnasio"}, {"due": "2026-11-05T09:00:00", "text": "otro día"}]
    text = briefing.build(NOW, status, "En Cochabamba hace 20 grados.", items, name="Ana")
    assert text.startswith("Buenas tardes, Ana. Son las 15:30.")
    assert "20 grados" in text and "disco está al 97" in text
    assert "1 recordatorio: a las 18:00, gimnasio" in text and "otro día" not in text


def test_presence_greets_on_arrival_and_locks_after_leaving():
    tracker = PresenceTracker()
    assert tracker.update(1, "Ana", 100, 0.0) is None
    assert tracker.update(1, "Ana", 100, ARRIVE_SECONDS) == ("arrive", {"away": None, "name": "Ana"})
    assert tracker.update(0, None, 100, 10) is None
    # Usar el teclado cuenta como estar presente aunque no se vea la cara.
    assert tracker.update(0, None, 1, AWAY_SECONDS + 5) is None
    assert tracker.update(0, None, 100, AWAY_SECONDS * 2 + 4) is None
    assert tracker.update(0, None, 100, AWAY_SECONDS * 2 + 6) == ("leave", {})
    tracker.update(1, None, 100, 1000 + AWAY_SECONDS * 2)
    kind, info = tracker.update(1, None, 100, 1000 + AWAY_SECONDS * 2 + ARRIVE_SECONDS)
    assert kind == "arrive" and info["away"] > 1000 and info["name"] is None


def test_guard_locks_for_a_stranger_but_not_for_the_owner():
    tracker = PresenceTracker()
    events = [tracker.update(1, "", 100, i * 0.25, guard=True) for i in range(40)]  # 10 s desconocido
    assert events.count(("stranger", {})) == 1
    # El dueño visto hace poco: una cara desconocida un rato (mala luz) no bloquea.
    owner = PresenceTracker()
    owner.update(1, "Ana", 100, 0.0)
    events = [owner.update(1, "", 100, 1 + i * 0.25, guard=True) for i in range(16)]
    assert ("stranger", {}) not in events
    # Sin modo guardia, nunca.
    relaxed = PresenceTracker()
    assert all(relaxed.update(1, "", 100, i * 0.25) != ("stranger", {}) for i in range(60))
    # Una cara que no se pudo medir (lejos o de perfil) no cuenta como desconocida.
    far = PresenceTracker()
    assert all(far.update(1, None, 100, i * 0.25, guard=True) != ("stranger", {}) for i in range(60))


def test_face_book_matches_learned_people(tmp_path):
    import numpy as np
    from jarvis.faces import FaceBook

    rng = np.random.default_rng(1)
    ana, other = rng.normal(size=128), rng.normal(size=128)
    book = FaceBook(tmp_path / "faces.npz")
    book.add("Ana", [ana + rng.normal(scale=0.2, size=128) for _ in range(5)])
    assert book.match(ana)[0] == "Ana"
    assert book.match(other)[0] is None
    book.add("Ana", [ana])  # volver a aprender reemplaza
    assert book.names == ["Ana"]
    reloaded = FaceBook(tmp_path / "faces.npz")
    assert reloaded.known() == ["Ana"] and reloaded.match(ana)[0] == "Ana"
    assert reloaded.forget("ana") == 1 and reloaded.known() == []


def test_dictation_helpers():
    assert dictation_text("Hola, nueva línea. Adiós.") == "Hola\nAdiós. "
    assert STOP_DICTATION.search("Fin del dictado.")
    assert not STOP_DICTATION.search("el dictado de hoy")


def test_safe_file_names():
    assert files.safe_name("..\\..\\Windows\\win.ini") == "win.ini"
    assert files.safe_name("a<b>c?.txt") == "a_b_c_.txt"
    assert files.safe_name("CON.txt").startswith("archivo")
    assert files.safe_name("..") == "archivo"


def test_new_routes_require_token():
    for method, path in [("post", "/api/toggle/subtitles"), ("get", "/api/screen"), ("post", "/api/screen/click"), ("get", "/api/files"),
                         ("post", "/api/files?name=a.txt"), ("get", "/api/files/a.txt"), ("get", "/api/push/key"),
                         ("post", "/api/presence"), ("post", "/api/dictation"), ("post", "/api/screen/type")]:
        assert getattr(client, method)(path).status_code == 401, path


def test_upload_list_and_download_files():
    first = client.post("/api/files?name=foto.jpg", content=b"abc", headers=AUTH).json()
    second = client.post("/api/files?name=foto.jpg", content=b"defg", headers=AUTH).json()
    assert (first["name"], second["name"]) == ("foto.jpg", "foto (1).jpg")
    listed = {item["name"]: item["size"] for item in client.get("/api/files", headers=AUTH).json()["files"]}
    assert listed == {"foto.jpg": 3, "foto (1).jpg": 4}
    assert client.get("/api/files/foto.jpg", headers=AUTH).content == b"abc"
    assert client.get("/api/files/..%5Ctoken.txt", headers=AUTH).status_code == 404


def test_share_file_copies_into_the_shared_folder(tmp_path):
    source = tmp_path / "informe.pdf"
    source.write_bytes(b"pdf")
    assert tools.execute("share_file", {"path": str(source)})["ok"]
    assert [item["name"] for item in files.list_files(files.SHARE_DIR)] == ["informe.pdf"]


def test_remote_keys_cannot_press_delete():
    response = client.post("/api/screen/type", json={"keys": "shift+delete"}, headers=AUTH)
    assert response.status_code == 403


def test_dictation_needs_the_pc_listener():
    response = client.post("/api/dictation", json={"enabled": True}, headers=AUTH)
    assert response.status_code == 409


def test_toggles_change_modes_seen_by_the_windows(monkeypatch):
    monkeypatch.setattr(tools.desktop, "start", lambda **env: True)
    assert client.post("/api/toggle/subtitles", json={"enabled": True}, headers=AUTH).status_code == 200
    assert client.get("/api/events", headers=AUTH).json()["modes"]["subtitles"] is True
    client.post("/api/toggle/subtitles", json={"enabled": False}, headers=AUTH)
    assert tools.settings["subtitles"] is False
    assert client.post("/api/toggle/hackear", json={"enabled": True}, headers=AUTH).status_code == 404


def test_search_and_new_tools_are_offered_to_claude():
    for tool in ("web_search", "learn_face", "guard_on", "draw_on", "globe_on", "record_start", "subtitles_on"):
        assert tool in tools.SAFE_TOOLS
        assert tool in brain.RESPONSE_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"]


def test_holograms_that_use_the_pinch_are_exclusive():
    assert tools.execute("holo", {"name": "solar"})["ok"]
    assert tools.execute("holo", {"name": "scanner"})["ok"]
    assert tools.execute("holo", {"name": "earth"})["ok"]
    assert tools.settings["earth"] and not tools.settings["solar"] and tools.settings["scanner"]
    assert not tools.execute("holo", {"name": "volar"})["ok"]
    tools.execute("earth_city", {"city": "Madrid"})
    assert tools.settings["earth_cities"] == ["Madrid"]


def test_notes_are_created_moved_and_deleted_from_the_hologram():
    assert tools.execute("create_note", {"text": "comprar leche"})["ok"]
    note = client.get("/api/events", headers=AUTH).json()["notes"][0]
    assert note["text"] == "comprar leche"
    assert client.post(f"/api/notes/{note['id']}/move", json={"x": 0.5, "y": 2}, headers=AUTH).status_code == 200
    moved = client.get("/api/events", headers=AUTH).json()["notes"][0]
    assert (moved["x"], moved["y"]) == (0.5, 0.95)
    assert client.delete(f"/api/notes/{note['id']}", headers=AUTH).status_code == 200
    assert client.delete(f"/api/notes/{note['id']}", headers=AUTH).status_code == 404


def test_timer_shows_up_for_the_desktop_and_not_in_the_briefing():
    outcome = tools.execute("set_timer", {"minutes": 5, "label": "té"})
    assert outcome["ok"] and outcome["result"]["seconds"] == 300
    timers = client.get("/api/events", headers=AUTH).json()["timers"]
    assert [t["text"] for t in timers] == ["té"]
    assert not tools.execute("set_timer", {})["ok"]


def test_page_can_toggle_holograms():
    response = client.post("/api/toggle/visualizer", json={"enabled": True}, headers=AUTH)
    assert response.status_code == 200 and tools.settings["visualizer"]


def test_hiding_the_side_panels_is_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "HOLO_CHOICES", tmp_path / "hologramas.json")
    tools.settings["taskbar"] = True  # sin depender de lo que tenga elegido el usuario
    tools.execute("holo", {"name": "panels", "enabled": False})
    tools.settings["panels"] = True
    tools._load_choices()
    assert tools.settings["panels"] is False
    tools.execute("hologram_off")
    assert tools.settings["panels"] is False and tools.settings["taskbar"] is True
