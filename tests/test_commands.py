from datetime import datetime

import pytest

from jarvis import commands, tools
from jarvis.commands import parse_clock, parse_duration, route


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """Registra lo que haría cada comando, sin tocar la PC."""
    done = []

    def fake_do(tool, **args):
        done.append((tool, args))
        return {"run_routine": {"say": "Modo trabajo listo.", "results": [], "needs_approval": []},
                "system_status": {"cpu_percent": 10, "ram_percent": 40, "disk_percent": 50},
                "launch": "Abriendo", "close_app": "Cerré 1 ventana", "focus_window": "Cambié",
                "briefing": "Informe", "learn_face": "Aprendí tu cara"}.get(tool, "ok")

    monkeypatch.setattr(commands, "do", fake_do)
    monkeypatch.setattr(commands, "keys", lambda combo, say="": done.append(("keys", combo)) or {"say": say})
    monkeypatch.setattr(tools, "settings", {**tools.settings, "local_only": False})
    monkeypatch.setattr(commands.reminders, "path", tmp_path / "r.json")
    return done


def first(calls):
    return calls[0] if calls else None


@pytest.mark.parametrize("phrase, expected", [
    ("Hey Jarvis, sube el volumen.", ("media_key", {"key": "volume_up"})),
    ("bájale", ("media_key", {"key": "volume_down"})),
    ("Volumen al 30 por ciento", ("set_volume", {"level": 30.0})),
    ("pausa la música", ("media_key", {"key": "play_pause"})),
    ("siguiente canción", ("media_key", {"key": "next"})),
    ("silencio", ("media_key", {"key": "mute"})),
    ("Abre Chrome", ("launch", {"name": "Chrome"})),
    ("abre OBS", ("launch", {"name": "OBS"})),
    ("abre mis descargas", ("launch", {"name": "descargas"})),
    ("cierra Spotify", ("close_app", {"name": "Spotify"})),
    ("cambia a Chrome", ("focus_window", {"name": "Chrome"})),
    ("nueva pestaña", ("keys", "ctrl+t")),
    ("cierra la pestaña", ("keys", "ctrl+w")),
    ("pestaña 3", ("keys", "ctrl+3")),
    ("atrás", ("keys", "alt+left")),
    ("recarga la página", ("keys", "f5")),
    ("cambia de ventana", ("keys", "alt+tab")),
    ("minimiza todo", ("window_action", {"action": "minimize_all"})),
    ("maximiza", ("window_action", {"action": "maximize"})),
    ("copia", ("keys", "ctrl+c")),
    ("deshaz", ("keys", "ctrl+z")),
    ("presiona control shift t", ("keys", "ctrl+shift+t")),
    ("Escribe: Hola, ¿cómo estás?", ("type_text", {"text": "Hola, ¿cómo estás?"})),
    ("Crea una nota: comprar leche y pan", ("create_note", {"text": "comprar leche y pan"})),
    ("busca gatos graciosos en YouTube",
     ("open_url", {"url": "https://www.youtube.com/results?search_query=gatos%20graciosos"})),
    ("activa el holograma", ("hologram_on", {})),
    ("muestra el sistema solar", ("holo", {"name": "solar", "enabled": True})),
    ("oculta los paneles laterales", ("holo", {"name": "panels", "enabled": False})),
    ("activa el escáner", ("holo", {"name": "scanner", "enabled": True})),
    ("activa los subtítulos", ("subtitles_on", {})),
    ("modo dictado", ("dictation_on", {})),
    ("empieza a grabar", ("record_start", {})),
    ("deja de grabar", ("record_stop", {})),
    ("modo trabajo", ("run_routine", {"name": "trabajo"})),
    ("modo local", ("local_only", {"enabled": True})),
    ("bloquea la PC", ("lock_pc", {})),
    ("estado de la PC", ("system_status", {})),
    ("aprende mi cara, me llamo nayer", ("learn_face", {"name": "Nayer"})),
])
def test_everyday_phrases_run_locally(calls, phrase, expected):
    result = route(phrase)
    assert result is not None, phrase
    assert first(calls) == expected


def test_timer_and_reminder_phrases(calls):
    assert route("pon un temporizador de 5 minutos")["say"] == "Temporizador de 5 minutos."
    assert calls[-1] == ("set_timer", {"seconds": 300, "label": ""})
    route("temporizador de media hora para el té")
    assert calls[-1] == ("set_timer", {"seconds": 1800, "label": "el té"})
    route("Recuérdame en 20 minutos sacar la comida")
    assert calls[-1] == ("set_reminder", {"text": "sacar la comida", "minutes": 20})
    route("pon una alarma a las 7 de la mañana")
    tool, args = calls[-1]
    assert tool == "set_reminder" and args["alarm"] and args["at"].endswith("07:00")


@pytest.mark.parametrize("phrase", [
    "abre Chrome y busca recetas de pollo",          # dos órdenes: mejor Claude
    "explícame qué es un agujero negro",              # pregunta libre
    "¿qué hay en mi pantalla?",
    "recuérdame mañana a las 9 llamar al dentista",   # "mañana": Claude lo entiende mejor
    "busca las noticias de hoy",                      # con Claude, "busca" da una respuesta resumida
    "organiza mi carpeta de descargas por tipo",
])
def test_free_questions_and_complex_tasks_go_to_claude(calls, phrase):
    assert route(phrase) is None
    assert calls == []


def test_power_actions_still_need_approval(calls):
    for phrase, tool in (("apaga la PC", "shutdown_pc"), ("reinicia la computadora", "restart_pc")):
        result = route(phrase)
        assert result["confirm"] == [{"tool": tool, "args": {}}] and calls == []
    assert route("presiona suprimir")["confirm"][0]["args"] == {"keys": "delete"}


def test_local_only_mode_opens_searches_itself(calls, monkeypatch):
    monkeypatch.setitem(tools.settings, "local_only", True)
    route("busca precios de laptops")
    assert calls[-1] == ("open_url", {"url": "https://www.google.com/search?q=precios%20de%20laptops"})


def test_durations_and_clock_times():
    assert parse_duration("5 minutos") == 300
    assert parse_duration("cinco minutos") == 300
    assert parse_duration("media hora") == 1800
    assert parse_duration("una hora y media") == 5400
    assert parse_duration("1 hora y 20 minutos") == 4800
    assert parse_duration("30 segundos") == 30
    assert parse_duration("un rato") is None
    now = datetime(2026, 11, 4, 15, 0)
    assert parse_clock("7", now) == datetime(2026, 11, 4, 19, 0)  # la próxima vez que el reloj marque las 7
    assert parse_clock("7 de la manana", now) == datetime(2026, 11, 5, 7, 0)
    assert parse_clock("las 6 y media de la tarde", now) == datetime(2026, 11, 4, 18, 30)
    assert parse_clock("19:45", now) == datetime(2026, 11, 4, 19, 45)
    assert parse_clock("mañana", now) is None


def test_brain_answers_commands_without_claude(monkeypatch):
    from jarvis.brain import Brain

    monkeypatch.setattr(commands, "do", lambda tool, **args: "ok")
    monkeypatch.setattr(commands, "keys", lambda combo, say="": {"say": say})
    brain = Brain(llm=lambda prompt, session: pytest.fail("no debería llamar a Claude"))
    assert brain.chat("nueva pestaña")["local"] is True
    pending = brain.chat("apaga la PC")["pending"]
    monkeypatch.setattr(tools, "execute", lambda tool, args=None: {"ok": True, "result": "ok"})
    assert brain.resolve(pending["id"], False)["say"] == "De acuerdo, no lo hago."


def test_catalog_lists_examples_by_category():
    groups = {group["category"]: group["examples"] for group in commands.catalog()}
    assert "abre Chrome" in groups["Apps"] and "nueva pestaña" in groups["Navegador"]
    assert len(commands.COMMANDS) > 100


@pytest.mark.parametrize("phrase", ["temporizador de 10 minutos", "alarma a las 7", "una alarma a las 8 y media"])
def test_timers_and_alarms_without_a_verb(calls, phrase):
    assert route(phrase) is not None
