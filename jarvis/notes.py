"""Notas adhesivas holográficas. Se guardan en disco con su posición en la pantalla."""
import json
import threading
import uuid

from .paths import DATA_DIR

MAX_NOTES = 30
COLORS = ["#ffd166", "#4fd8ff", "#7bffb5", "#ff8fab", "#c3a6ff"]


class Notes:
    def __init__(self, path=DATA_DIR / "notes.json"):
        self.path = path
        self._lock = threading.Lock()

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, text: str) -> dict:
        text = " ".join(text.split())
        if not text:
            raise ValueError("La nota está vacía")
        with self._lock:
            items = self.all()
            if len(items) >= MAX_NOTES:
                raise ValueError(f"Ya hay {MAX_NOTES} notas; borra alguna primero")
            # Las nuevas aparecen escalonadas en la parte de arriba, para no taparse entre sí.
            slot = len(items) % 6
            item = {"id": uuid.uuid4().hex[:6], "text": text[:300], "x": 0.08 + slot * 0.14,
                    "y": 0.12 + (len(items) // 6) * 0.2, "color": COLORS[len(items) % len(COLORS)]}
            self._save(items + [item])
        return item

    def move(self, note_id: str, x: float, y: float) -> None:
        with self._lock:
            items = self.all()
            for item in items:
                if item["id"] == note_id:
                    item["x"], item["y"] = min(max(x, 0.0), 0.95), min(max(y, 0.0), 0.95)
            self._save(items)

    def delete(self, note_id: str) -> dict:
        with self._lock:
            items = self.all()
            found = next((item for item in items if item["id"] == note_id), None)
            if found is None:
                raise ValueError(f"No hay una nota con id {note_id}")
            self._save([item for item in items if item is not found])
        return found


notes = Notes()
