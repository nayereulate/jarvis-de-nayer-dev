"""Modo holograma: tu imagen de cámara como fondo y las manos controlan el mouse y las ventanas.

Corre como proceso aparte (python -m jarvis.hologram) porque Qt necesita su propio hilo principal.
"""
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import mediapipe as mp
import psutil
from mediapipe.tasks.python import BaseOptions, vision
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from . import holoviz, tools, winctl
from .camera import open_camera
from .gestures import Engine, HandInput, hand_angle, hand_pose, middle_pinch_ratio, pinch_point, pinch_ratio

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
FRAME_WIDTH, FRAME_HEIGHT = 1280, 720
DETECT_SIZE = (640, 360)
TOKEN_FILE = ROOT / "data" / "token.txt"
SERVER = os.environ.get("JARVIS_URL", "http://127.0.0.1:8765")
MESSAGE_SECONDS = 14
BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
         (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]
CYAN = QColor(79, 216, 255)
AMBER = QColor(255, 181, 71)
MUTED = QColor(111, 157, 179)
WHITE = QColor(239, 252, 255)
VIOLET = QColor(190, 130, 255)


class Tracker(QThread):
    frame_ready = Signal(QImage, list, list)
    failed = Signal(str)
    scan = False  # el escáner de identidad pide buscar caras

    def _faces(self, rgb, state):
        """Caras con nombre, cada 5 cuadros (reconocer es más lento que seguir las manos)."""
        if not self.scan:
            return []
        state["count"] += 1
        if state["count"] % 5:
            return state["last"]
        from .faces import FaceBook, FaceID

        if state.get("face_id") is None:
            state["face_id"] = FaceID()
        if time.monotonic() - state.get("book_time", 0) > 30:
            state["book"], state["book_time"] = FaceBook(), time.monotonic()
        small = cv2.cvtColor(cv2.resize(rgb, DETECT_SIZE), cv2.COLOR_RGB2BGR)
        found = []
        for face in state["face_id"].faces(small)[:3]:
            feature = state["face_id"].feature(small, face)
            name = state["book"].match(feature)[0] if feature is not None else None
            x, y, w, h = face[:4]
            found.append({"box": (x / DETECT_SIZE[0], y / DETECT_SIZE[1], w / DETECT_SIZE[0], h / DETECT_SIZE[1]),
                          "name": name, "known": name is not None})
        state["last"] = found
        return found

    def run(self):
        try:
            if not MODEL.exists():
                MODEL.parent.mkdir(exist_ok=True)
                urllib.request.urlretrieve(MODEL_URL, MODEL)
            capture, name = open_camera(FRAME_WIDTH, FRAME_HEIGHT)
            options = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(MODEL)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            detector = vision.HandLandmarker.create_from_options(options)
            print(f"LISTO cámara={name}", flush=True)
            start = time.monotonic()
            last_stamp = -1
            face_state = {"count": 0, "last": []}
            while not self.isInterruptionRequested():
                ok, frame = capture.read()
                if not ok:
                    continue
                rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                stamp = max(int((time.monotonic() - start) * 1000), last_stamp + 1)
                last_stamp = stamp
                small = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.resize(rgb, DETECT_SIZE))
                result = detector.detect_for_video(small, stamp)
                hands = []
                for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
                    hand_id = handedness[0].category_name
                    if any(hand["id"] == hand_id for hand in hands):
                        hand_id += "-2"
                    hands.append({"id": hand_id, "points": [(p.x, p.y) for p in landmarks]})
                try:
                    faces = self._faces(rgb, face_state)
                except Exception as error:
                    print(f"Escáner sin caras: {error}", flush=True)
                    faces, self.scan = [], False
                height, width, _ = rgb.shape
                self.frame_ready.emit(QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy(), hands, faces)
            capture.release()
        except Exception as error:
            self.failed.emit(str(error))


class Feed(QThread):
    """Datos para los paneles: uso de la PC y lo último que se habló con Jarvis."""

    updated = Signal(dict)

    def run(self):
        token = TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else ""
        after = -1
        gpu = None
        tick = 0
        psutil.cpu_percent()
        while not self.isInterruptionRequested():
            data = {"cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent, "messages": [],
                    "modes": None, "notes": None}
            if tick % 6 == 0:
                gpu = read_gpu()
            data["gpu"] = gpu
            try:
                request = urllib.request.Request(f"{SERVER}/api/events?after={after}",
                                                 headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    events = json.load(response)
                after = events["last"]
                data["modes"] = events.get("modes")
                data["notes"] = events.get("notes")
                data["messages"] = [(event["type"], event["text"]) for event in events["events"]
                                    if event["type"] in ("user", "jarvis") and event.get("text")]
            except Exception:
                pass  # sin Jarvis, los paneles muestran solo el uso de la PC
            self.updated.emit(data)
            tick += 1
            self.msleep(500)


def call_server(method: str, path: str, body: dict | None = None) -> None:
    """Avisa al servidor en segundo plano (mover o borrar una nota)."""
    def send():
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
            request = urllib.request.Request(f"{SERVER}{path}", method=method,
                                             data=json.dumps(body).encode() if body is not None else None,
                                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=5).close()
        except Exception as error:
            print(f"No pude avisar al servidor: {error}", flush=True)
    threading.Thread(target=send, daemon=True).start()


class Floating:
    """Lo que flota y se pellizca (teclado y notas). Engine da píxeles de pantalla; aquí se pasan a la ventana."""

    def __init__(self, keyboard, notes, flags, to_window):
        self.keyboard, self.notes, self.flags, self.to_window = keyboard, notes, flags, to_window

    def hit(self, point):
        p = self.to_window(point)
        if self.flags.get("keyboard"):
            key = self.keyboard.hit(p)
            if key is not None:
                return ("key", key)
        if self.flags.get("notes"):
            note_id = self.notes.hit(p)
            if note_id is not None:
                return ("note", note_id)
        return None

    def press(self, token, point):
        kind, value = token
        if kind == "key":
            self.keyboard.press(value)
        else:
            self.notes.press(value, self.to_window(point))

    def drag(self, token, point):
        if token[0] == "note":
            self.notes.drag(token[1], self.to_window(point))

    def release(self, token, point):
        if token[0] == "note":
            self.notes.release(token[1])

    def fist(self, point):
        return bool(self.flags.get("notes")) and self.notes.erase_at(self.to_window(point))


def read_gpu():
    """(uso %, temperatura °C) de la tarjeta NVIDIA, o None."""
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        usage, temperature = done.stdout.strip().splitlines()[0].split(",")
        return int(usage), int(temperature)
    except Exception:
        return None


class Volume:
    """Volumen general de Windows (0 a 1)."""

    def __init__(self):
        from pycaw.pycaw import AudioUtilities

        self.endpoint = AudioUtilities.GetSpeakers().EndpointVolume

    def get(self) -> float:
        return float(self.endpoint.GetMasterVolumeLevelScalar())

    def set(self, level: float) -> None:
        self.endpoint.SetMasterVolumeLevelScalar(float(level), None)


def sphere_lines():
    """Paralelos y meridianos de una esfera de radio 1, como listas de puntos 3D."""
    lines = []
    for lat in range(-60, 61, 30):
        y, r = math.sin(math.radians(lat)), math.cos(math.radians(lat))
        lines.append([(r * math.cos(math.radians(a)), y, r * math.sin(math.radians(a))) for a in range(0, 361, 10)])
    for lon in range(0, 180, 20):
        lines.append([(math.cos(math.radians(a)) * math.cos(math.radians(lon)), math.sin(math.radians(a)),
                       math.cos(math.radians(a)) * math.sin(math.radians(lon))) for a in range(0, 361, 10)])
    return lines


SPHERE = sphere_lines()
# Puntos de datos que brillan sobre la superficie, siempre los mismos.
NODES = [(math.cos(math.radians(lat)) * math.cos(math.radians(lon)), math.sin(math.radians(lat)),
          math.cos(math.radians(lat)) * math.sin(math.radians(lon)))
         for lat, lon in ((40, 10), (-15, 60), (25, 130), (-35, 200), (55, 250), (5, 300), (-50, 330), (15, 20))]


def rotate(point, yaw, pitch):
    x, y, z = point
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


class Mapper:
    """Pasa coordenadas normalizadas de la cámara a la pantalla, igual que se dibuja la imagen."""

    def __init__(self, screen_width, screen_height):
        self.scale = max(screen_width / FRAME_WIDTH, screen_height / FRAME_HEIGHT)
        self.width, self.height = FRAME_WIDTH * self.scale, FRAME_HEIGHT * self.scale
        self.left, self.top = (screen_width - self.width) / 2, (screen_height - self.height) / 2

    def __call__(self, x, y):
        return self.left + x * self.width, self.top + y * self.height

    def target(self) -> QRectF:
        return QRectF(self.left, self.top, self.width, self.height)


class Background(QWidget):
    """Tu imagen de cámara, justo encima del escritorio y debajo de todas las ventanas."""

    def __init__(self, geometry, mapper):
        flags = (Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint
                 | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setGeometry(geometry)
        self.mapper = mapper
        self.image = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(2, 7, 13))
        if self.image is not None:
            painter.drawImage(self.mapper.target(), self.image)
        vignette = QRadialGradient(self.rect().center(), max(self.width(), self.height()) * 0.7)
        vignette.setColorAt(0.55, QColor(2, 7, 13, 0))
        vignette.setColorAt(1, QColor(2, 7, 13, 200))
        painter.fillRect(self.rect(), vignette)
        painter.fillRect(self.rect(), QColor(20, 120, 160, 28))


class Overlay(QWidget):
    """Tus manos dibujadas por encima de todo, para ver dónde estás apuntando."""

    def __init__(self, geometry):
        flags = (Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                 | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(geometry)
        self.hands = []
        self.status = ""
        self.stats = {}
        self.message = None  # (quién, texto, cuándo)
        self.strokes = []  # en coordenadas de esta ventana
        self.globe = None  # dict de Engine.globe cuando la esfera está a la vista
        self.knob = None  # (punto, nivel)
        self.extras = lambda painter: None  # los hologramas de holoviz
        self.font = QFont("Consolas", 11)
        self.big = QFont("Consolas", 30)
        self.small = QFont("Consolas", 9)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._draw_strokes(painter)
        if self.globe:
            self._draw_globe(painter)
        self.extras(painter)
        if self.knob:
            self._draw_knob(painter)
        for points, pointer, pinch in self.hands:
            # Cian: mover. Ámbar: pellizco (clic o agarrar). Violeta: pellizco con el medio (clic derecho).
            color = {"left": AMBER, "right": VIOLET}.get(pinch, CYAN)
            pinching = bool(pinch)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 150), 2))
            for a, b in BONES:
                painter.drawLine(QPointF(*points[a]), QPointF(*points[b]))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 200))
            for x, y in points:
                painter.drawEllipse(QPointF(x, y), 3, 3)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, 3))
            painter.drawEllipse(QPointF(*pointer), 14 if pinching else 20, 14 if pinching else 20)
        painter.setFont(self.font)
        painter.setPen(CYAN)
        painter.drawText(24, 36, "J.A.R.V.I.S. · MODO HOLOGRAMA" + (f" · {self.status}" if self.status else ""))
        self._draw_panel(painter)
        self._draw_message(painter)

    def _draw_strokes(self, painter):
        """Trazos de luz: un halo ancho y suave con una línea brillante encima."""
        for width, color in ((14, QColor(79, 216, 255, 50)), (6, QColor(79, 216, 255, 140)), (2, WHITE)):
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            for stroke in self.strokes:
                if len(stroke) == 1:
                    painter.drawPoint(QPointF(*stroke[0]))
                    continue
                path = QPainterPath(QPointF(*stroke[0]))
                for point in stroke[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)

    def _draw_globe(self, painter):
        """Esfera de alambre en 3D: la cara de atrás se ve tenue, la de adelante brillante."""
        globe = self.globe
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) * 0.22 * globe["scale"]
        glow = QRadialGradient(center, radius * 1.4)
        glow.setColorAt(0, QColor(79, 216, 255, 60))
        glow.setColorAt(1, QColor(79, 216, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 1.4, radius * 1.4)
        project = lambda p: QPointF(center.x() + p[0] * radius, center.y() - p[1] * radius)
        for line in SPHERE:
            turned = [rotate(p, globe["yaw"], globe["pitch"]) for p in line]
            for a, b in zip(turned, turned[1:]):
                front = (a[2] + b[2]) / 2 > 0
                painter.setPen(QPen(QColor(79, 216, 255, 200 if front else 45), 1.6 if front else 1))
                painter.drawLine(project(a), project(b))
        # Anillo en órbita que se inclina solo.
        ring = [rotate((1.35 * math.cos(math.radians(a)), 0, 1.35 * math.sin(math.radians(a))),
                       globe["yaw"] * 0.4, 0.5 + 0.25 * math.sin(globe["tilt"])) for a in range(0, 361, 6)]
        for a, b in zip(ring, ring[1:]):
            painter.setPen(QPen(QColor(255, 181, 71, 170 if (a[2] + b[2]) > 0 else 50), 2))
            painter.drawLine(project(a), project(b))
        for node in NODES:
            x, y, z = rotate(node, globe["yaw"], globe["pitch"])
            if z > 0:
                pulse = 4 + 2 * math.sin(globe["tilt"] * 3 + x * 5)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 230))
                painter.drawEllipse(project((x, y, z)), pulse, pulse)
        painter.setFont(self.small)
        painter.setPen(MUTED)
        painter.drawText(QRectF(center.x() - 200, center.y() + radius * 1.45, 400, 20), Qt.AlignCenter,
                         "ESFERA HOLOGRÁFICA · PELLIZCA PARA GIRAR · DOS MANOS PARA AGRANDAR")

    def _draw_knob(self, painter):
        """La perilla de volumen junto a la mano."""
        point, level = self.knob
        center = QPointF(point[0], point[1] - 150)
        radius = 70
        box = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setBrush(QColor(2, 14, 24, 170))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius + 14, radius + 14)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(79, 216, 255, 60), 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(box, 225 * 16, -270 * 16)
        painter.setPen(QPen(AMBER if level > 0.85 else CYAN, 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(box, 225 * 16, int(-270 * 16 * level))
        painter.setFont(self.big)
        painter.setPen(WHITE)
        painter.drawText(QRectF(center.x() - radius, center.y() - 26, radius * 2, 52), Qt.AlignCenter,
                         f"{round(level * 100)}")
        painter.setFont(self.small)
        painter.setPen(MUTED)
        painter.drawText(QRectF(center.x() - radius, center.y() + 24, radius * 2, 16), Qt.AlignCenter, "VOLUMEN")

    def _frame(self, painter, rect):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(2, 14, 24, 150))
        painter.drawRect(rect)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(79, 216, 255, 120), 1))
        painter.drawRect(rect)
        painter.setPen(QPen(CYAN, 2))
        corner = 12
        for x, y, dx, dy in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                             (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1)):
            painter.drawLine(QPointF(x, y), QPointF(x + dx * corner, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + dy * corner))

    def _draw_panel(self, painter):
        """Reloj y uso de la PC, arriba a la derecha."""
        rect = QRectF(self.width() - 264, 20, 240, 176)
        self._frame(painter, rect)
        now = datetime.now()
        painter.setPen(CYAN)
        painter.setFont(self.big)
        painter.drawText(QRectF(rect.left(), rect.top() + 8, rect.width(), 44), Qt.AlignCenter, now.strftime("%H:%M"))
        painter.setFont(self.small)
        painter.setPen(MUTED)
        painter.drawText(QRectF(rect.left(), rect.top() + 52, rect.width(), 16), Qt.AlignCenter, now.strftime("%d/%m/%Y"))
        gpu = self.stats.get("gpu")
        rows = [("CPU", self.stats.get("cpu")), ("RAM", self.stats.get("ram")),
                ("GPU" + (f" {gpu[1]}°C" if gpu else ""), gpu[0] if gpu else None)]
        for i, (label, value) in enumerate(rows):
            y = rect.top() + 84 + i * 28
            painter.setPen(MUTED)
            painter.drawText(QPointF(rect.left() + 14, y + 10), label)
            bar = QRectF(rect.left() + 100, y, 120, 10)
            painter.setPen(QPen(QColor(79, 216, 255, 90), 1))
            painter.drawRect(bar)
            if value is not None:
                painter.fillRect(QRectF(bar.left(), bar.top(), bar.width() * value / 100, bar.height()),
                                 AMBER if value >= 85 else CYAN)

    def _draw_message(self, painter):
        """Lo último que dijiste o respondió Jarvis, abajo en el centro."""
        if not self.message or time.monotonic() - self.message[2] > MESSAGE_SECONDS:
            return
        who, text, _ = self.message
        width = min(900, self.width() - 80)
        painter.setFont(self.font)
        bounds = painter.boundingRect(QRectF(0, 0, width - 32, 400), Qt.TextWordWrap, text)
        rect = QRectF((self.width() - width) / 2, self.height() - bounds.height() - 130, width, bounds.height() + 44)
        self._frame(painter, rect)
        painter.setFont(self.small)
        painter.setPen(MUTED)
        painter.drawText(QPointF(rect.left() + 16, rect.top() + 18), "TÚ" if who == "user" else "JARVIS")
        painter.setFont(self.font)
        painter.setPen(QColor(216, 243, 255))
        painter.drawText(QRectF(rect.left() + 16, rect.top() + 26, width - 32, bounds.height() + 10), Qt.TextWordWrap, text)


def main():
    app = QApplication(sys.argv)
    screen = app.primaryScreen()
    geometry = screen.geometry()
    ratio = screen.devicePixelRatio()
    mapper = Mapper(geometry.width(), geometry.height())
    background = Background(geometry, mapper)
    overlay = Overlay(geometry)
    background.show()
    overlay.show()
    # Los atajos se pulsan en otro hilo: así un Alt+Tab no frena la cámara.
    press = lambda combo: threading.Thread(target=tools.press_keys, args=(combo,), daemon=True).start()
    try:
        volume = Volume()
    except Exception as error:
        print(f"Sin control de volumen: {error}", flush=True)
        volume = None
    to_window = lambda p: (p[0] / ratio - geometry.x(), p[1] / ratio - geometry.y())
    flags = {}
    in_thread = lambda function: threading.Thread(target=function, daemon=True).start()
    solar, earth, effects, scanner = holoviz.SolarSystem(), holoviz.Earth(), holoviz.Effects(), holoviz.Scanner()
    audio = holoviz.AudioLevels()
    keyboard = holoviz.Keyboard(lambda text: in_thread(lambda: tools.type_text(text)),
                                lambda keys: in_thread(lambda: tools.press_keys(keys)))
    notes = holoviz.Notes(lambda note_id, x, y: call_server("POST", f"/api/notes/{note_id}/move", {"x": x, "y": y}),
                          lambda note_id: call_server("DELETE", f"/api/notes/{note_id}"))
    notes.size = (overlay.width(), overlay.height())
    keyboard.layout(overlay.width(), overlay.height())

    def open_menu_item(index):
        _, kind, target = holoviz.MENU_ITEMS[index]
        in_thread(lambda: tools.open_app(target) if kind == "app" else tools.open_url(target))

    engine = Engine(winctl.Windows(exclude={int(background.winId()), int(overlay.winId())}), winctl.Cursor(),
                    keys=press, work_area=winctl.work_area(), volume=volume,
                    ui=Floating(keyboard, notes, flags, to_window),
                    menu=(len(holoviz.MENU_ITEMS), open_menu_item))
    state = {"faces": [], "earth_faced": False, "earth_loading": False}

    def draw_extras(painter):
        width, height = overlay.width(), overlay.height()
        view = engine.globe
        if flags.get("solar"):
            solar.draw(painter, width, height, view)
        if flags.get("earth"):
            earth.draw(painter, width, height, view)
        if flags.get("visualizer"):
            holoviz.draw_visualizer(painter, width, height, audio.bands)
        if flags.get("notes"):
            notes.draw(painter)
        if flags.get("keyboard"):
            hover = to_window(engine.points[engine.primary]) if engine.primary in engine.points else None
            keyboard.draw(painter, hover)
        if engine.menu is not None:
            holoviz.draw_menu(painter, to_window(engine.menu["center"]), engine.menu["selected"])
        if flags.get("effects"):
            effects.draw(painter)
        if flags.get("scanner"):
            scanner.draw(painter, state["faces"])

    overlay.extras = draw_extras

    def keep_background():
        # Si algo lo minimizó o lo escondió (por ejemplo, Win+D), vuelve a mostrarse.
        if background.isMinimized() or not background.isVisible():
            background.showNormal()
        winctl.place_above_desktop(int(background.winId()))

    keep_at_bottom = QTimer()
    keep_at_bottom.timeout.connect(keep_background)
    keep_at_bottom.start(500)
    winctl.place_above_desktop(int(background.winId()))

    # Si Jarvis se cierra, el holograma se cierra con él y suelta la cámara.
    parent = int(os.environ.get("JARVIS_PARENT", "0"))
    watch_parent = QTimer()
    watch_parent.timeout.connect(lambda: parent and not psutil.pid_exists(parent) and app.quit())
    watch_parent.start(1000)

    stats = {"frames": 0, "since": time.monotonic()}

    def on_frame(image, hands, faces):
        now = time.monotonic()
        drawn, inputs = [], []
        for hand in hands:
            points = [mapper(x, y) for x, y in hand["points"]]
            pointer = pinch_point(points)
            physical = ((geometry.x() + pointer[0]) * ratio, (geometry.y() + pointer[1]) * ratio)
            inputs.append(HandInput(hand["id"], physical, pinch_ratio(points), hand_pose(points),
                                    middle_pinch_ratio(points), hand_angle(points)))
            drawn.append((hand["id"], points))
        engine.update(inputs, now)
        overlay.hands = []
        for hand_id, points in drawn:
            if hand_id in engine.points:
                x, y = engine.points[hand_id]
                pointer = (x / ratio - geometry.x(), y / ratio - geometry.y())
                pinch = "left" if engine.pinching.get(hand_id) else "right" if engine.right_pinching.get(hand_id) else ""
                overlay.hands.append((points, pointer, pinch))
        overlay.status = engine.status
        overlay.strokes = [[to_window(p) for p in stroke] for stroke in engine.strokes]
        overlay.globe = engine.globe if flags.get("globe") else None
        if engine.tap and flags.get("solar"):
            solar.tap(to_window(engine.tap[0]))
        engine.tap = None
        if flags.get("effects"):
            effects.update([(hand_id, points, engine.poses.get(hand_id, ("other", 0))[0]) for hand_id, points in drawn])
        if flags.get("scanner"):
            state["faces"] = []
            for face in faces:
                x, y, w, h = face["box"]
                left, top = mapper(x, y)
                right, bottom = mapper(x + w, y + h)
                state["faces"].append({"rect": QRectF(left, top, right - left, bottom - top),
                                       "name": face["name"], "known": face["known"]})
        overlay.knob = (to_window(engine.knob[0]), engine.knob[1]) if engine.knob else None
        background.image = image
        background.update()
        overlay.update()
        stats["frames"] += 1
        if now - stats["since"] >= 10:
            print(f"fps={stats['frames'] / (now - stats['since']):.1f}", flush=True)
            stats["frames"], stats["since"] = 0, now

    def on_failure(message):
        print(f"ERROR {message}", flush=True)
        app.exit(1)

    def on_feed(data):
        overlay.stats = data
        if data["notes"] is not None:
            notes.update_from_server(data["notes"])
        if data["modes"] is not None:
            modes = data["modes"]
            flags.clear()
            flags.update(modes)
            engine.draw_mode = modes.get("draw", False)
            engine.globe_mode = any(modes.get(name) for name in ("globe", "solar", "earth"))
            engine.effects_mode = modes.get("effects", False)
            tracker.scan = modes.get("scanner", False)
            if not engine.draw_mode:
                engine.strokes = []
            if modes.get("visualizer") and not audio.running:
                in_thread(audio.run)
            elif not modes.get("visualizer"):
                audio.running = False
            if modes.get("earth"):
                if not state["earth_loading"]:
                    state["earth_loading"] = True
                    in_thread(earth.load)
                earth.want_cities(modes.get("earth_cities", []), in_thread)
                engine.globe["idle"] = 0.03  # la Tierra gira despacio, para poder leerla
                if earth.home and not state["earth_faced"]:
                    engine.globe["yaw"], engine.globe["pitch"] = holoviz.face_view(earth.home["lat"], earth.home["lon"])
                    engine.globe["spin"] = 0.0
                    state["earth_faced"] = True
            else:
                engine.globe.pop("idle", None)
                state["earth_faced"] = False
        for who, text in data["messages"]:
            overlay.message = (who, text, time.monotonic())
        overlay.update()

    feed = Feed()
    feed.updated.connect(on_feed)
    feed.start()

    tracker = Tracker()
    tracker.frame_ready.connect(on_frame)
    tracker.failed.connect(on_failure)
    tracker.start()
    code = app.exec()
    tracker.requestInterruption()
    feed.requestInterruption()
    tracker.wait(3000)
    feed.wait(3000)
    sys.exit(code)


if __name__ == "__main__":
    main()
