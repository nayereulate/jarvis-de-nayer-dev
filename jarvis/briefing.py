"""Informe del día: saludo, hora, clima, estado de la PC y recordatorios de hoy."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

from .paths import DATA_DIR

STATE_FILE = DATA_DIR / "state.json"


def greeting(now: datetime) -> str:
    if 5 <= now.hour < 12:
        return "Buenos días"
    if 12 <= now.hour < 20:
        return "Buenas tardes"
    return "Buenas noches"


def weather(place: str | None = None) -> str | None:
    """Clima actual de wttr.in: de place, de JARVIS_CITY o de la ubicación aproximada de la conexión."""
    city = urllib.parse.quote(place or os.environ.get("JARVIS_CITY", ""))
    try:
        request = urllib.request.Request(f"https://wttr.in/{city}?format=j1&lang=es", headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        current = data["current_condition"][0]
        today = data["weather"][0]
        description = (current.get("lang_es") or current["weatherDesc"])[0]["value"].strip().lower()
        area = data["nearest_area"][0]["areaName"][0]["value"]
        return (f"En {area} hace {current['temp_C']} grados, {description}. "
                f"Máxima de {today['maxtempC']} y mínima de {today['mintempC']}.")
    except Exception:
        return None


def build(now: datetime, status: dict, weather_text: str | None, reminders: list[dict], name: str = "") -> str:
    parts = [f"{greeting(now)}{', ' + name if name else ''}. Son las {now:%H:%M}."]
    if weather_text:
        parts.append(weather_text)
    pc = f"La CPU está al {status['cpu_percent']:.0f} por ciento y la RAM al {status['ram_percent']:.0f}."
    if status["disk_percent"] >= 90:
        pc += f" Atención: el disco está al {status['disk_percent']:.0f} por ciento, conviene liberar espacio."
    parts.append(pc)
    today = [item for item in reminders if datetime.fromisoformat(item["due"]).date() == now.date()]
    if today:
        listed = "; ".join(f"a las {datetime.fromisoformat(item['due']):%H:%M}, {item['text']}" for item in today[:5])
        parts.append(f"Hoy tienes {len(today)} recordatorio{'s' if len(today) > 1 else ''}: {listed}.")
    else:
        parts.append("No tienes recordatorios para hoy.")
    return " ".join(parts)


def done_today(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("briefing") == now.date().isoformat()
    except (OSError, ValueError):
        return False


def mark_done(now: datetime | None = None) -> None:
    now = now or datetime.now()
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    state["briefing"] = now.date().isoformat()
    DATA_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
