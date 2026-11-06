from datetime import date, datetime

import pytest

from jarvis import holidays
from jarvis.foods import parse_meal
from jarvis.life import Life, LifeError


@pytest.fixture
def life(tmp_path):
    return Life(tmp_path / "vida.json")


def test_bolivian_holidays_move_with_easter():
    names = {h["date"]: h["name"] for h in holidays.holidays(2026)}
    assert names["2026-02-16"] == "Carnaval (lunes)" and names["2026-02-17"] == "Carnaval (martes)"
    assert names["2026-04-03"] == "Viernes Santo" and names["2026-06-04"] == "Corpus Christi"
    assert names["2026-09-14"] == "Aniversario de Cochabamba" and names["2026-08-06"] == "Día de la Independencia"
    upcoming = holidays.upcoming(date(2026, 11, 5), 3)
    assert [h["name"] for h in upcoming] == ["Navidad", "Año Nuevo", "Día del Estado Plurinacional"]


def test_meals_are_counted_with_the_local_table():
    items = parse_meal("dos salteñas, un café con leche y un tamal")
    assert [(i["name"], i["qty"]) for i in items] == [("saltena", 2), ("cafe con leche", 1), ("tamal", 1.0)]
    assert items[0]["kcal"] == 700 and items[2]["kcal"] is None


def test_tasks_can_be_found_by_part_of_their_text(life):
    life.apply("task_add", {"text": "Pagar la luz", "priority": "alta"})
    life.apply("task_add", {"text": "Estudiar cálculo"})
    result = life.apply("task_done", {"task": "luz"})
    assert result["say"] == "Tarea completada: Pagar la luz"
    assert [t["text"] for t in result["summary"]["tasks"]] == ["Estudiar cálculo"]
    with pytest.raises(LifeError):
        life.apply("task_done", {"task": "algo que no existe"})


def test_body_goals_for_gaining_muscle(life):
    life.apply("height", {"cm": 1.75})
    life.apply("weight", {"kg": 70})
    summary = life.apply("weight", {"kg": 71})["summary"]
    assert summary["body"]["height_cm"] == 175 and summary["body"]["bmi"] == 23.2
    assert summary["food"]["goals"] == {"kcal": 2640, "protein": 128, "estimated": False}
    assert "+1.0 kg" in life.apply("weight", {"kg": 72})["say"]


def test_daily_counters(life):
    life.apply("meal", {"text": "un silpancho y una coca", "meal": "almuerzo"})
    life.apply("water", {"glasses": 3})
    life.apply("sleep", {"hours": 7.5})
    life.apply("exercise", {"kind": "pesas", "minutes": 45})
    life.apply("money", {"amount": 25, "category": "comida"})
    life.apply("money", {"amount": 100, "kind": "ahorro"})
    summary = life.apply("mood", {"score": 4})["summary"]
    assert summary["food"]["kcal"] == 1040 and summary["water"]["today"] == 3
    assert summary["sleep"]["last"] == 7.5 and summary["exercise"]["streak"] == 1
    assert summary["money"]["spent"] == 25 and summary["money"]["saved"] == 100
    assert summary["mood"]["today"]["score"] == 4


def test_habits_and_routine_are_checked_per_day(life):
    life.apply("habit_add", {"name": "Leer"})
    life.apply("routine_add", {"text": "Tender la cama", "time": "07:00"})
    life.apply("routine_add", {"text": "Desayunar", "time": "07:30"})
    life.apply("habit_check", {"habit": "leer"})
    result = life.apply("routine_check", {"item": "cama"})
    assert result["say"] == "Hecho: Tender la cama. Te quedan 1 de tu rutina"
    summary = result["summary"]
    assert summary["habits"][0]["done"] and summary["habits"][0]["streak"] == 1
    assert [r["done"] for r in summary["routine"]] == [True, False]


def test_class_schedule_knows_the_current_and_next_class(life):
    life.apply("class_add", {"day": "miércoles", "start": "08:00", "end": "09:30", "subject": "Cálculo",
                             "room": "A-12", "place": "Campus central", "teacher": "Ing. Rojas"})
    life.apply("class_add", {"day": 2, "start": "10:00", "end": "11:30", "subject": "Física"})
    summary = life.summary(now=datetime(2026, 11, 4, 8, 30))  # miércoles
    assert summary["classes"]["now"]["subject"] == "Cálculo" and summary["classes"]["now"]["teacher"] == "Ing. Rojas"
    assert summary["classes"]["next"]["subject"] == "Física"


def test_idea_maps_and_flowcharts(life):
    life.apply("map_add", {"name": "Proyecto Jarvis", "kind": "flujo"})
    life.apply("node_add", {"map_": "proyecto", "text": "Inicio", "shape": "oval"})
    life.apply("node_add", {"map_": "proyecto", "text": "¿Funciona?", "parent": "inicio", "shape": "diamond"})
    life.apply("node_add", {"map_": "proyecto", "text": "Publicar", "parent": "funciona", "label": "sí"})
    life.apply("node_move", {"map_": "proyecto", "node": "publicar", "x": 1.5, "y": 0.4})
    summary = life.apply("link_add", {"map_": "proyecto", "source": "publicar", "target": "inicio"})["summary"]
    chart = summary["maps"][0]
    assert [n["text"] for n in chart["nodes"]] == ["Inicio", "¿Funciona?", "Publicar"]
    assert len(chart["links"]) == 3 and chart["links"][1]["label"] == "sí"
    assert chart["nodes"][2]["x"] == 0.98  # no se sale del lienzo
    life.apply("node_delete", {"map_": "proyecto", "node": "funciona"})
    assert len(life.summary()["maps"][0]["links"]) == 1


def test_unknown_actions_are_rejected(life):
    with pytest.raises(LifeError):
        life.apply("hackear", {})
