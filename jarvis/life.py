"""Mi vida: tareas, cuerpo, comidas, agua, sueño, ejercicio, dinero, ánimo, hábitos, rutina,
calendario, horario de clases y mapas de ideas o diagramas de flujo.

Todo se guarda en data/vida.json, solo en esta PC. apply(acción, datos) es la única puerta de entrada:
la usan la voz, la página, el holograma y Claude.
"""
import json
import threading
import uuid
from datetime import date, datetime, timedelta

from . import holidays
from .foods import parse_meal
from .paths import DATA_DIR

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MOODS = {1: "muy mal", 2: "mal", 3: "normal", 4: "bien", 5: "excelente"}
EMPTY = {
    "profile": {"height_cm": None, "goal": "muscle", "target_kg": None, "age": None, "sex": None},
    "weights": [], "tasks": [], "routine": [], "routine_done": {}, "habits": [], "habits_done": {},
    "meals": [], "water": {}, "water_goal": 8, "sleep": {}, "sleep_goal": 8, "exercise": [],
    "money": [], "savings_goal": None, "mood": {}, "events": [], "classes": [], "maps": [],
}


def new_id() -> str:
    return uuid.uuid4().hex[:6]


def today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now()).date().isoformat()


class LifeError(ValueError):
    pass


class Life:
    def __init__(self, path=DATA_DIR / "vida.json"):
        self.path = path
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- guardar y cargar

    def load(self) -> dict:
        data = json.loads(json.dumps(EMPTY))
        if self.path.exists():
            data.update(json.loads(self.path.read_text(encoding="utf-8")))
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        temp.replace(self.path)  # nunca queda un archivo a medio escribir

    def apply(self, action: str, args: dict | None = None) -> dict:
        """Ejecuta una acción y devuelve {"say": texto para decir, "summary": resumen actualizado}."""
        handler = getattr(self, "do_" + action, None)
        if handler is None:
            raise LifeError(f"Acción desconocida: {action}")
        with self._lock:
            data = self.load()
            say = handler(data, **(args or {}))
            self._save(data)
        return {"say": say, "summary": self.summary(data)}

    # ---------------------------------------------------------------- tareas

    def do_task_add(self, data, text, due=None, priority="normal"):
        data["tasks"].append({"id": new_id(), "text": text.strip(), "due": due, "priority": priority,
                              "done": False, "created": today_iso()})
        return f"Tarea agregada: {text.strip()}"

    def _find(self, items, key, text_field="text"):
        """Por id, o por parte del texto ("la del banco")."""
        found = next((i for i in items if i["id"] == key), None)
        if found is None:
            needle = str(key).lower().strip()
            found = next((i for i in items if needle and needle in str(i.get(text_field, "")).lower()), None)
        if found is None:
            raise LifeError(f"No encontré «{key}»")
        return found

    def do_task_done(self, data, task, done=True):
        item = self._find([t for t in data["tasks"] if t["done"] != done] or data["tasks"], task)
        item["done"], item["done_at"] = done, today_iso() if done else None
        return f"Tarea completada: {item['text']}" if done else f"Tarea pendiente otra vez: {item['text']}"

    def do_task_delete(self, data, task):
        item = self._find(data["tasks"], task)
        data["tasks"].remove(item)
        return f"Tarea borrada: {item['text']}"

    def do_tasks_clear_done(self, data):
        data["tasks"] = [t for t in data["tasks"] if not t["done"]]
        return "Borré las tareas completadas"

    # ---------------------------------------------------------------- cuerpo

    def do_weight(self, data, kg, day=None):
        kg = float(kg)
        if not 20 <= kg <= 400:
            raise LifeError("Ese peso no parece correcto")
        day = day or today_iso()
        previous = data["weights"][-1]["kg"] if data["weights"] else None
        data["weights"] = [w for w in data["weights"] if w["date"] != day] + [{"date": day, "kg": round(kg, 1)}]
        data["weights"].sort(key=lambda w: w["date"])
        change = "" if previous is None else f" ({kg - previous:+.1f} kg desde la última vez)"
        return f"Peso registrado: {kg:.1f} kg{change}"

    def do_height(self, data, cm):
        cm = float(cm)
        if cm < 3:
            cm *= 100  # dijo "1.75" en metros
        if not 50 <= cm <= 250:
            raise LifeError("Esa estatura no parece correcta")
        data["profile"]["height_cm"] = round(cm)
        return f"Estatura registrada: {cm:.0f} cm"

    def do_profile(self, data, **fields):
        allowed = {"age", "sex", "goal", "target_kg", "height_cm"}
        data["profile"].update({k: v for k, v in fields.items() if k in allowed and v is not None})
        return "Perfil actualizado"

    # ---------------------------------------------------------------- comidas, agua, sueño, ejercicio

    def do_meal(self, data, text, meal=None, day=None):
        items = parse_meal(text)
        if not items:
            raise LifeError("No entendí qué comiste")
        now = datetime.now()
        meal = meal or ("desayuno" if now.hour < 11 else "almuerzo" if now.hour < 16 else
                        "merienda" if now.hour < 19 else "cena")
        known = [i for i in items if i["kcal"] is not None]
        entry = {"id": new_id(), "date": day or today_iso(), "time": now.strftime("%H:%M"), "meal": meal,
                 "text": text.strip(), "items": items, "kcal": sum(i["kcal"] for i in known),
                 "protein": round(sum(i["protein"] for i in known), 1)}
        data["meals"].append(entry)
        unknown = [i["name"] for i in items if i["kcal"] is None]
        say = f"Anoté tu {meal}: unas {entry['kcal']} calorías y {entry['protein']:.0f} gramos de proteína"
        if unknown:
            say += f". No conozco las calorías de: {', '.join(unknown)}"
        return say

    def do_meal_delete(self, data, meal_id):
        item = self._find(data["meals"], meal_id)
        data["meals"].remove(item)
        return f"Borré: {item['text']}"

    def do_water(self, data, glasses=1, day=None):
        day = day or today_iso()
        data["water"][day] = max(0, data["water"].get(day, 0) + int(glasses))
        return f"Llevas {data['water'][day]} de {data['water_goal']} vasos de agua hoy"

    def do_sleep(self, data, hours, day=None):
        hours = float(hours)
        if not 0 <= hours <= 24:
            raise LifeError("Esas horas de sueño no parecen correctas")
        data["sleep"][day or today_iso()] = hours
        return f"Dormiste {hours:g} horas" + (". ¡Bien!" if hours >= data["sleep_goal"] - 0.5 else ". Intenta descansar más")

    def do_exercise(self, data, kind, minutes, day=None):
        data["exercise"].append({"id": new_id(), "date": day or today_iso(), "kind": kind.strip(),
                                 "minutes": int(float(minutes))})
        return f"Ejercicio anotado: {kind.strip()}, {int(float(minutes))} minutos. Racha: {self._streak(data)} días"

    def _streak(self, data) -> int:
        days = {e["date"] for e in data["exercise"]}
        streak, day = 0, date.today()
        if day.isoformat() not in days:
            day -= timedelta(days=1)  # hoy todavía puedes entrenar: la racha no se corta hasta mañana
        while day.isoformat() in days:
            streak += 1
            day -= timedelta(days=1)
        return streak

    # ---------------------------------------------------------------- dinero

    def do_money(self, data, amount, category="otros", note="", kind="gasto", day=None):
        amount = float(amount)
        if amount <= 0:
            raise LifeError("El monto debe ser positivo")
        data["money"].append({"id": new_id(), "date": day or today_iso(), "amount": round(amount, 2),
                              "category": category.strip().lower() or "otros", "note": note.strip(), "kind": kind})
        month = self._month_money(data)
        verb = {"gasto": "Gasto", "ingreso": "Ingreso", "ahorro": "Ahorro"}[kind]
        return f"{verb} anotado: {amount:g} Bs. Este mes llevas {month['spent']:g} Bs gastados"

    def do_money_delete(self, data, item):
        found = self._find(data["money"], item, "note")
        data["money"].remove(found)
        return "Movimiento borrado"

    def do_savings_goal(self, data, amount):
        data["savings_goal"] = float(amount)
        return f"Meta de ahorro: {float(amount):g} Bs"

    def _month_money(self, data) -> dict:
        month = today_iso()[:7]
        items = [m for m in data["money"] if m["date"].startswith(month)]
        categories = {}
        for m in items:
            if m["kind"] == "gasto":
                categories[m["category"]] = categories.get(m["category"], 0) + m["amount"]
        return {"spent": round(sum(categories.values()), 2),
                "income": round(sum(m["amount"] for m in items if m["kind"] == "ingreso"), 2),
                "saved": round(sum(m["amount"] for m in data["money"] if m["kind"] == "ahorro"), 2),
                "categories": dict(sorted(categories.items(), key=lambda c: -c[1]))}

    # ---------------------------------------------------------------- ánimo, hábitos y rutina

    def do_mood(self, data, score, note=""):
        score = int(score)
        if score not in MOODS:
            raise LifeError("El ánimo va de 1 a 5")
        data["mood"][today_iso()] = {"score": score, "note": note.strip()}
        return f"Anotado: hoy te sientes {MOODS[score]}"

    def do_habit_add(self, data, name):
        data["habits"].append({"id": new_id(), "name": name.strip()})
        return f"Hábito agregado: {name.strip()}"

    def do_habit_delete(self, data, habit):
        item = self._find(data["habits"], habit, "name")
        data["habits"].remove(item)
        return f"Hábito borrado: {item['name']}"

    def do_habit_check(self, data, habit, done=True):
        item = self._find(data["habits"], habit, "name")
        checked = set(data["habits_done"].get(today_iso(), []))
        checked.add(item["id"]) if done else checked.discard(item["id"])
        data["habits_done"][today_iso()] = sorted(checked)
        return f"Hábito cumplido: {item['name']}. Racha: {self._habit_streak(data, item['id'])} días" if done \
            else f"Desmarcado: {item['name']}"

    def _habit_streak(self, data, habit_id) -> int:
        streak, day = 0, date.today()
        if habit_id not in data["habits_done"].get(day.isoformat(), []):
            day -= timedelta(days=1)
        while habit_id in data["habits_done"].get(day.isoformat(), []):
            streak += 1
            day -= timedelta(days=1)
        return streak

    def do_routine_add(self, data, text, time=None):
        data["routine"].append({"id": new_id(), "text": text.strip(), "time": time})
        data["routine"].sort(key=lambda r: r["time"] or "99:99")
        return f"Agregado a tu rutina: {text.strip()}" + (f" a las {time}" if time else "")

    def do_routine_delete(self, data, item):
        found = self._find(data["routine"], item)
        data["routine"].remove(found)
        return f"Quitado de tu rutina: {found['text']}"

    def do_routine_check(self, data, item, done=True):
        found = self._find(data["routine"], item)
        checked = set(data["routine_done"].get(today_iso(), []))
        checked.add(found["id"]) if done else checked.discard(found["id"])
        data["routine_done"][today_iso()] = sorted(checked)
        left = len(data["routine"]) - len(checked)
        return f"Hecho: {found['text']}. " + (f"Te quedan {left} de tu rutina" if left else "¡Rutina completa!")

    # ---------------------------------------------------------------- calendario y clases

    def do_event_add(self, data, title, day, time=None, place=""):
        datetime.fromisoformat(day)  # valida AAAA-MM-DD
        data["events"].append({"id": new_id(), "date": day, "time": time, "title": title.strip(), "place": place})
        data["events"].sort(key=lambda e: (e["date"], e["time"] or ""))
        return f"Evento agregado: {title.strip()} el {day}" + (f" a las {time}" if time else "")

    def do_event_delete(self, data, event):
        found = self._find(data["events"], event, "title")
        data["events"].remove(found)
        return f"Evento borrado: {found['title']}"

    def do_class_add(self, data, day, start, end, subject, room="", place="", teacher=""):
        day = DAYS.index(day.lower()) if isinstance(day, str) and not day.isdigit() else int(day)
        data["classes"].append({"id": new_id(), "day": day, "start": start, "end": end, "subject": subject.strip(),
                                "room": room.strip(), "place": place.strip(), "teacher": teacher.strip()})
        data["classes"].sort(key=lambda c: (c["day"], c["start"]))
        return f"Clase agregada: {subject.strip()}, {DAYS[day]} de {start} a {end}"

    def do_class_delete(self, data, item):
        found = self._find(data["classes"], item, "subject")
        data["classes"].remove(found)
        return f"Clase borrada: {found['subject']}"

    # ---------------------------------------------------------------- mapas de ideas y diagramas de flujo

    def _map(self, data, key):
        return self._find(data["maps"], key, "name")

    def do_map_add(self, data, name, kind="ideas"):
        data["maps"].append({"id": new_id(), "name": name.strip(), "kind": kind, "nodes": [], "links": []})
        return f"{'Diagrama' if kind == 'flujo' else 'Mapa de ideas'} creado: {name.strip()}"

    def do_map_delete(self, data, map_):
        found = self._map(data, map_)
        data["maps"].remove(found)
        return f"Borré {found['name']}"

    def do_node_add(self, data, map_, text, parent=None, shape="box", label=""):
        """Sin posición: aparece cerca de su nodo padre (x, y van de 0 a 1 dentro del lienzo)."""
        found = self._map(data, map_)
        node = {"id": new_id(), "text": text.strip(), "shape": shape, "x": 0.5, "y": 0.15}
        if parent:
            father = self._find(found["nodes"], parent)
            siblings = [l for l in found["links"] if l["from"] == father["id"]]
            if found["kind"] == "flujo":
                node["x"], node["y"] = min(0.92, father["x"] + 0.2 * len(siblings)), min(0.92, father["y"] + 0.18)
            else:
                import math
                angle = len(siblings) * 1.1 + 0.4
                node["x"] = min(0.95, max(0.05, father["x"] + 0.22 * math.cos(angle)))
                node["y"] = min(0.95, max(0.05, father["y"] + 0.22 * math.sin(angle)))
            found["links"].append({"from": father["id"], "to": node["id"], "label": label})
        elif found["nodes"]:
            node["x"] = min(0.95, 0.1 + 0.15 * (len(found["nodes"]) % 6))
            node["y"] = min(0.95, 0.15 + 0.15 * (len(found["nodes"]) // 6))
        found["nodes"].append(node)
        return f"Agregué «{text.strip()}» a {found['name']}"

    def do_node_move(self, data, map_, node, x, y):
        item = self._find(self._map(data, map_)["nodes"], node)
        item["x"], item["y"] = min(0.98, max(0.02, float(x))), min(0.98, max(0.02, float(y)))
        return ""

    def do_node_delete(self, data, map_, node):
        found = self._map(data, map_)
        item = self._find(found["nodes"], node)
        found["nodes"].remove(item)
        found["links"] = [l for l in found["links"] if item["id"] not in (l["from"], l["to"])]
        return f"Quité «{item['text']}»"

    def do_link_add(self, data, map_, source, target, label=""):
        found = self._map(data, map_)
        a, b = self._find(found["nodes"], source), self._find(found["nodes"], target)
        found["links"].append({"from": a["id"], "to": b["id"], "label": label})
        return f"Conecté «{a['text']}» con «{b['text']}»"

    # ---------------------------------------------------------------- resumen para mostrar

    def goals(self, data) -> dict:
        """Calorías y proteínas diarias para ganar masa muscular (o mantener)."""
        weight = data["weights"][-1]["kg"] if data["weights"] else None
        profile = data["profile"]
        if weight is None:
            return {"kcal": 2500, "protein": 120, "estimated": True}
        if profile.get("age") and profile.get("sex") and profile.get("height_cm"):
            base = 10 * weight + 6.25 * profile["height_cm"] - 5 * profile["age"] + (5 if profile["sex"] == "hombre" else -161)
            maintenance = base * 1.55  # actividad moderada
        else:
            maintenance = weight * 33
        extra = {"muscle": 300, "lose": -450, "keep": 0}.get(profile.get("goal"), 0)
        protein = weight * (1.8 if profile.get("goal") == "muscle" else 1.4)
        return {"kcal": round(maintenance + extra, -1), "protein": round(protein), "estimated": False}

    def summary(self, data: dict | None = None, now: datetime | None = None) -> dict:
        data = data or self.load()
        now = now or datetime.now()
        today = now.date().isoformat()
        weekday = now.weekday()
        clock = now.strftime("%H:%M")
        profile = data["profile"]
        weight = data["weights"][-1]["kg"] if data["weights"] else None
        bmi = None
        if weight and profile.get("height_cm"):
            bmi = round(weight / (profile["height_cm"] / 100) ** 2, 1)
        meals = [m for m in data["meals"] if m["date"] == today]
        classes_today = [c for c in data["classes"] if c["day"] == weekday]
        now_class = next((c for c in classes_today if c["start"] <= clock < c["end"]), None)
        next_class = next((c for c in classes_today if c["start"] > clock), None)
        week = [(now.date() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        events = [e for e in data["events"] if today <= e["date"] <= (now.date() + timedelta(days=30)).isoformat()]
        routine_done = set(data["routine_done"].get(today, []))
        habits_done = set(data["habits_done"].get(today, []))
        return {
            "today": today, "weekday": DAYS[weekday], "clock": clock,
            "tasks": sorted([t for t in data["tasks"] if not t["done"]],
                            key=lambda t: (t["priority"] != "alta", t["due"] or "9999")),
            "tasks_done_today": [t for t in data["tasks"] if t["done"] and t.get("done_at") == today],
            "body": {"weight": weight, "height_cm": profile.get("height_cm"), "bmi": bmi,
                     "bmi_label": None if bmi is None else "bajo" if bmi < 18.5 else "normal" if bmi < 25
                     else "sobrepeso" if bmi < 30 else "obesidad",
                     "history": data["weights"][-30:], "goal": profile.get("goal"), "target_kg": profile.get("target_kg")},
            "food": {"meals": meals, "kcal": sum(m["kcal"] for m in meals),
                     "protein": round(sum(m["protein"] for m in meals), 1), "goals": self.goals(data),
                     "week": [{"date": d, "kcal": sum(m["kcal"] for m in data["meals"] if m["date"] == d)} for d in week]},
            "water": {"today": data["water"].get(today, 0), "goal": data["water_goal"]},
            "sleep": {"last": data["sleep"].get(today), "goal": data["sleep_goal"],
                      "week": [{"date": d, "hours": data["sleep"].get(d)} for d in week]},
            "exercise": {"streak": self._streak(data),
                         "week_minutes": sum(e["minutes"] for e in data["exercise"] if e["date"] in week),
                         "recent": data["exercise"][-5:]},
            "money": {**self._month_money(data), "goal": data["savings_goal"], "recent": data["money"][-6:]},
            "mood": {"today": data["mood"].get(today),
                     "week": [{"date": d, "score": (data["mood"].get(d) or {}).get("score")} for d in week]},
            "habits": [{**h, "done": h["id"] in habits_done, "streak": self._habit_streak(data, h["id"])}
                       for h in data["habits"]],
            "routine": [{**r, "done": r["id"] in routine_done} for r in data["routine"]],
            "classes": {"today": classes_today, "now": now_class, "next": next_class, "week": data["classes"]},
            "events": events, "holidays": holidays.upcoming(now.date(), 6),
            "maps": data["maps"],
        }


life = Life()
