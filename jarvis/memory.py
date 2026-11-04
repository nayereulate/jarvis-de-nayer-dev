"""Lo que Jarvis recuerda del usuario entre conversaciones."""
import json
import threading

from .paths import DATA_DIR

MAX_FACTS = 200


class Memory:
    def __init__(self, path=DATA_DIR / "memory.json"):
        self.path = path
        self._lock = threading.Lock()

    def facts(self) -> list[str]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, facts: list[str]) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

    def remember(self, fact: str) -> str:
        fact = " ".join(fact.split())
        if not fact:
            raise ValueError("No hay nada que recordar")
        with self._lock:
            facts = self.facts()
            if fact not in facts:
                facts = (facts + [fact])[-MAX_FACTS:]
                self._save(facts)
        return f"Recordaré: {fact}"

    def forget(self, text: str) -> str:
        needle = text.lower().strip()
        with self._lock:
            facts = self.facts()
            kept = [fact for fact in facts if needle not in fact.lower()]
            self._save(kept)
        removed = len(facts) - len(kept)
        if not removed:
            raise ValueError(f"No recuerdo nada sobre «{text}»")
        return f"Olvidé {removed} recuerdo(s)"


memory = Memory()
