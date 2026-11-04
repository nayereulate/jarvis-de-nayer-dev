"""Jarvis en el escritorio: el orbe flotante, la animación de arranque y los subtítulos grandes.

Corre como proceso aparte (python -m jarvis.desktop) y pregunta al servidor qué está pasando.
"""
import json
import math
import os
import random
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

import psutil
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / "data" / "token.txt"
SERVER = os.environ.get("JARVIS_URL", "http://127.0.0.1:8765")
ORB_SIZE = 168
SUBTITLE_SECONDS = 9
BOOT_SECONDS = 5.2

CYAN = QColor(79, 216, 255)
AMBER = QColor(255, 181, 71)
RED = QColor(255, 77, 94)
GREEN = QColor(90, 255, 180)
GRAY = QColor(111, 157, 179)
WHITE = QColor(239, 252, 255)
STATES = {
    # estado de la escucha: (color, texto, velocidad de giro)
    "wake": (CYAN, "EN LÍNEA", 1.0),
    "listening": (WHITE, "ESCUCHANDO", 1.6),
    "thinking": (AMBER, "PROCESANDO", 3.2),
    "speaking": (CYAN, "HABLANDO", 1.4),
    "dictating": (GREEN, "DICTADO", 1.0),
    "paused": (GRAY, "EN PAUSA", 0.3),
    "error": (RED, "ERROR", 0.5),
    "off": (GRAY, "INICIANDO", 0.6),
}


def faded(color: QColor, alpha: float) -> QColor:
    return QColor(color.red(), color.green(), color.blue(), max(0, min(255, int(alpha))))


class Feed(QThread):
    """Pregunta al servidor el estado de Jarvis cuatro veces por segundo."""

    updated = Signal(dict)

    def run(self):
        token = TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else ""
        after = -1
        while not self.isInterruptionRequested():
            try:
                request = urllib.request.Request(f"{SERVER}/api/events?after={after}",
                                                 headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.load(response)
                after = data["last"]
                data["online"] = True
            except Exception:
                data = {"online": False, "events": []}
            self.updated.emit(data)
            self.msleep(250)


class Orb(QWidget):
    """El orbe de la esquina. Se puede arrastrar; doble clic abre la página de Jarvis."""

    def __init__(self, screen_rect):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(ORB_SIZE, ORB_SIZE + 22)
        self.move(screen_rect.right() - ORB_SIZE - 24, screen_rect.bottom() - ORB_SIZE - 70)
        self.state = "off"
        self.online = False
        self.recording = False
        self.level = 0.0
        self.angle = 0.0
        self.ripples = []
        self.drag_from = None
        self.font = QFont("Consolas", 8)
        self.font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        self.opacity_in = 0.0  # aparece suave después del arranque

    def set_state(self, state, online, recording):
        if state == "listening" and self.state != "listening":
            self.ripples.append(0.0)
        self.state, self.online, self.recording = state, online, recording

    def tick(self, dt):
        color, _, speed = STATES.get(self.state, STATES["wake"])
        self.angle = (self.angle + dt * 40 * speed) % 360
        if self.state == "speaking":
            target = 0.35 + 0.65 * abs(math.sin(time.monotonic() * 9)) * random.uniform(0.5, 1)
        elif self.state == "listening":
            target = 0.25 + 0.15 * math.sin(time.monotonic() * 5)
            if not self.ripples or self.ripples[-1] > 0.45:
                self.ripples.append(0.0)
        else:
            target = 0.0
        self.level += (target - self.level) * min(1, dt * 12)
        self.ripples = [r + dt * 0.8 for r in self.ripples if r < 1]
        if self.isVisible():
            self.opacity_in = min(1.0, self.opacity_in + dt * 1.5)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self.opacity_in * (1.0 if self.online else 0.45))
        color, label, _ = STATES.get(self.state, STATES["wake"]) if self.online else (GRAY, "SIN CONEXIÓN", 0.3)
        center = QPointF(ORB_SIZE / 2, ORB_SIZE / 2)
        radius = ORB_SIZE * 0.24

        glow = QRadialGradient(center, ORB_SIZE / 2)
        glow.setColorAt(0, faded(color, 90 + 120 * self.level))
        glow.setColorAt(0.45, faded(color, 30 + 40 * self.level))
        glow.setColorAt(1, faded(color, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, ORB_SIZE / 2, ORB_SIZE / 2)

        for ripple in self.ripples:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(faded(color, 200 * (1 - ripple)), 1.5))
            r = radius + ripple * ORB_SIZE * 0.3
            painter.drawEllipse(center, r, r)

        painter.save()
        painter.translate(center)
        for ring, (size, width, dash, sign) in enumerate(((1.75, 1.2, [2, 4], 1), (1.5, 3, [10, 4, 3, 4], -1),
                                                          (1.25, 1.5, [24, 8], 1))):
            painter.rotate(self.angle * sign * (1 + ring * 0.4))
            pen = QPen(faded(color, 170), width)
            pen.setDashPattern(dash)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            r = radius * size
            painter.drawEllipse(QPointF(0, 0), r, r)
        painter.restore()

        if self.state == "thinking" and self.online:
            painter.setPen(QPen(AMBER, 3, Qt.SolidLine, Qt.RoundCap))
            box = QRectF(center.x() - radius * 1.1, center.y() - radius * 1.1, radius * 2.2, radius * 2.2)
            painter.drawArc(box, int(-self.angle * 16 * 3), 90 * 16)

        core = radius * (0.62 + 0.38 * self.level)
        body = QRadialGradient(center, core * 1.6)
        body.setColorAt(0, WHITE)
        body.setColorAt(0.35, faded(color, 230))
        body.setColorAt(1, faded(color, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(body)
        painter.drawEllipse(center, core * 1.6, core * 1.6)
        painter.setBrush(WHITE)
        painter.drawEllipse(center, core * 0.42, core * 0.42)

        if self.recording and int(time.monotonic() * 2) % 2 == 0:
            painter.setBrush(RED)
            painter.drawEllipse(QPointF(ORB_SIZE - 20, 18), 6, 6)
            painter.setPen(RED)
            painter.setFont(self.font)
            painter.drawText(QPointF(ORB_SIZE - 50, 22), "REC")

        painter.setFont(self.font)
        painter.setPen(faded(color, 230))
        painter.drawText(QRectF(0, ORB_SIZE - 4, ORB_SIZE, 22), Qt.AlignCenter, label)

    def mousePressEvent(self, event):
        self.drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_from is not None:
            self.move(event.globalPosition().toPoint() - self.drag_from)

    def mouseReleaseEvent(self, event):
        self.drag_from = None

    def mouseDoubleClickEvent(self, event):
        webbrowser.open(SERVER)


class Subtitles(QWidget):
    """Modo presentación: lo que dices y lo que responde Jarvis, en grande abajo de la pantalla."""

    def __init__(self, screen_rect):
        flags = (Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                 | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        height = 260
        self.setGeometry(screen_rect.left(), screen_rect.bottom() - height - 30, screen_rect.width(), height)
        self.lines = []  # (quién, texto, cuándo)
        self.big = QFont("Segoe UI", 26, QFont.DemiBold)
        self.small = QFont("Consolas", 11)
        self.small.setLetterSpacing(QFont.AbsoluteSpacing, 3)

    def add(self, who, text):
        self.lines = (self.lines + [(who, text, time.monotonic())])[-2:]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        now = time.monotonic()
        visible = [line for line in self.lines if now - line[2] < SUBTITLE_SECONDS]
        y = self.height()
        width = min(1500, self.width() - 160)
        for who, text, when in reversed(visible):
            fade = min(1.0, (SUBTITLE_SECONDS - (now - when)) / 1.5, (now - when) * 4)
            painter.setFont(self.big)
            bounds = painter.boundingRect(QRectF(0, 0, width - 48, 1000), Qt.TextWordWrap | Qt.AlignHCenter, text)
            box = QRectF((self.width() - width) / 2, y - bounds.height() - 52, width, bounds.height() + 44)
            if box.top() < 0:
                break
            painter.setOpacity(fade)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(2, 10, 18, 205))
            painter.drawRoundedRect(box, 6, 6)
            accent = CYAN if who == "jarvis" else AMBER
            painter.setBrush(accent)
            painter.drawRect(QRectF(box.left(), box.top(), 4, box.height()))
            painter.setFont(self.small)
            painter.setPen(accent)
            painter.drawText(QRectF(box.left() + 24, box.top() + 6, 200, 18), Qt.AlignLeft,
                             "JARVIS" if who == "jarvis" else "TÚ")
            painter.setFont(self.big)
            painter.setPen(WHITE)
            painter.drawText(QRectF(box.left() + 24, box.top() + 24, width - 48, bounds.height() + 10),
                             Qt.TextWordWrap | Qt.AlignHCenter, text)
            y = box.top() - 10


class Boot(QWidget):
    """La animación de arranque a pantalla completa."""

    MODULES = ["NÚCLEO", "VOZ", "OÍDO", "VISIÓN", "MANOS", "RED", "MEMORIA"]

    def __init__(self, screen_rect):
        flags = (Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                 | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(screen_rect)
        self.started = time.monotonic()
        self.title = QFont("Consolas", 34)
        self.title.setLetterSpacing(QFont.AbsoluteSpacing, 18)
        self.small = QFont("Consolas", 11)
        self.small.setLetterSpacing(QFont.AbsoluteSpacing, 3)

    def progress(self) -> float:
        return (time.monotonic() - self.started) / BOOT_SECONDS

    def paintEvent(self, event):
        t = self.progress()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fade = min(1.0, t * 5, (1 - t) * 6)
        painter.setOpacity(max(0.0, fade))
        center = QPointF(self.width() / 2, self.height() / 2)
        size = min(self.width(), self.height())

        backdrop = QRadialGradient(center, size * 0.9)
        backdrop.setColorAt(0, QColor(6, 30, 46, 235))
        backdrop.setColorAt(1, QColor(1, 5, 10, 250))
        painter.fillRect(self.rect(), backdrop)

        # Anillos que se abren desde el centro y giran.
        painter.save()
        painter.translate(center)
        for i in range(6):
            grow = min(1.0, max(0.0, (t - i * 0.06) * 2.2))
            radius = size * (0.08 + i * 0.045) * (0.3 + 0.7 * (1 - (1 - grow) ** 3))
            painter.rotate((t * 160 + i * 47) * (1 if i % 2 else -1))
            pen = QPen(faded(CYAN, 210 * grow), 2 if i % 2 else 6)
            pen.setDashPattern([3, 5] if i % 3 == 0 else [30, 10, 6, 10])
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius, radius)
        painter.restore()

        core = QRadialGradient(center, size * 0.07)
        core.setColorAt(0, WHITE)
        core.setColorAt(0.4, faded(CYAN, 220))
        core.setColorAt(1, faded(CYAN, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(core)
        pulse = 1 + 0.08 * math.sin(t * 20)
        painter.drawEllipse(center, size * 0.07 * pulse, size * 0.07 * pulse)

        # Línea de escaneo.
        scan_y = (t * 1.6 % 1) * self.height()
        painter.fillRect(QRectF(0, scan_y, self.width(), 2), faded(CYAN, 70))

        # Título que se escribe solo.
        title = "J.A.R.V.I.S."
        shown = title[:max(0, int((t - 0.1) * 40))]
        painter.setFont(self.title)
        painter.setPen(CYAN)
        painter.drawText(QRectF(0, center.y() + size * 0.3, self.width(), 50), Qt.AlignCenter, shown)

        # Módulos que se van cargando.
        painter.setFont(self.small)
        done = int(max(0.0, t - 0.25) / 0.5 * len(self.MODULES) / 1.2)
        x = self.width() * 0.08
        y = self.height() * 0.3
        for i, name in enumerate(self.MODULES):
            ready = i < done
            painter.setPen(faded(CYAN if ready else GRAY, 230 if ready else 120))
            painter.drawText(QPointF(x, y + i * 28), f"{'■' if ready else '□'} {name:<9} {'EN LÍNEA' if ready else '...'}")
        bar = QRectF(self.width() * 0.3, center.y() + size * 0.3 + 70, self.width() * 0.4, 4)
        painter.fillRect(bar, faded(CYAN, 50))
        painter.fillRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, t / 0.8), bar.height()), CYAN)
        message = "TODOS LOS SISTEMAS EN LÍNEA" if t > 0.8 else "INICIANDO SISTEMAS"
        painter.setPen(WHITE if t > 0.8 else GRAY)
        painter.drawText(QRectF(0, bar.bottom() + 14, self.width(), 24), Qt.AlignCenter, message)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    screen = app.primaryScreen()
    orb = Orb(screen.availableGeometry())
    subtitles = Subtitles(screen.availableGeometry())
    boot = Boot(screen.geometry()) if os.environ.get("JARVIS_BOOT") == "1" else None
    if boot:
        boot.show()
        QTimer.singleShot(int(BOOT_SECONDS * 1000) - 300, orb.show)
    else:
        orb.show()

    status = {"subtitles": False, "hologram": False}

    def on_feed(data):
        if data.get("online"):
            listener = data["listener"]
            state = "dictating" if listener.get("dictation") else (listener["state"] if listener["enabled"] else "paused")
            orb.set_state(state, True, data.get("recording", {}).get("recording", False))
            status["subtitles"] = data.get("modes", {}).get("subtitles", False)
            status["hologram"] = data.get("hologram", False)
            for event in data["events"]:
                if event["type"] in ("user", "jarvis") and event.get("text"):
                    subtitles.add(event["type"], event["text"])
        else:
            orb.set_state(orb.state, False, False)
        # El holograma ya muestra lo que se dice: no se repite encima.
        show = status["subtitles"] and not status["hologram"]
        if show != subtitles.isVisible():
            subtitles.setVisible(show)

    feed = Feed()
    feed.updated.connect(on_feed)
    feed.start()

    last = {"t": time.monotonic()}

    def animate():
        now = time.monotonic()
        dt, last["t"] = now - last["t"], now
        orb.tick(dt)
        if subtitles.isVisible():
            subtitles.update()
        if boot is not None and boot.isVisible():
            if boot.progress() >= 1:
                boot.hide()
            else:
                boot.update()

    timer = QTimer()
    timer.timeout.connect(animate)
    timer.start(16)

    # Si Jarvis se cierra, el orbe se va con él.
    parent = int(os.environ.get("JARVIS_PARENT", "0"))
    watch_parent = QTimer()
    watch_parent.timeout.connect(lambda: parent and not psutil.pid_exists(parent) and app.quit())
    watch_parent.start(1000)

    print("LISTO", flush=True)
    code = app.exec()
    feed.requestInterruption()
    feed.wait(3000)
    sys.exit(code)


if __name__ == "__main__":
    main()
