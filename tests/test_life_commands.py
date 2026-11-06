from datetime import date, datetime

import pytest

from jarvis import commands
from jarvis.commands import route
from jarvis.life import life
from jarvis.life_commands import hhmm, parse_day


@pytest.fixture(autouse=True)
def private_life(tmp_path, monkeypatch):
    monkeypatch.setattr(life, "path", tmp_path / "vida.json")


def say(phrase):
    result = route(phrase)
    assert result is not None, phrase
    return result["say"]


def test_tasks_by_voice():
    assert say("agrega tarea pagar la luz para mañana es urgente") == "Tarea agregada: pagar la luz"
    say("tengo que estudiar cálculo")
    tasks = life.summary()["tasks"]
    assert tasks[0]["priority"] == "alta" and tasks[0]["due"] is not None
    assert say("¿qué tareas tengo?").startswith("Tienes 2 pendientes: pagar la luz (urgente)")
    assert say("terminé la tarea de estudiar cálculo") == "Tarea completada: estudiar cálculo"


def test_body_food_and_health_by_voice():
    assert say("mido 1.75") == "Estatura registrada: 175 cm"
    assert say("peso 70 kilos").startswith("Peso registrado: 70.0 kg")
    assert "1040 calorías" in say("almorcé un silpancho y una coca")
    assert say("tomé 2 vasos de agua") == "Llevas 2 de 8 vasos de agua hoy"
    assert say("dormí 7 horas y media").startswith("Dormiste 7.5 horas")
    assert "45 minutos" in say("hice 45 minutos de pesas")
    assert say("¿cuántas calorías llevo?").startswith("Hoy llevas 1040 de")
    assert say("me siento cansado") == "Anotado: hoy te sientes mal"


def test_money_by_voice():
    assert "25 Bs" in say("gasté 25 bolivianos en comida")
    say("ahorré 100 bolivianos")
    assert say("¿cuánto gasté este mes?") == "Este mes gastaste 25 bolivianos: comida 25. Llevas 100 ahorrados."


def test_habits_and_routine_by_voice():
    say("agrega el hábito leer")
    say("agrega a mi rutina tender la cama a las 7")
    assert life.summary()["routine"][0]["time"] == "07:00"
    assert say("hice leer").startswith("Hábito cumplido: leer")
    assert say("terminé tender la cama") == "Hecho: tender la cama. ¡Rutina completa!"


def test_classes_events_and_holidays_by_voice(monkeypatch):
    say("agrega clase de cálculo el lunes de 8 a 9 y media en el aula a12 con el ingeniero rojas")
    cls = life.summary()["classes"]["week"][0]
    assert (cls["subject"], cls["start"], cls["end"], cls["room"], cls["teacher"]) == ("Cálculo", "08:00", "09:30", "A12", "Rojas")
    assert say("¿qué clases tengo el lunes?") == "El lunes tienes: Cálculo de 08:00 a 09:30 en aula A12, con Rojas."
    assert say("tengo examen de física el 20 de diciembre a las 10").startswith("Evento agregado: Examen física")
    assert say("¿cuál es el próximo feriado?").startswith("El próximo feriado es")


def test_idea_maps_by_voice():
    assert say("crea un mapa de ideas sobre mi negocio") == "Mapa de ideas creado: mi negocio"
    say("en el mapa negocio agrega la idea ventas")
    assert say("agrega la idea vender en línea al mapa negocio conectada a ventas") == "Agregué «vender en línea» a mi negocio"
    chart = life.summary()["maps"][0]
    assert len(chart["nodes"]) == 2 and len(chart["links"]) == 1


def test_showing_a_page_of_the_life_panel(monkeypatch):
    shown = []
    monkeypatch.setattr(commands, "do", lambda tool, **args: shown.append((tool, args)))
    route("muestra mis clases")
    assert shown == [("life_show", {"page": "classes"})]


def test_spoken_dates_and_times():
    today = date(2026, 11, 5)  # jueves
    assert parse_day("mañana", today) == date(2026, 11, 6)
    assert parse_day("el lunes", today) == date(2026, 11, 9)
    assert parse_day("el 20 de noviembre", today) == date(2026, 11, 20)
    assert parse_day("el 3 de marzo", today) == date(2027, 3, 3)
    assert parse_day("el 2", today) == date(2026, 12, 2)
    assert hhmm("8 y media") == "08:30" and hhmm("2 de la tarde") == "14:00" and hhmm("14:15") == "14:15"
