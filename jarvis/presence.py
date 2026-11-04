"""Presencia con la webcam: saluda por tu nombre al llegar, bloquea la PC al irte
y, en modo guardia, la bloquea si se sienta alguien que no conoce."""
import logging
import os
import threading
import time

ARRIVE_SECONDS = 1.5  # cara vista seguido para dar por llegado
AWAY_SECONDS = float(os.environ.get("JARVIS_AWAY_MINUTES", "3")) * 60
INPUT_MEANS_PRESENT = 5  # si se usó el teclado o el mouse hace poco, sigues ahí
STRANGER_SECONDS = 6  # una cara desconocida tanto tiempo, sin ver a nadie conocido, activa la guardia
CHECK_INTERVAL = 0.25
ENROLL_SAMPLES = 15

log = logging.getLogger("jarvis.presence")


class PresenceTracker:
    """Solo lógica. Por cada cuadro recibe:
    faces: cuántas caras se ven; who: nombre reconocido, "" si la cara es de un desconocido,
    None si no se pudo saber (cara chica o de perfil); idle: segundos sin usar teclado y mouse.
    Devuelve ("arrive", {"away": segundos o None, "name": ...}), ("leave", {}), ("stranger", {}) o None.
    """

    def __init__(self):
        self.state = "unknown"  # unknown, present, away
        self.last_seen = None
        self.seen_since = None
        self.left_at = None
        self.last_name = None
        self.last_name_time = None
        self.stranger_since = None
        self.stranger_fired = False

    def update(self, faces: int, who: str | None, idle: float, now: float, guard: bool = False):
        if who:
            self.last_name, self.last_name_time = who, now
            self.stranger_since, self.stranger_fired = None, False
        if faces or idle < INPUT_MEANS_PRESENT:
            self.last_seen = now
        if not faces:
            self.seen_since = None
            self.stranger_since = None
            if self.state == "present" and now - self.last_seen >= AWAY_SECONDS:
                self.state = "away"
                self.left_at = self.last_seen
                self.stranger_fired = False
                return "leave", {}
            return None
        if guard and who == "" and not self.stranger_fired:
            if self.stranger_since is None:
                self.stranger_since = now
            recently_known = self.last_name_time is not None and now - self.last_name_time < STRANGER_SECONDS
            if now - self.stranger_since >= STRANGER_SECONDS and not recently_known:
                self.stranger_fired = True
                return "stranger", {}
        if self.seen_since is None:
            self.seen_since = now
        if self.state != "present" and now - self.seen_since >= ARRIVE_SECONDS:
            away = None if self.left_at is None else now - self.left_at
            self.state = "present"
            name = self.last_name if self.last_name_time and now - self.last_name_time < 5 else None
            return "arrive", {"away": away, "name": name}
        return None


class Presence:
    def __init__(self, on_event, paused):
        """on_event(kind, info). paused(): True cuando otra parte de Jarvis usa la cámara (el holograma)."""
        self.on_event = on_event
        self.paused = paused
        self.enabled = os.environ.get("JARVIS_PRESENCE", "1") != "0"
        self.guard = os.environ.get("JARVIS_GUARD", "1") != "0"
        self.state = "off"
        self.tracker = PresenceTracker()
        self.book = None
        self._thread = None
        self._enroll = None  # {"name", "features", "done": Event, "error"}

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="jarvis-presence", daemon=True)
            self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def set_guard(self, enabled: bool) -> None:
        self.guard = enabled

    def known_people(self) -> list[str]:
        return self.book.known() if self.book else []

    def enroll(self, name: str, timeout: float = 25) -> str:
        """Aprende la cara de quien esté frente a la cámara."""
        if self._thread is None:
            raise RuntimeError("La detección de presencia no está corriendo")
        if not self.enabled:
            raise RuntimeError("Activa primero la detección de presencia")
        if self.paused():
            raise RuntimeError("Apaga el modo holograma: la cámara está ocupada")
        request = {"name": name.strip(), "features": [], "done": threading.Event()}
        self._enroll = request
        finished = request["done"].wait(timeout)
        self._enroll = None
        if not finished or len(request["features"]) < 5:
            raise RuntimeError("No vi bien tu cara. Mira a la cámara, con luz de frente, y vuelve a intentarlo")
        self.book.add(request["name"], request["features"])
        return f"Aprendí tu cara, {request['name']} ({len(request['features'])} muestras)"

    def forget(self, name: str | None = None) -> int:
        if not self.book:
            return 0
        return self.book.forget(name)

    def _run(self) -> None:
        from . import winctl
        from .camera import open_camera
        from .faces import FaceBook, FaceID

        capture = None
        failures = 0
        try:
            face_id = FaceID()
            self.book = FaceBook()
        except Exception as error:
            log.exception("No pude cargar el reconocimiento facial")
            self.state = f"error: {error}"
            return
        while True:
            if not self.enabled or self.paused():
                if capture is not None:
                    capture.release()
                    capture = None
                self.state = "paused" if self.enabled else "off"
                # Con el holograma activo estás frente a la PC: no cuenta como ausencia.
                self.tracker.last_seen = time.monotonic()
                time.sleep(1)
                continue
            try:
                if capture is None:
                    capture, _ = open_camera(640, 360)
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError("La cámara no entrega imagen")
                faces = face_id.faces(frame)
                who = None
                if faces:
                    feature = face_id.feature(frame, faces[0])
                    if feature is not None:
                        if self._enroll is not None:
                            self._collect(feature)
                        name, _ = self.book.match(feature)
                        who = name or ("" if self.book.names else None)
                failures = 0
            except Exception as error:
                failures += 1
                if capture is not None:
                    capture.release()
                    capture = None
                self.state = f"error: {error}"
                time.sleep(min(60, 5 * failures))
                continue
            # Mientras aprende una cara nueva, esa persona todavía es "desconocida": sin guardia.
            guard = self.guard and bool(self.book.names) and self._enroll is None
            event = self.tracker.update(len(faces), who, winctl.idle_seconds(), time.monotonic(), guard)
            self.state = self.tracker.state
            if event:
                try:
                    self.on_event(*event)
                except Exception:
                    log.exception("Falló la reacción a la presencia")
            time.sleep(CHECK_INTERVAL)

    def _collect(self, feature) -> None:
        request = self._enroll
        request["features"].append(feature)
        if len(request["features"]) >= ENROLL_SAMPLES:
            request["done"].set()
