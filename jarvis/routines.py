"""Modos o rutinas: varias acciones con un solo nombre, como "modo trabajo"."""
import json
import threading

from .paths import DATA_DIR

DEFAULT_ROUTINES = {
    "trabajo": {
        "say": "Modo trabajo listo.",
        "actions": [
            {"tool": "open_app", "args": {"name": "explorador"}},
            {"tool": "open_app", "args": {"name": "edge"}},
            {"tool": "open_app", "args": {"name": "notepad"}},
        ],
    },
    "juego": {
        "say": "Modo juego activado. Que lo disfrutes.",
        "actions": [
            {"tool": "hologram_off", "args": {}},
            {"tool": "run_powershell", "args": {"command": "Start-Process 'steam://open/main'"}},
        ],
    },
    "descanso": {
        "say": "Pausa activada. Bloqueo la PC.",
        "actions": [
            {"tool": "lock_pc", "args": {}},
        ],
    },
}


class Routines:
    def __init__(self, path=DATA_DIR / "routines.json"):
        self.path = path
        self._lock = threading.Lock()

    def all(self) -> dict:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_ROUTINES))
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, routines: dict) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(routines, ensure_ascii=False, indent=1), encoding="utf-8")

    def get(self, name: str) -> dict:
        routines = self.all()
        key = name.lower().removeprefix("modo ").strip()
        if key not in routines:
            raise ValueError(f"No existe la rutina {name}. Disponibles: {', '.join(routines)}")
        return routines[key]

    def save(self, name: str, actions: list[dict], say: str = "") -> None:
        key = name.lower().removeprefix("modo ").strip()
        if not key or not actions:
            raise ValueError("La rutina necesita un nombre y al menos una acción")
        with self._lock:
            routines = self.all()
            routines[key] = {"say": say, "actions": [{"tool": a["tool"], "args": a.get("args") or {}} for a in actions]}
            self._save(routines)

    def delete(self, name: str) -> None:
        key = name.lower().removeprefix("modo ").strip()
        with self._lock:
            routines = self.all()
            if routines.pop(key, None) is None:
                raise ValueError(f"No existe la rutina {name}")
            self._save(routines)


routines = Routines()
