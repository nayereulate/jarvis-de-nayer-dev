"""Avisos para la página: lo que pasa con la escucha de la PC aparece también en pantalla."""
import threading
from collections import deque


class Events:
    def __init__(self, keep: int = 200):
        self._items = deque(maxlen=keep)
        self._next_id = 1
        self._lock = threading.Lock()

    def publish(self, kind: str, **data) -> None:
        with self._lock:
            self._items.append({"id": self._next_id, "type": kind, **data})
            self._next_id += 1

    def recent(self, kinds: set[str], count: int) -> list[dict]:
        """Los últimos avisos de esos tipos, para que una ventana recién abierta muestre la conversación."""
        with self._lock:
            return [item for item in self._items if item["type"] in kinds][-count:]

    def since(self, after: int) -> tuple[list[dict], int]:
        """Una página recién abierta (after < 0) o de antes de un reinicio no recibe el historial."""
        with self._lock:
            last = self._next_id - 1
            if after < 0 or after > last:
                return [], last
            return [item for item in self._items if item["id"] > after], last
