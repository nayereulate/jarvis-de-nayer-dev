"""Recordatorios y alarmas. Se guardan en disco para que sobrevivan a un reinicio de Jarvis."""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta

from .paths import DATA_DIR

log = logging.getLogger("jarvis.reminders")


def parse_when(minutes=None, at=None, now: datetime | None = None) -> datetime:
    """minutes desde ahora, o at como "HH:MM" (hoy, o mañana si ya pasó) o "YYYY-MM-DDTHH:MM"."""
    now = now or datetime.now()
    if minutes is not None:
        minutes = float(minutes)
        if minutes <= 0:
            raise ValueError("Los minutos deben ser positivos")
        return now + timedelta(minutes=minutes)
    if not at:
        raise ValueError("Indica minutes o at")
    at = str(at).strip()
    try:
        moment = datetime.fromisoformat(at)
    except ValueError:
        try:
            clock = datetime.strptime(at, "%H:%M").time()
        except ValueError as error:
            raise ValueError(f"Hora no válida: {at}. Usa HH:MM o AAAA-MM-DDTHH:MM") from error
        moment = datetime.combine(now.date(), clock)
        if moment <= now:
            moment += timedelta(days=1)
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    if moment <= now:
        raise ValueError("Esa hora ya pasó")
    return moment


class Reminders:
    def __init__(self, path=DATA_DIR / "reminders.json"):
        self.path = path
        self.on_due = None  # el servidor decide cómo avisar
        self._lock = threading.Lock()
        self._thread = None

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, text: str, when: datetime, alarm: bool = False, kind: str = "reminder") -> dict:
        """kind: "reminder" o "timer" (los temporizadores se ven como un anillo que se vacía)."""
        item = {"id": uuid.uuid4().hex[:6], "text": text.strip(), "due": when.isoformat(timespec="seconds"),
                "alarm": bool(alarm), "kind": kind, "created": datetime.now().isoformat(timespec="seconds")}
        with self._lock:
            self._save(sorted(self.all() + [item], key=lambda entry: entry["due"]))
        return item

    def cancel(self, reminder_id: str) -> dict:
        with self._lock:
            items = self.all()
            found = next((item for item in items if item["id"] == reminder_id), None)
            if found is None:
                raise ValueError(f"No hay un recordatorio con id {reminder_id}")
            self._save([item for item in items if item is not found])
        return found

    def pop_due(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now()
        with self._lock:
            items = self.all()
            due = [item for item in items if datetime.fromisoformat(item["due"]) <= now]
            if due:
                self._save([item for item in items if item not in due])
        return due

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="jarvis-reminders", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                for item in self.pop_due():
                    if self.on_due:
                        self.on_due(item)
            except Exception:
                log.exception("Falló un recordatorio")
            time.sleep(1)


reminders = Reminders()
