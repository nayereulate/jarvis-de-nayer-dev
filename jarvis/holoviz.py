"""Los hologramas que se dibujan sobre la pantalla: esfera, sistema solar, globo terráqueo,
teclado, notas, menú radial, partículas, bola de energía, escáner de identidad y visualizador.

Solo dibuja y guarda estado visual; los gestos los decide gestures.Engine.
"""
import json
import math
import random
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient

from .paths import MODELS_DIR

CYAN = QColor(79, 216, 255)
AMBER = QColor(255, 181, 71)
RED = QColor(255, 77, 94)
GREEN = QColor(90, 255, 180)
WHITE = QColor(239, 252, 255)
MUTED = QColor(111, 157, 179)
VIOLET_SOFT = QColor(190, 150, 255)
PANEL = QColor(2, 14, 24, 190)
# Tipografía técnica (Bahnschrift viene con Windows); el espaciado da el aire de interfaz futurista.
FONT = QFont("Bahnschrift", 11)
SMALL = QFont("Bahnschrift", 9)
SMALL.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
BIG = QFont("Bahnschrift", 18)


def faded(color: QColor, alpha: float) -> QColor:
    return QColor(color.red(), color.green(), color.blue(), max(0, min(255, int(alpha))))


def rotate(point, yaw, pitch):
    x, y, z = point
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


def hud_frame(painter: QPainter, rect: QRectF, accent: QColor = CYAN) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(PANEL)
    painter.drawRect(rect)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(faded(accent, 120), 1))
    painter.drawRect(rect)
    painter.setPen(QPen(accent, 2))
    corner = 12
    for x, y, dx, dy in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                         (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1)):
        painter.drawLine(QPointF(x, y), QPointF(x + dx * corner, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + dy * corner))


# ---------------------------------------------------------------- Sistema solar

PLANETS = [
    # nombre, color, tamaño en pantalla, distancia al Sol, diámetro, lunas, día, año
    ("Mercurio", QColor(190, 185, 180), 4, "58 millones de km", "4.879 km", "0", "59 días", "88 días"),
    ("Venus", QColor(235, 200, 130), 7, "108 millones de km", "12.104 km", "0", "243 días", "225 días"),
    ("Tierra", QColor(80, 160, 255), 7, "150 millones de km", "12.742 km", "1", "24 horas", "365 días"),
    ("Marte", QColor(235, 105, 70), 5, "228 millones de km", "6.779 km", "2", "24,6 horas", "687 días"),
    ("Júpiter", QColor(225, 175, 125), 15, "778 millones de km", "139.820 km", "más de 90", "9,9 horas", "11,9 años"),
    ("Saturno", QColor(235, 215, 155), 13, "1.432 millones de km", "116.460 km", "más de 270", "10,7 horas", "29,4 años"),
    ("Urano", QColor(155, 230, 240), 10, "2.867 millones de km", "50.724 km", "28", "17,2 horas", "84 años"),
    ("Neptuno", QColor(95, 125, 255), 10, "4.515 millones de km", "49.244 km", "16", "16,1 horas", "165 años"),
]


class SolarSystem:
    def __init__(self):
        self.start = time.monotonic()
        self.selected = None
        self.selected_at = 0.0
        self.projected = []  # (índice, punto en pantalla, radio) del último dibujo

    def tap(self, point) -> None:
        """Un toque cerca de un planeta lo elige; lejos de todos, cierra su ficha."""
        best = min(self.projected, key=lambda p: math.dist(p[1], point), default=None)
        if best and math.dist(best[1], point) <= best[2] + 40:
            self.selected, self.selected_at = best[0], time.monotonic()
        else:
            self.selected = None

    def draw(self, painter: QPainter, width: int, height: int, view: dict) -> None:
        center = QPointF(width / 2, height / 2)
        scale = min(width, height) / 900 * view["scale"]
        t = time.monotonic() - self.start
        yaw, pitch = view["yaw"] * 0.3, 0.45 + view["pitch"] * 0.5

        def project(p):
            x, y, z = rotate(p, yaw, pitch)
            return QPointF(center.x() + x * scale, center.y() - y * scale), z

        # Órbitas.
        for i, _ in enumerate(PLANETS):
            radius = 70 + i * 48
            path = QPainterPath()
            for step in range(0, 361, 6):
                a = math.radians(step)
                point, _ = project((radius * math.cos(a), 0, radius * math.sin(a)))
                path.moveTo(point) if step == 0 else path.lineTo(point)
            painter.setPen(QPen(faded(CYAN, 70 if self.selected != i else 200), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        bodies = []
        for i, planet in enumerate(PLANETS):
            radius = 70 + i * 48
            angle = i * 1.7 + t * 1.2 / (i + 1) ** 1.3
            point, depth = project((radius * math.cos(angle), 0, radius * math.sin(angle)))
            bodies.append((depth, i, point))
        bodies.append((0.0, None, center))
        self.projected = []
        for depth, i, point in sorted(bodies, key=lambda b: -b[0]):
            if i is None:
                sun = QRadialGradient(point, 46 * scale)
                sun.setColorAt(0, WHITE)
                sun.setColorAt(0.3, QColor(255, 210, 90))
                sun.setColorAt(1, QColor(255, 150, 40, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(sun)
                painter.drawEllipse(point, 46 * scale, 46 * scale)
                continue
            name, color, size = PLANETS[i][:3]
            size *= scale * (1 + depth / 900)
            glow = QRadialGradient(point, size * 2.2)
            glow.setColorAt(0, faded(color, 255))
            glow.setColorAt(0.45, faded(color, 220))
            glow.setColorAt(1, faded(color, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(point, size * 2.2, size * 2.2)
            if name == "Saturno":
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(faded(color, 200), 2))
                painter.drawEllipse(point, size * 2.4, size * 0.8)
            if self.selected == i:
                painter.setPen(QPen(AMBER, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(point, size * 2.2 + 8, size * 2.2 + 8)
            self.projected.append((i, (point.x(), point.y()), size * 2.2))
        if self.selected is not None:
            self._draw_card(painter, width)
        painter.setFont(SMALL)
        painter.setPen(MUTED)
        painter.drawText(QRectF(0, height - 70, width, 20), Qt.AlignCenter,
                         "SISTEMA SOLAR · PELLIZCA Y ARRASTRA PARA GIRAR · PELLIZCO RÁPIDO SOBRE UN PLANETA PARA VER SUS DATOS")

    def _draw_card(self, painter, width):
        name, color, _, distance, diameter, moons, day, year = PLANETS[self.selected]
        rect = QRectF(width - 380, 230, 340, 200)
        hud_frame(painter, rect, color)
        painter.setFont(BIG)
        painter.setPen(color)
        painter.drawText(QPointF(rect.left() + 18, rect.top() + 36), name.upper())
        painter.setFont(FONT)
        rows = [("Distancia al Sol", distance), ("Diámetro", diameter), ("Lunas", moons), ("Día", day), ("Año", year)]
        for j, (label, value) in enumerate(rows):
            y = rect.top() + 66 + j * 26
            painter.setPen(MUTED)
            painter.drawText(QPointF(rect.left() + 18, y), label)
            painter.setPen(WHITE)
            painter.drawText(QRectF(rect.left() + 150, y - 15, 175, 20), Qt.AlignRight, value)


# ---------------------------------------------------------------- Globo terráqueo

COASTLINE = MODELS_DIR / "ne_110m_land.geojson"
COASTLINE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"


def earth_point(lat, lon):
    """Este a la derecha y el norte arriba cuando se mira la cara de adelante."""
    lat, lon = math.radians(lat), math.radians(lon)
    return math.cos(lat) * math.cos(lon), math.sin(lat), -math.cos(lat) * math.sin(lon)


def face_view(lat, lon) -> tuple[float, float]:
    """El giro (yaw, pitch) que deja el punto (lat, lon) mirando de frente."""
    return -math.pi / 2 - math.radians(lon), math.radians(lat)


def subsolar_point(now: datetime) -> tuple[float, float]:
    """Dónde está el Sol justo encima, aproximado: suficiente para dibujar el día y la noche."""
    day = now.timetuple().tm_yday
    declination = -23.44 * math.cos(math.radians(360 / 365 * (day + 10)))
    hours = now.hour + now.minute / 60 + now.second / 3600
    return declination, (12 - hours) * 15


def weather_for(place: str = "") -> dict | None:
    """Clima y coordenadas de wttr.in. Sin lugar, la ubicación aproximada de la conexión."""
    try:
        request = urllib.request.Request(f"https://wttr.in/{urllib.request.quote(place)}?format=j1&lang=es",
                                         headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(request, timeout=6) as response:
            data = json.load(response)
        area = data["nearest_area"][0]
        current = data["current_condition"][0]
        return {"name": place or area["areaName"][0]["value"], "lat": float(area["latitude"]),
                "lon": float(area["longitude"]), "temp": current["temp_C"],
                "sky": (current.get("lang_es") or current["weatherDesc"])[0]["value"].strip()}
    except Exception:
        return None


class Earth:
    def __init__(self):
        self.coasts = []  # listas de puntos 3D
        self.home = None
        self.cities = {}  # nombre: datos de weather_for
        self.loading = set()

    def load(self) -> None:
        """Se llama en un hilo aparte: baja la costa y busca dónde estás."""
        if not COASTLINE.exists():
            MODELS_DIR.mkdir(exist_ok=True)
            urllib.request.urlretrieve(COASTLINE_URL, COASTLINE)
        data = json.loads(COASTLINE.read_text(encoding="utf-8"))
        coasts = []
        for feature in data["features"]:
            geometry = feature["geometry"]
            polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
            for polygon in polygons:
                for ring in polygon:
                    coasts.append([earth_point(lat, lon) for lon, lat in ring[::2]])
        self.coasts = coasts
        self.home = weather_for("")

    def want_cities(self, names: list[str], spawn) -> None:
        for name in names:
            if name not in self.cities and name not in self.loading:
                self.loading.add(name)
                spawn(lambda name=name: self.cities.__setitem__(name, weather_for(name)))

    def draw(self, painter: QPainter, width: int, height: int, view: dict) -> None:
        center = QPointF(width / 2, height / 2)
        radius = min(width, height) * 0.27 * view["scale"]
        yaw, pitch = view["yaw"], view["pitch"]
        project = lambda p: QPointF(center.x() + p[0] * radius, center.y() - p[1] * radius)

        ocean = QRadialGradient(center, radius * 1.15)
        ocean.setColorAt(0, QColor(10, 50, 80, 150))
        ocean.setColorAt(0.85, QColor(5, 30, 55, 120))
        ocean.setColorAt(1, QColor(79, 216, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(ocean)
        painter.drawEllipse(center, radius * 1.15, radius * 1.15)

        # Noche: una malla de puntos tenues en el lado oscuro.
        sun_lat, sun_lon = subsolar_point(datetime.now(timezone.utc))
        sun = earth_point(sun_lat, sun_lon)
        for lat in range(-80, 81, 8):
            for lon in range(-180, 180, 8):
                p = earth_point(lat, lon)
                if p[0] * sun[0] + p[1] * sun[1] + p[2] * sun[2] < 0:
                    x, y, z = rotate(p, yaw, pitch)
                    if z > 0:
                        painter.setBrush(QColor(20, 40, 120, 120))
                        painter.drawEllipse(project((x, y, z)), 2.2, 2.2)

        for line in self.coasts:
            turned = [rotate(p, yaw, pitch) for p in line]
            for a, b in zip(turned, turned[1:]):
                front = a[2] > 0 and b[2] > 0
                if not front and (a[2] < -0.2 and b[2] < -0.2):
                    continue
                painter.setPen(QPen(faded(CYAN, 220 if front else 35), 1.6 if front else 1))
                painter.drawLine(project(a), project(b))
        if not self.coasts:
            painter.setFont(FONT)
            painter.setPen(MUTED)
            painter.drawText(QRectF(center.x() - 200, center.y() - 10, 400, 20), Qt.AlignCenter, "CARGANDO CONTINENTES…")

        places = ([("home", self.home)] if self.home else []) + [(n, c) for n, c in self.cities.items() if c]
        for kind, place in places:
            x, y, z = rotate(earth_point(place["lat"], place["lon"]), yaw, pitch)
            if z <= 0:
                continue
            point = project((x, y, z))
            color = AMBER if kind == "home" else GREEN
            pulse = 6 + 3 * math.sin(time.monotonic() * 4)
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(point, pulse, pulse)
            painter.setBrush(color)
            painter.drawEllipse(point, 3, 3)
            label = f"{place['name']} · {place['temp']}°C · {place['sky']}"
            painter.setFont(SMALL)
            box = QRectF(point.x() + 14, point.y() - 12, painter.fontMetrics().horizontalAdvance(label) + 16, 22)
            painter.setPen(Qt.NoPen)
            painter.setBrush(PANEL)
            painter.drawRect(box)
            painter.setPen(color)
            painter.drawText(box, Qt.AlignCenter, label)
        painter.setFont(SMALL)
        painter.setPen(MUTED)
        painter.drawText(QRectF(0, center.y() + radius * 1.2 + 10, width, 20), Qt.AlignCenter,
                         f"GLOBO TERRÁQUEO · {datetime.now():%H:%M} · PELLIZCA PARA GIRAR · PIDE EL CLIMA DE UNA CIUDAD")


# ---------------------------------------------------------------- Teclado

ROWS = [list("1234567890"), list("qwertyuiop"), list("asdfghjklñ"), ["SHIFT", *"zxcvbnm,.", "BACK"], ["SPACE", "ENTER"]]
KEY_LABELS = {"SPACE": "ESPACIO", "ENTER": "ENTER", "BACK": "BORRAR", "SHIFT": "MAYÚS"}


class Keyboard:
    def __init__(self, type_text, press_keys):
        self.type_text, self.press_keys = type_text, press_keys
        self.shift = False
        self.keys = []  # (rect en ventana, tecla)
        self.flash = {}  # tecla: cuándo se pulsó

    def layout(self, width: int, height: int) -> None:
        key_w = min(70, width * 0.6 / 11)
        key_h = key_w * 0.85
        total_w = key_w * 11
        left, top = (width - total_w) / 2, height - key_h * 5 - 150
        self.keys = []
        for r, row in enumerate(ROWS):
            if row == ["SPACE", "ENTER"]:
                self.keys.append((QRectF(left + key_w * 2, top + r * key_h, key_w * 6.5, key_h - 6), "SPACE"))
                self.keys.append((QRectF(left + key_w * 8.7, top + r * key_h, key_w * 2.3, key_h - 6), "ENTER"))
                continue
            offset = (11 - len(row)) * key_w / 2
            for c, key in enumerate(row):
                self.keys.append((QRectF(left + offset + c * key_w, top + r * key_h, key_w - 6, key_h - 6), key))

    def hit(self, point):
        for rect, key in self.keys:
            if rect.contains(QPointF(*point)):
                return key
        return None

    def press(self, key) -> None:
        self.flash[key] = time.monotonic()
        if key == "SHIFT":
            self.shift = not self.shift
        elif key == "BACK":
            self.press_keys("backspace")
        elif key == "ENTER":
            self.press_keys("enter")
        elif key == "SPACE":
            self.type_text(" ")
        else:
            self.type_text(key.upper() if self.shift else key)
            self.shift = False

    def draw(self, painter: QPainter, hover) -> None:
        if not self.keys:
            return
        area = self.keys[0][0].united(self.keys[-1][0]).adjusted(-16, -16, 16, 16)
        area.setLeft(min(rect.left() for rect, _ in self.keys) - 16)
        area.setRight(max(rect.right() for rect, _ in self.keys) + 16)
        hud_frame(painter, area)
        now = time.monotonic()
        for rect, key in self.keys:
            hot = hover is not None and rect.contains(QPointF(*hover))
            pressed = now - self.flash.get(key, 0) < 0.18 or (key == "SHIFT" and self.shift)
            painter.setPen(QPen(faded(CYAN, 230 if hot else 110), 1.5))
            painter.setBrush(faded(CYAN, 150 if pressed else 55 if hot else 18))
            painter.drawRoundedRect(rect, 4, 4)
            label = KEY_LABELS.get(key, key.upper() if self.shift else key)
            painter.setFont(FONT)
            painter.setPen(WHITE)
            painter.drawText(rect, Qt.AlignCenter, label)


# ---------------------------------------------------------------- Notas adhesivas

NOTE_W, NOTE_H = 250, 160


class Notes:
    def __init__(self, move, delete):
        """move(id, x, y) y delete(id) avisan al servidor (posiciones de 0 a 1)."""
        self.move, self.delete = move, delete
        self.items = []
        self.dragging = None  # (id, desplazamiento del agarre)
        self.size = (1, 1)

    def update_from_server(self, items: list[dict]) -> None:
        local = {item["id"]: item for item in self.items}
        merged = []
        for item in items:
            if self.dragging and item["id"] == self.dragging[0] and item["id"] in local:
                merged.append(local[item["id"]])  # mientras la arrastras manda tu mano
            else:
                merged.append(dict(item))
        self.items = merged

    def rect(self, item) -> QRectF:
        return QRectF(item["x"] * self.size[0], item["y"] * self.size[1], NOTE_W, NOTE_H)

    def hit(self, point):
        for item in reversed(self.items):
            if self.rect(item).contains(QPointF(*point)):
                return item["id"]
        return None

    def press(self, note_id, point) -> None:
        item = next(i for i in self.items if i["id"] == note_id)
        rect = self.rect(item)
        self.dragging = (note_id, (point[0] - rect.left(), point[1] - rect.top()))
        self.items.remove(item)
        self.items.append(item)  # al frente

    def drag(self, note_id, point) -> None:
        item = next((i for i in self.items if i["id"] == note_id), None)
        if item and self.dragging:
            dx, dy = self.dragging[1]
            item["x"] = (point[0] - dx) / self.size[0]
            item["y"] = (point[1] - dy) / self.size[1]

    def release(self, note_id) -> None:
        item = next((i for i in self.items if i["id"] == note_id), None)
        self.dragging = None
        if item:
            self.move(note_id, item["x"], item["y"])

    def erase_at(self, point) -> bool:
        note_id = self.hit(point)
        if note_id is None:
            return False
        self.items = [i for i in self.items if i["id"] != note_id]
        self.delete(note_id)
        return True

    def draw(self, painter: QPainter) -> None:
        for item in self.items:
            rect = self.rect(item)
            color = QColor(item.get("color", "#ffd166"))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(4, 16, 26, 215))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setBrush(faded(color, 230))
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width(), 8), 3, 3)
            painter.setPen(QPen(faded(color, 160), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setFont(QFont("Segoe UI", 12))
            painter.setPen(WHITE)
            painter.drawText(rect.adjusted(14, 18, -14, -12), Qt.TextWordWrap, item["text"])


# ---------------------------------------------------------------- Menú radial

MENU_ITEMS = [("Chrome", "app", "chrome"), ("YouTube", "url", "https://www.youtube.com"),
              ("Explorador", "app", "explorador"), ("Bloc de notas", "app", "notepad"),
              ("Calculadora", "app", "calculadora"), ("Tareas", "app", "administrador_tareas"),
              ("Jarvis", "url", "http://127.0.0.1:8765")]


def draw_menu(painter: QPainter, center, selected) -> None:
    count = len(MENU_ITEMS)
    inner, outer = 75, 190
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(2, 14, 24, 150))
    painter.drawEllipse(QPointF(*center), outer + 10, outer + 10)
    for i, (label, _, _) in enumerate(MENU_ITEMS):
        # La opción 0 está arriba y siguen en sentido horario (igual que en Engine).
        start = 90 - (i * 360 / count) + 180 / count
        path = QPainterPath()
        box_outer = QRectF(center[0] - outer, center[1] - outer, outer * 2, outer * 2)
        box_inner = QRectF(center[0] - inner, center[1] - inner, inner * 2, inner * 2)
        path.arcMoveTo(box_outer, start)
        path.arcTo(box_outer, start, -360 / count + 2)
        path.arcTo(box_inner, start - 360 / count + 2, 360 / count - 2)
        path.closeSubpath()
        hot = selected == i
        painter.setPen(QPen(faded(AMBER if hot else CYAN, 230 if hot else 120), 1.5))
        painter.setBrush(faded(AMBER if hot else CYAN, 90 if hot else 25))
        painter.drawPath(path)
        middle = math.radians(start - 180 / count)
        text_point = QPointF(center[0] + math.cos(middle) * (inner + outer) / 2,
                             center[1] - math.sin(middle) * (inner + outer) / 2)
        painter.setFont(FONT)
        painter.setPen(WHITE)
        painter.drawText(QRectF(text_point.x() - 60, text_point.y() - 10, 120, 20), Qt.AlignCenter, label)
    painter.setFont(SMALL)
    painter.setPen(MUTED)
    painter.drawText(QRectF(center[0] - 60, center[1] - 8, 120, 16), Qt.AlignCenter, "APUNTA Y PELLIZCA")


# ---------------------------------------------------------------- Partículas y bola de energía

TIPS = (4, 8, 12, 16, 20)


class Effects:
    def __init__(self):
        self.particles = []  # [x, y, vx, vy, vida, vida total, tamaño, color]
        self.last_tips = {}
        self.ball = None  # (centro, radio)
        self.charge = 0.0
        self.last = time.monotonic()

    def burst(self, center, power) -> None:
        for _ in range(int(80 + 120 * power)):
            angle, speed = random.uniform(0, 2 * math.pi), random.uniform(150, 650) * (0.5 + power)
            self.particles.append([center[0], center[1], math.cos(angle) * speed, math.sin(angle) * speed,
                                   1.2, 1.2, random.uniform(2, 5), random.choice((CYAN, WHITE, AMBER))])

    def update(self, hands: list[tuple]) -> None:
        """hands: (id, puntos, postura) por mano, en coordenadas de la ventana."""
        now = time.monotonic()
        dt, self.last = min(0.1, now - self.last), now
        for hand_id, points, _ in hands:
            for tip in TIPS:
                x, y = points[tip]
                last = self.last_tips.get((hand_id, tip))
                self.last_tips[(hand_id, tip)] = (x, y)
                if last and math.dist(last, (x, y)) > 3:
                    for _ in range(2):
                        self.particles.append([x, y, random.uniform(-40, 40), random.uniform(-60, 10),
                                               0.6, 0.6, random.uniform(1.5, 3.5), CYAN if tip != 8 else WHITE])
        # Bola de energía: dos palmas abiertas, frente a frente.
        palms = [points for _, points, pose in hands if pose == "palm"]
        fists = [points for _, points, pose in hands if pose == "fist"]
        if len(palms) == 2:
            a, b = palms[0][9], palms[1][9]
            gap = math.dist(a, b)
            center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            self.charge = min(1.0, self.charge + dt * 0.6)
            self.ball = (center, max(25, gap * 0.32))
            for _ in range(3):
                angle = random.uniform(0, 2 * math.pi)
                r = self.ball[1] * 1.6
                self.particles.append([center[0] + math.cos(angle) * r, center[1] + math.sin(angle) * r,
                                       -math.cos(angle) * r * 2, -math.sin(angle) * r * 2, 0.45, 0.45, 2, CYAN])
        elif self.ball is not None:
            if len(fists) == 2 or self.charge > 0.3:
                self.burst(self.ball[0], self.charge)
            self.ball, self.charge = None, 0.0
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.97
            p[3] = p[3] * 0.97 + 30 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0][-2500:]

    def draw(self, painter: QPainter) -> None:
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        painter.setPen(Qt.NoPen)
        for x, y, _, _, life, total, size, color in self.particles:
            painter.setBrush(faded(color, 230 * life / total))
            painter.drawEllipse(QPointF(x, y), size, size)
        if self.ball:
            (cx, cy), radius = self.ball
            radius *= 1 + 0.06 * math.sin(time.monotonic() * 18)
            glow = QRadialGradient(QPointF(cx, cy), radius * 2.2)
            glow.setColorAt(0, faded(WHITE, 255))
            glow.setColorAt(0.25, faded(CYAN, 230))
            glow.setColorAt(0.6, faded(QColor(40, 120, 255), 120 * (0.4 + self.charge)))
            glow.setColorAt(1, faded(CYAN, 0))
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(cx, cy), radius * 2.2, radius * 2.2)
            # Rayos que crepitan alrededor.
            painter.setBrush(Qt.NoBrush)
            for _ in range(4):
                path = QPainterPath(QPointF(cx, cy))
                angle = random.uniform(0, 2 * math.pi)
                for step in range(1, 6):
                    r = radius * 0.4 * step
                    angle += random.uniform(-0.5, 0.5)
                    path.lineTo(QPointF(cx + math.cos(angle) * r, cy + math.sin(angle) * r))
                painter.setPen(QPen(faded(WHITE, 200), 1.5))
                painter.drawPath(path)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


# ---------------------------------------------------------------- Escáner de identidad

class Scanner:
    def __init__(self):
        self.seen = {}  # nombre o "?": cuándo empezó a verse

    def draw(self, painter: QPainter, faces: list[dict]) -> None:
        """faces: {"rect": QRectF en la ventana, "name": str | None, "known": bool}."""
        now = time.monotonic()
        for face in faces:
            rect = face["rect"].adjusted(-30, -40, 30, 30)
            key = face["name"] or "?"
            started = self.seen.setdefault(key, now)
            scanning = now - started < 1.6
            color = CYAN if scanning else (GREEN if face["known"] else RED)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, 2))
            corner = rect.width() * 0.18
            for x, y, dx, dy in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                                 (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1)):
                painter.drawLine(QPointF(x, y), QPointF(x + dx * corner, y))
                painter.drawLine(QPointF(x, y), QPointF(x, y + dy * corner))
            painter.setPen(QPen(faded(color, 90), 1))
            painter.drawEllipse(rect.center(), rect.width() * 0.62, rect.width() * 0.62)
            if scanning:
                line_y = rect.top() + (now - started) / 1.6 * rect.height()
                painter.fillRect(QRectF(rect.left(), line_y, rect.width(), 3), faded(CYAN, 200))
                title, detail = "ESCANEANDO…", f"{int((now - started) / 1.6 * 100)}%"
            elif face["known"]:
                title, detail = f"IDENTIDAD: {face['name'].upper()}", "ACCESO CONCEDIDO"
            else:
                title, detail = "IDENTIDAD: DESCONOCIDA", "ACCESO DENEGADO"
            box = QRectF(rect.right() + 16, rect.top(), 300, 64)
            hud_frame(painter, box, color)
            painter.setFont(FONT)
            painter.setPen(color)
            painter.drawText(QPointF(box.left() + 14, box.top() + 26), title)
            painter.setFont(SMALL)
            painter.setPen(WHITE)
            painter.drawText(QPointF(box.left() + 14, box.top() + 48), detail)
        if not faces:
            self.seen = {}


# ---------------------------------------------------------------- Visualizador de audio

class AudioLevels:
    """Lo que suena en la PC (música, la voz de Jarvis), en bandas de frecuencia. Corre en un hilo."""

    BANDS = 48

    def __init__(self):
        self.bands = [0.0] * self.BANDS
        self.running = False

    def run(self) -> None:
        import warnings

        import numpy as np
        import soundcard

        warnings.filterwarnings("ignore")
        speaker = soundcard.default_speaker()
        loopback = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
        edges = np.geomspace(40, 16000, self.BANDS + 1)
        window = np.hanning(2048)
        freqs = np.fft.rfftfreq(2048, 1 / 48000)
        groups = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges, edges[1:])]
        self.running = True
        with loopback.recorder(samplerate=48000, channels=1, blocksize=1024) as recorder:
            while self.running:
                samples = recorder.record(numframes=2048)[:, 0]
                spectrum = np.abs(np.fft.rfft(samples * window))
                levels = [float(spectrum[g].mean()) if len(g) else 0.0 for g in groups]
                levels = [min(1.0, math.log10(1 + level * 4) / 1.6) for level in levels]
                self.bands = [max(new, old * 0.82) for new, old in zip(levels, self.bands)]


def draw_visualizer(painter: QPainter, width: int, height: int, bands: list[float]) -> None:
    center = QPointF(width / 2, height / 2)
    base = min(width, height) * 0.2
    count = len(bands)
    painter.setCompositionMode(QPainter.CompositionMode_Plus)
    for mirror in (1, -1):
        for i, level in enumerate(bands):
            angle = math.pi / 2 + mirror * (i + 0.5) * math.pi / count
            length = 8 + level * base * 0.9
            inner = QPointF(center.x() + math.cos(angle) * base, center.y() - math.sin(angle) * base)
            outer = QPointF(center.x() + math.cos(angle) * (base + length), center.y() - math.sin(angle) * (base + length))
            color = AMBER if level > 0.75 else CYAN
            painter.setPen(QPen(faded(color, 120 + 130 * level), 5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(inner, outer)
    energy = sum(bands) / max(1, count)
    glow = QRadialGradient(center, base)
    glow.setColorAt(0, faded(CYAN, 90 * energy * 2))
    glow.setColorAt(1, faded(CYAN, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(center, base, base)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


# ---------------------------------------------------------------- Paneles laterales (la página web, en holograma)

LISTENER_LABELS = {"wake": ("EN LÍNEA", CYAN), "listening": ("ESCUCHANDO", WHITE), "thinking": ("PROCESANDO", AMBER),
                   "speaking": ("HABLANDO", CYAN), "dictating": ("DICTADO", GREEN), "paused": ("EN PAUSA", MUTED),
                   "error": ("ERROR", RED), "off": ("INICIANDO", MUTED)}
QUICK = [("Vol −", ("quick", "volume_down")), ("Vol +", ("quick", "volume_up")), ("Silencio", ("quick", "mute")),
         ("Pausa", ("quick", "play_pause")), ("Anterior", ("quick", "previous")), ("Siguiente", ("quick", "next")),
         ("Bloquear", ("quick", "lock"))]
HOLD_TO_APPROVE = 1.5  # segundos: aprobar algo delicado (apagar, borrar) con un pellizco sostenido


class SidePanels:
    """A la izquierda la conversación y las autorizaciones; a la derecha el estado y los botones rápidos."""

    def __init__(self, act):
        """act(tipo, valor): ("quick", acción), ("toggle", (modo, encender)), ("listener", encender),
        ("confirm", (id, aprobado))."""
        self.act = act
        self.chat = []  # avisos "user", "jarvis" y "error" del servidor
        self.status = {}
        self.stats = {}
        self.buttons = []  # (rect, token) del último dibujo
        self.holding = None  # (token, desde cuándo)
        self.answered = set()
        self.flash = {}

    def add_events(self, items: list[dict]) -> None:
        self.chat = (self.chat + [item for item in items if item["type"] in ("user", "jarvis", "error")])[-30:]

    def pending(self):
        for item in reversed(self.chat):
            if item["type"] == "jarvis" and item.get("pending") and item["pending"]["id"] not in self.answered:
                return item["pending"]
        return None

    def hit(self, point):
        for rect, token in self.buttons:
            if rect.contains(QPointF(*point)):
                return token
        return None

    def press(self, token, point) -> None:
        self.flash[token] = time.monotonic()
        if token[0] == "approve":
            self.holding = (token, time.monotonic())
        elif token[0] == "deny":
            self.answered.add(token[1])
            self.act("confirm", (token[1], False))
        else:
            self.act(*token)

    def drag(self, token, point) -> None:
        if self.holding and self.holding[0] == token and time.monotonic() - self.holding[1] >= HOLD_TO_APPROVE:
            self.answered.add(token[1])
            self.act("confirm", (token[1], True))
            self.holding = None

    def release(self, token) -> None:
        self.holding = None

    def _button(self, painter, rect, label, token, hover, active=False, accent=CYAN):
        hot = hover is not None and rect.contains(QPointF(*hover))
        pressed = time.monotonic() - self.flash.get(token, 0) < 0.2
        painter.setPen(QPen(faded(accent, 230 if hot or active else 110), 1.4))
        painter.setBrush(faded(accent, 150 if pressed else 70 if active else 45 if hot else 14))
        painter.drawRect(rect)
        painter.setFont(SMALL)
        painter.setPen(WHITE if hot or active else faded(accent, 230))
        painter.drawText(rect, Qt.AlignCenter, label)
        self.buttons.append((rect, token))

    def draw(self, painter: QPainter, width: int, height: int, hover) -> None:
        self.buttons = []
        bottom = height - 150
        self._draw_chat(painter, QRectF(18, 60, 380, bottom - 60), hover)
        # A la medida de su contenido: así no queda un hueco ni tapa el orbe de la esquina.
        self._draw_status(painter, QRectF(width - 338, 60, 320, min(bottom - 60, 770)), hover)

    def _draw_chat(self, painter, rect, hover):
        hud_frame(painter, rect)
        painter.setFont(SMALL)
        painter.setPen(CYAN)
        painter.drawText(QPointF(rect.left() + 14, rect.top() + 22), "J.A.R.V.I.S. · CONVERSACIÓN")
        pending = self.pending()
        y = rect.bottom() - 12
        if pending:
            y = self._draw_confirm(painter, rect, pending, hover) - 10
        body = QFont("Segoe UI", 10)
        for item in reversed(self.chat):
            text = item.get("text") or ""
            if not text:
                continue
            painter.setFont(body)
            bounds = painter.boundingRect(QRectF(0, 0, rect.width() - 44, 400), Qt.TextWordWrap, text)
            box = QRectF(rect.left() + 12, y - bounds.height() - 26, rect.width() - 24, bounds.height() + 22)
            if box.top() < rect.top() + 34:
                break
            color = {"user": AMBER, "error": RED}.get(item["type"], CYAN)
            painter.setPen(Qt.NoPen)
            painter.setBrush(faded(color, 26))
            painter.drawRect(box)
            painter.setBrush(color)
            painter.drawRect(QRectF(box.left(), box.top(), 3, box.height()))
            painter.setFont(SMALL)
            painter.setPen(color)
            painter.drawText(QPointF(box.left() + 12, box.top() + 13),
                             {"user": "TÚ", "error": "SISTEMA"}.get(item["type"], "JARVIS"))
            painter.setFont(body)
            painter.setPen(WHITE)
            painter.drawText(QRectF(box.left() + 12, box.top() + 16, box.width() - 20, bounds.height() + 4),
                             Qt.TextWordWrap, text)
            y = box.top() - 6

    def _draw_confirm(self, painter, rect, pending, hover) -> float:
        actions = "\n".join(f"{a['tool']} {json.dumps(a['args'], ensure_ascii=False)[:80]}" for a in pending["actions"])
        painter.setFont(SMALL)
        bounds = painter.boundingRect(QRectF(0, 0, rect.width() - 48, 300), Qt.TextWordWrap, actions)
        box = QRectF(rect.left() + 12, rect.bottom() - bounds.height() - 104, rect.width() - 24, bounds.height() + 92)
        painter.setPen(QPen(AMBER, 1.5))
        painter.setBrush(faded(AMBER, 22))
        painter.drawRect(box)
        painter.setPen(AMBER)
        painter.drawText(QPointF(box.left() + 12, box.top() + 18), "AUTORIZACIÓN REQUERIDA")
        painter.setPen(WHITE)
        painter.drawText(QRectF(box.left() + 12, box.top() + 26, box.width() - 24, bounds.height() + 4),
                         Qt.TextWordWrap, actions)
        half = (box.width() - 36) / 2
        approve = QRectF(box.left() + 12, box.bottom() - 46, half, 34)
        deny = QRectF(approve.right() + 12, approve.top(), half, 34)
        token = ("approve", pending["id"])
        self._button(painter, approve, "APROBAR (MANTÉN)", token, hover, accent=GREEN)
        if self.holding and self.holding[0] == token:
            done = min(1.0, (time.monotonic() - self.holding[1]) / HOLD_TO_APPROVE)
            painter.fillRect(QRectF(approve.left(), approve.bottom() - 4, approve.width() * done, 4), GREEN)
        self._button(painter, deny, "RECHAZAR", ("deny", pending["id"]), hover, accent=RED)
        return box.top()

    def _draw_status(self, painter, rect, hover):
        hud_frame(painter, rect)
        now = datetime.now()
        painter.setFont(QFont("Consolas", 26))
        painter.setPen(CYAN)
        painter.drawText(QRectF(rect.left(), rect.top() + 8, rect.width(), 40), Qt.AlignCenter, now.strftime("%H:%M"))
        painter.setFont(SMALL)
        painter.setPen(MUTED)
        painter.drawText(QRectF(rect.left(), rect.top() + 48, rect.width(), 16), Qt.AlignCenter, now.strftime("%d/%m/%Y"))

        listener = self.status.get("listener", {})
        state = "dictating" if listener.get("dictation") else listener.get("state", "off")
        if listener and not listener.get("enabled", True):
            state = "paused"
        label, color = LISTENER_LABELS.get(state, LISTENER_LABELS["off"])
        center = QPointF(rect.center().x(), rect.top() + 120)
        t = time.monotonic()
        painter.save()
        painter.translate(center)
        for i, (radius, dash) in enumerate(((44, [3, 4]), (36, [16, 6]), (28, [6, 3]))):
            painter.rotate((t * (30 + i * 25)) % 360 * (1 if i % 2 else -1))
            pen = QPen(faded(color, 180), 2)
            pen.setDashPattern(dash)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius, radius)
        painter.restore()
        core = QRadialGradient(center, 22)
        core.setColorAt(0, WHITE)
        core.setColorAt(0.5, faded(color, 220))
        core.setColorAt(1, faded(color, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(core)
        pulse = 1 + (0.25 * abs(math.sin(t * 8)) if state == "speaking" else 0.06 * math.sin(t * 2))
        painter.drawEllipse(center, 22 * pulse, 22 * pulse)
        painter.setFont(SMALL)
        painter.setPen(color)
        painter.drawText(QRectF(rect.left(), center.y() + 52, rect.width(), 16), Qt.AlignCenter, label)

        gpu = self.stats.get("gpu")
        gauges = [("CPU", self.stats.get("cpu")), ("RAM", self.stats.get("ram")), ("DISCO", self.stats.get("disk")),
                  ("GPU", gpu[0] if gpu else None)]
        gauge_y = center.y() + 84
        for i, (name, value) in enumerate(gauges):
            gauge_center = QPointF(rect.left() + 40 + i * 80, gauge_y + 26)
            box = QRectF(gauge_center.x() - 24, gauge_center.y() - 24, 48, 48)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(faded(CYAN, 40), 4))
            painter.drawEllipse(box)
            if value is not None:
                painter.setPen(QPen(AMBER if value >= 85 else CYAN, 4, Qt.SolidLine, Qt.FlatCap))
                painter.drawArc(box, 90 * 16, int(-360 * 16 * value / 100))
            painter.setFont(SMALL)
            painter.setPen(WHITE)
            painter.drawText(box, Qt.AlignCenter, "--" if value is None else f"{value:.0f}")
            painter.setPen(MUTED)
            painter.drawText(QRectF(gauge_center.x() - 40, gauge_center.y() + 28, 80, 14), Qt.AlignCenter, name)

        top = gauge_y + 70
        modes = self.status.get("modes", {})
        recording = self.status.get("recording", {}).get("recording", False)
        presence = self.status.get("presence", {})
        mode = lambda name, label: (label, ("toggle", (name, not modes.get(name))), bool(modes.get(name)))
        sections = [
            ("SISTEMA", 2, [
                ("ESCUCHA", ("listener", not listener.get("enabled", True)), listener.get("enabled", True)),
                ("DICTADO", ("dictation", not listener.get("dictation")), bool(listener.get("dictation"))),
                ("PRESENCIA", ("presence", not presence.get("enabled")), bool(presence.get("enabled"))),
                ("GUARDIA", ("toggle", ("guard", not presence.get("guard"))), bool(presence.get("guard"))),
                ("GRABAR", ("toggle", ("record", not recording)), recording),
                mode("subtitles", "SUBTÍTULOS"),
                mode("orb", "ORBE"),
                ("SOLO LOCAL", ("toggle", ("local", not modes.get("local_only"))), bool(modes.get("local_only"))),
                ("OCULTAR PANELES", ("toggle", ("panels", False)), False),
                ("APAGAR HOLOGRAMA", ("hologram_off", None), False),
            ]),
            ("HOLOGRAMAS", 3, [
                mode("scanner", "ESCÁNER"), mode("effects", "EFECTOS"), mode("draw", "DIBUJO"),
                mode("globe", "ESFERA"), mode("solar", "SIST. SOLAR"), mode("earth", "TIERRA"),
                mode("keyboard", "TECLADO"), mode("notes", "NOTAS"), mode("visualizer", "VISUALIZ."),
                mode("taskbar", "BARRA TAREAS"), mode("life", "MI VIDA"),
            ]),
            ("ACCIONES RÁPIDAS", 3, [(label, token, False) for label, token in QUICK] + [
                ("Estado", ("chat", "estado de la PC"), False),
                ("Apagar", ("chat", "Apaga la PC."), False),
                ("Reiniciar", ("chat", "Reinicia la PC."), False),
            ]),
        ]
        # Los botones se encogen si la pantalla es baja, para que entre todo.
        rows = sum(-(-len(items) // columns) for _, columns, items in sections)
        row_h = max(24, min(34, (rect.bottom() - top - 8 - len(sections) * 22) / rows))
        for title, columns, items in sections:
            painter.setFont(SMALL)
            painter.setPen(MUTED)
            painter.drawText(QPointF(rect.left() + 14, top + 13), title)
            top += 20
            width = (rect.width() - 24 - (columns - 1) * 8) / columns
            for i, (label, token, active) in enumerate(items):
                box = QRectF(rect.left() + 12 + (i % columns) * (width + 8), top + (i // columns) * row_h,
                             width, row_h - 6)
                if box.bottom() > rect.bottom() - 4:
                    break
                danger = label in ("Apagar", "Reiniciar") or (label == "GRABAR" and active)
                self._button(painter, box, label, token, hover, active=active, accent=RED if danger else CYAN)
            top += -(-len(items) // columns) * row_h + 2


# ---------------------------------------------------------------- Barra de tareas holográfica

CARD_W, CARD_H = 170, 104
REVEAL_ZONE = 0.86  # bajar la mano por debajo del 86 % de la pantalla muestra la barra


class Dock:
    """Las ventanas abiertas como tarjetas flotantes abajo. Pellizcar una la trae al frente."""

    def __init__(self, activate, start_menu, show_desktop):
        self.activate, self.start_menu, self.show_desktop = activate, start_menu, show_desktop
        self.windows = []  # {"hwnd", "title", "minimized", "active", "icon": QImage | None}
        self.reveal = 0.0
        self.last_near = 0.0
        self.cards = []  # (rect, token)
        self.flash = {}
        self.pin_until = 0.0  # al pedirla por voz se queda a la vista unos segundos

    def set_windows(self, windows: list[dict]) -> None:
        self.windows = windows[:9]

    def update(self, hover, height: int, pinned: bool) -> None:
        now = time.monotonic()
        near = hover is not None and hover[1] >= height * REVEAL_ZONE
        if near or pinned or now < self.pin_until:
            self.last_near = now
        target = 1.0 if now - self.last_near < 1.2 else 0.0  # se queda un momento al alejar la mano
        self.reveal += (target - self.reveal) * 0.25

    def hit(self, point):
        if self.reveal < 0.7:
            return None
        for rect, token in self.cards:
            if rect.contains(QPointF(*point)):
                return token
        return None

    def press(self, token) -> None:
        self.flash[token] = time.monotonic()
        kind, value = token
        if kind == "window":
            self.activate(value)
        elif kind == "start":
            self.start_menu()
        else:
            self.show_desktop()

    def draw(self, painter: QPainter, width: int, height: int, hover) -> None:
        self.cards = []
        if self.reveal < 0.02:
            return
        items = ([("start", None, "INICIO", None, False, False)]
                 + [("window", w["hwnd"], w["title"], w.get("icon"), w["minimized"], w["active"]) for w in self.windows]
                 + [("desktop", None, "ESCRITORIO", None, False, False)])
        gap = 12
        scale = min(1.0, (width - 80) / (len(items) * (CARD_W + gap) - gap))
        card_w, card_h = CARD_W * scale, CARD_H * scale
        row = len(items) * (card_w + gap) - gap
        left = (width - row) / 2
        top = height - 90 - card_h + 30 * (1 - self.reveal)
        painter.setOpacity(self.reveal)
        back = QRectF(left - 18, top - 34, row + 36, card_h + 50)
        hud_frame(painter, back)
        painter.setFont(SMALL)
        painter.setPen(CYAN)
        painter.drawText(QPointF(back.left() + 14, back.top() + 18), "BARRA DE TAREAS · PELLIZCA UNA VENTANA")
        now = time.monotonic()
        for i, (kind, value, title, icon, minimized, active) in enumerate(items):
            rect = QRectF(left + i * (card_w + gap), top, card_w, card_h)
            token = (kind, value)
            hot = hover is not None and rect.contains(QPointF(*hover))
            self.cards.append((rect, token))
            if hot:
                rect = rect.adjusted(-6, -10, 6, 0)
            pressed = now - self.flash.get(token, 0) < 0.25
            accent = AMBER if active else CYAN
            painter.setPen(QPen(faded(accent, 240 if hot or active else 120), 1.5))
            painter.setBrush(faded(accent, 140 if pressed else 50 if hot else 18))
            painter.drawRoundedRect(rect, 5, 5)
            icon_box = QRectF(rect.center().x() - 20, rect.top() + 12, 40, 40)
            if icon is not None and not icon.isNull():
                painter.drawImage(icon_box, icon)
            elif kind == "start":  # cuatro cuadros
                painter.setPen(Qt.NoPen)
                painter.setBrush(CYAN)
                for dx in (0, 1):
                    for dy in (0, 1):
                        painter.drawRect(QRectF(icon_box.left() + 4 + dx * 17, icon_box.top() + 4 + dy * 17, 15, 15))
            elif kind == "desktop":  # una pantalla vacía
                painter.setPen(QPen(CYAN, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(icon_box.adjusted(2, 6, -2, -10))
                painter.drawLine(QPointF(icon_box.center().x() - 8, icon_box.bottom() - 3), QPointF(icon_box.center().x() + 8, icon_box.bottom() - 3))
            else:
                painter.setFont(BIG)
                painter.setPen(WHITE)
                painter.drawText(icon_box, Qt.AlignCenter, title[:1].upper())
            painter.setFont(SMALL)
            painter.setPen(MUTED if minimized else WHITE)
            short = title if len(title) <= 22 else title[:21] + "…"
            painter.drawText(QRectF(rect.left() + 6, rect.bottom() - 40, rect.width() - 12, 34),
                             Qt.AlignCenter | Qt.TextWordWrap, short)
            if minimized:
                painter.setPen(QPen(MUTED, 2))
                painter.drawLine(QPointF(rect.center().x() - 12, rect.bottom() - 4),
                                 QPointF(rect.center().x() + 12, rect.bottom() - 4))
        painter.setOpacity(1.0)


# ---------------------------------------------------------------- Mi vida

LIFE_TABS = [("today", "HOY"), ("tasks", "TAREAS"), ("body", "CUERPO"), ("food", "COMIDA"), ("habits", "HÁBITOS"),
             ("money", "DINERO"), ("classes", "CLASES"), ("calendar", "CALENDARIO"), ("ideas", "IDEAS")]
WEEK = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
MOOD_NAMES = ["MUY MAL", "MAL", "NORMAL", "BIEN", "EXCELENTE"]
MOOD_COLORS = [QColor(255, 77, 94), QColor(255, 159, 90), QColor(255, 209, 102), QColor(79, 216, 255), QColor(90, 255, 180)]
MONTH_NAMES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE",
               "NOVIEMBRE", "DICIEMBRE"]
BODY = QFont("Segoe UI", 11)
BODY_BOLD = QFont("Segoe UI", 11, QFont.DemiBold)
TITLE = QFont("Consolas", 12)


class LifePanel:
    """El panel de «Mi vida». Lo que se pellizca se avisa con act(acción, datos) y cambia al instante en pantalla."""

    def __init__(self, act, show_page):
        self.act, self.show_page = act, show_page
        self.summary = None
        self.page = "today"
        self.buttons = []
        self.map_id = None
        self.dragging = None  # (id del mapa, id del nodo, desplazamiento)
        self.canvas = QRectF()
        self.area = QRectF()

    # ------------------------------------------------ datos

    def update(self, summary: dict | None, page: str | None) -> None:
        if summary is not None and not self.dragging:
            self.summary = summary
        if page:
            self.page = page

    def hit(self, point):
        for rect, token in reversed(self.buttons):
            if rect.contains(QPointF(*point)):
                return token
        return ("none",) if self.area.contains(QPointF(*point)) else None

    def press(self, token, point) -> None:
        kind = token[0]
        s = self.summary or {}
        if kind == "tab":
            self.page = token[1]
            self.show_page(token[1])
        elif kind in ("task", "habit", "routine"):
            _, item_id, done = token
            lists = {"task": s.get("tasks", []) + s.get("tasks_done_today", []), "habit": s.get("habits", []),
                     "routine": s.get("routine", [])}[kind]
            for item in lists:
                if item["id"] == item_id:
                    item["done"] = not done  # se ve al instante; el servidor confirma enseguida
            action = {"task": "task_done", "habit": "habit_check", "routine": "routine_check"}[kind]
            key = {"task": "task", "habit": "habit", "routine": "item"}[kind]
            self.act(action, {key: item_id, "done": not done})
        elif kind == "water":
            s["water"]["today"] = max(0, s["water"]["today"] + token[1])
            self.act("water", {"glasses": token[1]})
        elif kind == "mood":
            s["mood"]["today"] = {"score": token[1], "note": ""}
            self.act("mood", {"score": token[1]})
        elif kind == "clear_done":
            self.act("tasks_clear_done", {})
        elif kind == "map":
            self.map_id = token[1]
        elif kind == "node":
            _, map_id, node_id = token
            node = self._node(map_id, node_id)
            if node:
                x, y = self._to_canvas(node)
                self.dragging = (map_id, node_id, (point[0] - x, point[1] - y))

    def drag(self, token, point) -> None:
        if not self.dragging or token[0] != "node":
            return
        map_id, node_id, (dx, dy) = self.dragging
        node = self._node(map_id, node_id)
        if node and self.canvas.width() > 0:
            node["x"] = min(0.98, max(0.02, (point[0] - dx - self.canvas.left()) / self.canvas.width()))
            node["y"] = min(0.98, max(0.02, (point[1] - dy - self.canvas.top()) / self.canvas.height()))

    def release(self, token) -> None:
        if self.dragging and token[0] == "node":
            map_id, node_id, _ = self.dragging
            node = self._node(map_id, node_id)
            self.dragging = None
            if node:
                self.act("node_move", {"map_": map_id, "node": node_id, "x": node["x"], "y": node["y"]})

    def _node(self, map_id, node_id):
        for chart in (self.summary or {}).get("maps", []):
            if chart["id"] == map_id:
                return next((n for n in chart["nodes"] if n["id"] == node_id), None)
        return None

    def _to_canvas(self, node):
        return self.canvas.left() + node["x"] * self.canvas.width(), self.canvas.top() + node["y"] * self.canvas.height()

    # ------------------------------------------------ piezas de dibujo

    def _button(self, painter, rect, label, token, hover, active=False, accent=CYAN, font=SMALL):
        hot = hover is not None and rect.contains(QPointF(*hover))
        painter.setPen(QPen(faded(accent, 230 if hot or active else 110), 1.3))
        painter.setBrush(faded(accent, 70 if active else 40 if hot else 12))
        painter.drawRect(rect)
        painter.setFont(font)
        painter.setPen(WHITE if hot or active else faded(accent, 235))
        painter.drawText(rect, Qt.AlignCenter, label)
        self.buttons.append((rect, token))

    def _check(self, painter, x, y, width, text, done, token, hover, detail="", accent=CYAN):
        """Una fila con casilla que se pellizca."""
        row = QRectF(x, y, width, 30)
        hot = hover is not None and row.contains(QPointF(*hover))
        if hot:
            painter.fillRect(row, faded(accent, 30))
        box = QRectF(x + 6, y + 7, 16, 16)
        painter.setPen(QPen(faded(accent, 230), 1.5))
        painter.setBrush(faded(accent, 200) if done else Qt.NoBrush)
        painter.drawRect(box)
        if done:
            painter.setPen(QPen(QColor(2, 14, 24), 2.5))
            painter.drawLine(QPointF(box.left() + 3, box.center().y()), QPointF(box.center().x() - 1, box.bottom() - 3))
            painter.drawLine(QPointF(box.center().x() - 1, box.bottom() - 3), QPointF(box.right() - 3, box.top() + 3))
        painter.setFont(BODY)
        painter.setPen(MUTED if done else WHITE)
        metrics = painter.fontMetrics()
        room = width - 40 - (metrics.horizontalAdvance(detail) + 10 if detail else 0)
        painter.drawText(QPointF(x + 32, y + 20), metrics.elidedText(text, Qt.ElideRight, int(room)))
        if detail:
            painter.setFont(SMALL)
            painter.setPen(faded(accent, 200))
            painter.drawText(QRectF(x, y, width - 6, 30), Qt.AlignRight | Qt.AlignVCenter, detail)
        self.buttons.append((row, token))

    def _ring(self, painter, center, radius, value, goal, label, unit):
        box = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(faded(CYAN, 40), 8))
        painter.drawEllipse(box)
        share = min(1.0, value / goal) if goal else 0
        painter.setPen(QPen(GREEN if share >= 1 else CYAN, 8, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(box, 90 * 16, int(-360 * 16 * share))
        painter.setFont(QFont("Consolas", 14))
        painter.setPen(WHITE)
        painter.drawText(QRectF(box.left(), center.y() - 16, box.width(), 22), Qt.AlignCenter, f"{value:.0f}")
        painter.setFont(SMALL)
        painter.setPen(MUTED)
        painter.drawText(QRectF(box.left(), center.y() + 4, box.width(), 16), Qt.AlignCenter, f"/ {goal:.0f}")
        painter.setPen(CYAN)
        painter.drawText(QRectF(box.left() - 30, box.bottom() + 6, box.width() + 60, 16), Qt.AlignCenter,
                         f"{label} · {unit.upper()}")

    def _card(self, painter, rect, title, accent=CYAN) -> float:
        hud_frame(painter, rect, accent)
        painter.setFont(SMALL)
        painter.setPen(accent)
        painter.drawText(QPointF(rect.left() + 12, rect.top() + 18), title)
        return rect.top() + 30

    def _text(self, painter, x, y, text, color=WHITE, font=BODY, width=None):
        painter.setFont(font)
        painter.setPen(color)
        if width:
            text = painter.fontMetrics().elidedText(text, Qt.ElideRight, int(width))
        painter.drawText(QPointF(x, y), text)

    # ------------------------------------------------ panel

    def draw(self, painter: QPainter, area: QRectF, hover) -> None:
        self.buttons = []
        self.area = area
        hud_frame(painter, area)
        tab_width = (area.width() - 24 - 8 * 6) / len(LIFE_TABS)
        for i, (page, label) in enumerate(LIFE_TABS):
            tab = QRectF(area.left() + 12 + i * (tab_width + 6), area.top() + 12, tab_width, 34)
            self._button(painter, tab, label, ("tab", page), hover, active=self.page == page)
        body = QRectF(area.left() + 12, area.top() + 58, area.width() - 24, area.height() - 70)
        if not self.summary:
            self._text(painter, body.left(), body.top() + 30, "Cargando tu información…", MUTED)
            return
        getattr(self, "_page_" + self.page, self._page_today)(painter, body, hover)

    def _grid(self, body, columns, rows):
        width = (body.width() - (columns - 1) * 12) / columns
        height = (body.height() - (rows - 1) * 12) / rows
        return [QRectF(body.left() + c * (width + 12), body.top() + r * (height + 12), width, height)
                for r in range(rows) for c in range(columns)]

    def _page_today(self, painter, body, hover):
        s = self.summary
        cells = self._grid(body, 3, 2)
        # Clases
        y = self._card(painter, cells[0], f"CLASES · {s['weekday'].upper()} {s['clock']}")
        current, upcoming = s["classes"]["now"], s["classes"]["next"]
        for label, cls, color in (("AHORA", current, GREEN), ("SIGUIENTE", upcoming, CYAN)):
            if cls:
                self._text(painter, cells[0].left() + 12, y + 16, label, color, SMALL)
                self._text(painter, cells[0].left() + 12, y + 36, cls["subject"], WHITE, BODY_BOLD, cells[0].width() - 24)
                where = " · ".join(x for x in (f"{cls['start']}–{cls['end']}", f"Aula {cls['room']}" if cls["room"] else "",
                                                 cls["place"], cls["teacher"]) if x)
                self._text(painter, cells[0].left() + 12, y + 56, where, MUTED, SMALL, cells[0].width() - 24)
                y += 70
        if not current and not upcoming:
            self._text(painter, cells[0].left() + 12, y + 20, "Sin más clases hoy", MUTED)
        # Tareas
        y = self._card(painter, cells[1], f"TAREAS · {len(s['tasks'])} PENDIENTES", AMBER)
        for task in s["tasks"][:int((cells[1].bottom() - y - 8) // 32)]:
            due = task["due"][8:] + "/" + task["due"][5:7] if task["due"] else ""  # día/mes
            self._check(painter, cells[1].left() + 6, y, cells[1].width() - 12, task["text"], False,
                        ("task", task["id"], False), hover, due, RED if task["priority"] == "alta" else AMBER)
            y += 32
        # Nutrición y agua
        y = self._card(painter, cells[2], "ALIMENTACIÓN · META: GANAR MÚSCULO", GREEN)
        food, goals = s["food"], s["food"]["goals"]
        radius = min(42, cells[2].width() / 7)
        self._ring(painter, QPointF(cells[2].left() + cells[2].width() * 0.27, y + radius + 10), radius, food["kcal"], goals["kcal"], "CALORÍAS", "kcal")
        self._ring(painter, QPointF(cells[2].left() + cells[2].width() * 0.73, y + radius + 10), radius, food["protein"], goals["protein"], "PROTEÍNA", "g")
        water = s["water"]
        y_water = cells[2].bottom() - 42
        glass = min(22, (cells[2].width() - 100) / water["goal"] - 4)
        for i in range(water["goal"]):
            box = QRectF(cells[2].left() + 12 + i * (glass + 4), y_water, glass, 28)
            painter.setPen(QPen(faded(CYAN, 160), 1))
            painter.setBrush(faded(CYAN, 170) if i < water["today"] else Qt.NoBrush)
            painter.drawRect(box)
        self._button(painter, QRectF(cells[2].right() - 76, y_water, 64, 28), "+ AGUA", ("water", 1), hover)
        # Hábitos y rutina
        y = self._card(painter, cells[3], "HÁBITOS Y RUTINA", GREEN)
        rows = [("habit", h["id"], h["name"], h["done"], f"RACHA {h['streak']}" if h["streak"] else "") for h in s["habits"]] + \
               [("routine", r["id"], r["text"], r["done"], r["time"] or "") for r in s["routine"]]
        for kind, item_id, text, done, detail in rows[:int((cells[3].bottom() - y - 8) // 32)]:
            self._check(painter, cells[3].left() + 6, y, cells[3].width() - 12, text, done, (kind, item_id, done), hover, detail, GREEN)
            y += 32
        if not rows:
            self._text(painter, cells[3].left() + 12, y + 20, "Di «agrega el hábito leer»", MUTED, SMALL)
        # Ánimo, sueño y ejercicio
        y = self._card(painter, cells[4], "¿CÓMO TE SIENTES HOY?", VIOLET_SOFT)
        today_mood = (s["mood"]["today"] or {}).get("score")
        size = min(76, (cells[4].width() - 24 - 4 * 8) / 5)
        for i, name in enumerate(MOOD_NAMES):
            box = QRectF(cells[4].left() + 12 + i * (size + 8), y + 4, size, 52)
            self._button(painter, box, f"{i + 1}\n{name}", ("mood", i + 1), hover, active=today_mood == i + 1,
                         accent=MOOD_COLORS[i])
        size = 52
        sleep, exercise = s["sleep"], s["exercise"]
        self._text(painter, cells[4].left() + 12, y + size + 32,
                   f"Sueño: {sleep['last']:g} h" if sleep["last"] is not None else "Sueño: sin dato (di «dormí 7 horas»)", WHITE, SMALL)
        self._text(painter, cells[4].left() + 12, y + size + 52,
                   f"Ejercicio: racha de {exercise['streak']} días · {exercise['week_minutes']} min esta semana", WHITE, SMALL)
        # Próximos días y dinero
        y = self._card(painter, cells[5], "PRÓXIMOS DÍAS", AMBER)
        items = [(e["date"], e["title"] + (f" · {e['time']}" if e["time"] else ""), CYAN) for e in s["events"]] + \
                [(h["date"], "Feriado: " + h["name"], AMBER) for h in s["holidays"]]
        for day, text, color in sorted(items)[:int((cells[5].bottom() - y - 40) // 22)]:
            self._text(painter, cells[5].left() + 12, y + 16, day[8:] + "/" + day[5:7], color, SMALL)
            self._text(painter, cells[5].left() + 62, y + 16, text, WHITE, SMALL, cells[5].width() - 74)
            y += 22
        money = s["money"]
        self._text(painter, cells[5].left() + 12, cells[5].bottom() - 14,
                   f"Gastado este mes: {money['spent']:g} Bs · Ahorrado: {money['saved']:g} Bs", MUTED, SMALL)

    def _page_tasks(self, painter, body, hover):
        s = self.summary
        half = (body.width() - 12) / 2
        for column, (title, items, done) in enumerate((("PENDIENTES", s["tasks"], False),
                                                       ("HECHAS HOY", s["tasks_done_today"], True))):
            rect = QRectF(body.left() + column * (half + 12), body.top(), half, body.height())
            y = self._card(painter, rect, f"{title} · {len(items)}", AMBER if not done else GREEN)
            for task in items[:int((rect.bottom() - y - 50) // 32)]:
                due = ("vence " + task["due"][8:] + "/" + task["due"][5:7]) if task.get("due") else ""
                accent = RED if task["priority"] == "alta" and not done else (GREEN if done else AMBER)
                self._check(painter, rect.left() + 6, y, rect.width() - 12, task["text"], done,
                            ("task", task["id"], done), hover, due, accent)
                y += 32
            if done and items:
                self._button(painter, QRectF(rect.left() + 12, rect.bottom() - 44, 180, 32), "BORRAR LAS HECHAS",
                             ("clear_done",), hover, accent=RED)
        self._text(painter, body.left(), body.bottom() + 2, "Di «agrega tarea …» o «terminé …»", MUTED, SMALL)

    def _page_body(self, painter, body, hover):
        s = self.summary["body"]
        goals = self.summary["food"]["goals"]
        left = QRectF(body.left(), body.top(), body.width() * 0.34, body.height())
        chart = QRectF(left.right() + 12, body.top(), body.width() - left.width() - 12, body.height())
        y = self._card(painter, left, "TU CUERPO", GREEN)
        rows = [("Peso", f"{s['weight']:.1f} kg" if s["weight"] else "— (di «peso 70 kilos»)"),
                ("Estatura", f"{s['height_cm']} cm" if s["height_cm"] else "— (di «mido 1.75»)"),
                ("IMC", f"{s['bmi']} · {s['bmi_label']}" if s["bmi"] else "—"),
                ("Meta", "Ganar masa muscular" if s["goal"] == "muscle" else s["goal"] or "—"),
                ("Peso objetivo", f"{s['target_kg']:g} kg" if s["target_kg"] else "— (di «mi meta es 75 kilos»)"),
                ("Calorías al día", f"{goals['kcal']:.0f} kcal"), ("Proteína al día", f"{goals['protein']} g")]
        for label, value in rows:
            self._text(painter, left.left() + 14, y + 22, label, MUTED, SMALL)
            self._text(painter, left.left() + 14, y + 42, value, WHITE, BODY_BOLD, left.width() - 28)
            y += 50
        y = self._card(painter, chart, "PESO · ÚLTIMOS REGISTROS", GREEN)
        history = s["history"]
        plot = QRectF(chart.left() + 50, y + 10, chart.width() - 70, chart.bottom() - y - 50)
        if len(history) < 2:
            self._text(painter, plot.left(), plot.center().y(), "Registra tu peso varios días para ver la gráfica", MUTED)
            return
        weights = [w["kg"] for w in history] + ([s["target_kg"]] if s["target_kg"] else [])
        low, high = min(weights) - 1, max(weights) + 1
        to_y = lambda kg: plot.bottom() - (kg - low) / (high - low) * plot.height()
        painter.setFont(SMALL)
        for step in range(5):
            kg = low + (high - low) * step / 4
            painter.setPen(QPen(faded(CYAN, 30), 1))
            painter.drawLine(QPointF(plot.left(), to_y(kg)), QPointF(plot.right(), to_y(kg)))
            painter.setPen(MUTED)
            painter.drawText(QRectF(chart.left() + 4, to_y(kg) - 8, 42, 16), Qt.AlignRight, f"{kg:.0f}")
        if s["target_kg"]:
            painter.setPen(QPen(AMBER, 1.5, Qt.DashLine))
            painter.drawLine(QPointF(plot.left(), to_y(s["target_kg"])), QPointF(plot.right(), to_y(s["target_kg"])))
        path = QPainterPath()
        points = [QPointF(plot.left() + i / (len(history) - 1) * plot.width(), to_y(w["kg"])) for i, w in enumerate(history)]
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(GREEN, 2.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(GREEN)
        for point in points:
            painter.drawEllipse(point, 4, 4)
        painter.setPen(MUTED)
        painter.drawText(QPointF(plot.left(), plot.bottom() + 18), history[0]["date"][5:])
        painter.drawText(QRectF(plot.right() - 80, plot.bottom() + 6, 80, 16), Qt.AlignRight, history[-1]["date"][5:])

    def _page_food(self, painter, body, hover):
        food = self.summary["food"]
        goals = food["goals"]
        left = QRectF(body.left(), body.top(), body.width() * 0.3, body.height())
        meals = QRectF(left.right() + 12, body.top(), body.width() - left.width() - 12, body.height() * 0.62)
        week = QRectF(meals.left(), meals.bottom() + 12, meals.width(), body.height() - meals.height() - 12)
        y = self._card(painter, left, "HOY", GREEN)
        radius = min(56, left.width() / 4)
        self._ring(painter, QPointF(left.center().x(), y + radius + 14), radius, food["kcal"], goals["kcal"], "CALORÍAS", "kcal")
        self._ring(painter, QPointF(left.center().x(), y + radius * 3 + 70), radius, food["protein"], goals["protein"], "PROTEÍNA", "g")
        y = self._card(painter, meals, "COMIDAS DE HOY", GREEN)
        for meal in food["meals"]:
            if y > meals.bottom() - 40:
                break
            self._text(painter, meals.left() + 14, y + 20, f"{meal['time']} · {meal['meal'].upper()}", CYAN, SMALL)
            self._text(painter, meals.left() + 14, y + 40, meal["text"], WHITE, BODY, meals.width() - 200)
            self._text(painter, meals.right() - 170, y + 40, f"{meal['kcal']} kcal · {meal['protein']:.0f} g", GREEN, SMALL)
            y += 52
        if not food["meals"]:
            self._text(painter, meals.left() + 14, y + 24, "Di «almorcé un silpancho y una coca»", MUTED)
        y = self._card(painter, week, "ÚLTIMOS 7 DÍAS", GREEN)
        bar_w = (week.width() - 40) / 7
        top = max([d["kcal"] for d in food["week"]] + [goals["kcal"]])
        plot_h = week.bottom() - y - 30
        goal_y = week.bottom() - 22 - goals["kcal"] / top * plot_h
        for i, day in enumerate(food["week"]):
            h = day["kcal"] / top * plot_h
            bar = QRectF(week.left() + 20 + i * bar_w + 6, week.bottom() - 22 - h, bar_w - 12, h)
            painter.fillRect(bar, GREEN if day["kcal"] >= goals["kcal"] * 0.9 else CYAN)
            self._text(painter, bar.left(), week.bottom() - 6, day["date"][8:] + "/" + day["date"][5:7], MUTED, SMALL)
        painter.setPen(QPen(AMBER, 1.2, Qt.DashLine))
        painter.drawLine(QPointF(week.left() + 16, goal_y), QPointF(week.right() - 16, goal_y))

    def _page_habits(self, painter, body, hover):
        s = self.summary
        cells = self._grid(body, 2, 2)
        y = self._card(painter, cells[0], "HÁBITOS · RACHAS", GREEN)
        for habit in s["habits"][:int((cells[0].bottom() - y) // 32)]:
            self._check(painter, cells[0].left() + 6, y, cells[0].width() - 12, habit["name"], habit["done"],
                        ("habit", habit["id"], habit["done"]), hover, f"RACHA {habit['streak']} DÍAS", GREEN)
            y += 32
        y = self._card(painter, cells[1], "RUTINA DIARIA", CYAN)
        for item in s["routine"][:int((cells[1].bottom() - y) // 32)]:
            self._check(painter, cells[1].left() + 6, y, cells[1].width() - 12, item["text"], item["done"],
                        ("routine", item["id"], item["done"]), hover, item["time"] or "")
            y += 32
        y = self._card(painter, cells[2], "ÁNIMO · ÚLTIMA SEMANA", VIOLET_SOFT)
        step = (cells[2].width() - 24) / 7
        plot_h = cells[2].bottom() - y - 34
        for i, day in enumerate(s["mood"]["week"]):
            x = cells[2].left() + 12 + i * step
            if day["score"]:
                bar_h = plot_h * day["score"] / 5
                painter.fillRect(QRectF(x + 8, cells[2].bottom() - 26 - bar_h, step - 16, bar_h), faded(MOOD_COLORS[day["score"] - 1], 200))
                self._text(painter, x + step / 2 - 4, cells[2].bottom() - 30 - bar_h, str(day["score"]), WHITE, SMALL)
            self._text(painter, x + step / 2 - 14, cells[2].bottom() - 8, day["date"][8:] + "/" + day["date"][5:7], MUTED, SMALL)
        y = self._card(painter, cells[3], f"SUEÑO · META {s['sleep']['goal']} H · AGUA {s['water']['today']}/{s['water']['goal']}", CYAN)
        plot_h = cells[3].bottom() - y - 30
        for i, day in enumerate(s["sleep"]["week"]):
            hours = day["hours"] or 0
            h = min(1, hours / 12) * plot_h
            bar = QRectF(cells[3].left() + 12 + i * step + 6, cells[3].bottom() - 22 - h, step - 12, h)
            painter.fillRect(bar, GREEN if hours >= s["sleep"]["goal"] - 0.5 else AMBER)
            self._text(painter, bar.left(), cells[3].bottom() - 6, f"{hours:g}h" if hours else "—", MUTED, SMALL)

    def _page_money(self, painter, body, hover):
        money = self.summary["money"]
        left = QRectF(body.left(), body.top(), body.width() * 0.45, body.height())
        right = QRectF(left.right() + 12, body.top(), body.width() - left.width() - 12, body.height())
        y = self._card(painter, left, "ESTE MES", AMBER)
        self._text(painter, left.left() + 14, y + 44, f"{money['spent']:g} Bs", WHITE, QFont("Consolas", 28))
        self._text(painter, left.left() + 14, y + 66, f"gastados · ingresos {money['income']:g} Bs", MUTED, SMALL)
        y += 90
        top = max(money["categories"].values(), default=1)
        for name, amount in list(money["categories"].items())[:int((left.bottom() - y - 60) // 34)]:
            self._text(painter, left.left() + 14, y + 14, name.capitalize(), WHITE, SMALL)
            self._text(painter, left.right() - 90, y + 14, f"{amount:g} Bs", AMBER, SMALL)
            painter.fillRect(QRectF(left.left() + 14, y + 20, (left.width() - 28) * amount / top, 8), AMBER)
            y += 34
        goal = money["goal"]
        self._text(painter, left.left() + 14, left.bottom() - 34,
                   f"Ahorrado: {money['saved']:g} Bs" + (f" de {goal:g}" if goal else ""), GREEN, BODY_BOLD)
        if goal:
            painter.fillRect(QRectF(left.left() + 14, left.bottom() - 24, left.width() - 28, 8), faded(GREEN, 40))
            painter.fillRect(QRectF(left.left() + 14, left.bottom() - 24, (left.width() - 28) * min(1, money["saved"] / goal), 8), GREEN)
        y = self._card(painter, right, "ÚLTIMOS MOVIMIENTOS", AMBER)
        for item in reversed(money["recent"]):
            sign, color = {"gasto": ("−", AMBER), "ingreso": ("+", GREEN), "ahorro": ("AHORRO", CYAN)}[item["kind"]]
            self._text(painter, right.left() + 14, y + 20, item["date"][8:] + "/" + item["date"][5:7], MUTED, SMALL)
            self._text(painter, right.left() + 70, y + 20, (item["note"] or item["category"]).capitalize(), WHITE, BODY, right.width() - 200)
            self._text(painter, right.right() - 110, y + 20, f"{sign} {item['amount']:g} Bs", color, BODY_BOLD)
            y += 34
        self._text(painter, right.left() + 14, right.bottom() - 12, "Di «gasté 20 bolivianos en pasajes»", MUTED, SMALL)

    def _page_classes(self, painter, body, hover):
        s = self.summary
        rect = QRectF(body.left(), body.top(), body.width(), body.height())
        y = self._card(painter, rect, "HORARIO DE CLASES", CYAN)
        classes = s["classes"]["week"]
        days = 6 if not any(c["day"] == 6 for c in classes) else 7
        first = min([int(c["start"][:2]) for c in classes] + [7])
        last = max([int(c["end"][:2]) + 1 for c in classes] + [13])
        grid = QRectF(rect.left() + 56, y + 26, rect.width() - 68, rect.bottom() - y - 34)
        col = grid.width() / days
        hour_h = grid.height() / (last - first)
        today = datetime.now().weekday()
        for d in range(days):
            header = QRectF(grid.left() + d * col, y + 2, col, 20)
            self._text(painter, header.left() + 6, header.bottom() - 4, WEEK[d], GREEN if d == today else CYAN, SMALL)
            if d == today:
                painter.fillRect(QRectF(grid.left() + d * col, grid.top(), col, grid.height()), faded(GREEN, 14))
        for h in range(first, last + 1):
            line_y = grid.top() + (h - first) * hour_h
            painter.setPen(QPen(faded(CYAN, 25), 1))
            painter.drawLine(QPointF(grid.left(), line_y), QPointF(grid.right(), line_y))
            self._text(painter, rect.left() + 10, line_y + 4, f"{h:02d}:00", MUTED, SMALL)
        to_y = lambda hm: grid.top() + (int(hm[:2]) + int(hm[3:]) / 60 - first) * hour_h
        current = s["classes"]["now"]
        for cls in classes:
            if cls["day"] >= days:
                continue
            block = QRectF(grid.left() + cls["day"] * col + 3, to_y(cls["start"]), col - 6, to_y(cls["end"]) - to_y(cls["start"]))
            live = current and current["id"] == cls["id"]
            painter.setPen(QPen(GREEN if live else CYAN, 1.5))
            painter.setBrush(faded(GREEN if live else CYAN, 70 if live else 35))
            painter.drawRect(block)
            painter.setFont(BODY_BOLD)
            painter.setPen(WHITE)
            lines = [cls["subject"], f"{cls['start']}–{cls['end']}", f"Aula {cls['room']}" if cls["room"] else "",
                     cls["place"], cls["teacher"]]
            painter.save()
            painter.setClipRect(block)
            ly = block.top() + 16
            for i, line in enumerate(l for l in lines if l):
                painter.setFont(BODY_BOLD if i == 0 else SMALL)
                painter.setPen(WHITE if i == 0 else faded(WHITE, 200))
                painter.drawText(QPointF(block.left() + 6, ly), painter.fontMetrics().elidedText(line, Qt.ElideRight, int(block.width() - 10)))
                ly += 16 if i else 18
            painter.restore()
        if not classes:
            self._text(painter, grid.left() + 20, grid.center().y(),
                       "Di «agrega clase de Cálculo el lunes de 8 a 10 en el aula A12 con el ingeniero Rojas»", MUTED)

    def _page_calendar(self, painter, body, hover):
        s = self.summary
        today = datetime.fromisoformat(s["today"]).date()  # fecha sin hora, para comparar con los eventos
        left = QRectF(body.left(), body.top(), body.width() * 0.62, body.height())
        right = QRectF(left.right() + 12, body.top(), body.width() - left.width() - 12, body.height())
        y = self._card(painter, left, f"{MONTH_NAMES[today.month - 1]} {today.year}", CYAN)
        marks = {}
        for event in s["events"]:
            marks.setdefault(event["date"], []).append(CYAN)
        for holiday in s["holidays"]:
            marks.setdefault(holiday["date"], []).append(AMBER)
        col = (left.width() - 24) / 7
        for i, name in enumerate(WEEK):
            self._text(painter, left.left() + 12 + i * col + 6, y + 14, name, MUTED, SMALL)
        first = today.replace(day=1)
        rows = 6
        row_h = (left.bottom() - y - 30) / rows
        offset = first.weekday()
        days_in_month = ((first.replace(month=first.month % 12 + 1, year=first.year + first.month // 12)) - timedelta(days=1)).day
        for day in range(1, days_in_month + 1):
            index = offset + day - 1
            cell = QRectF(left.left() + 12 + (index % 7) * col, y + 24 + (index // 7) * row_h, col - 4, row_h - 4)
            iso = first.replace(day=day).isoformat()
            is_today = day == today.day
            painter.setPen(QPen(faded(GREEN if is_today else CYAN, 220 if is_today else 50), 1.5 if is_today else 1))
            painter.setBrush(faded(GREEN, 40) if is_today else Qt.NoBrush)
            painter.drawRect(cell)
            self._text(painter, cell.left() + 6, cell.top() + 16, str(day), WHITE if is_today else faded(WHITE, 190), SMALL)
            for j, color in enumerate(marks.get(iso, [])[:4]):
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(cell.left() + 10 + j * 12, cell.bottom() - 10), 4, 4)
        y = self._card(painter, right, "PRÓXIMOS", CYAN)
        items = [(e["date"], e["title"] + (f" · {e['time']}" if e["time"] else "") + (f" · {e['place']}" if e["place"] else ""), CYAN)
                 for e in s["events"]] + [(h["date"], h["name"], AMBER) for h in s["holidays"]]
        for day, text, color in sorted(items)[:int((right.bottom() - y) // 40)]:
            self._text(painter, right.left() + 14, y + 18, day[8:] + "/" + day[5:7], color, BODY_BOLD)
            self._text(painter, right.left() + 14, y + 36, text, WHITE, SMALL, right.width() - 28)
            y += 42

    def _page_ideas(self, painter, body, hover):
        maps = self.summary["maps"]
        if not maps:
            hud_frame(painter, body)
            self._text(painter, body.left() + 20, body.top() + 40, "Aún no tienes mapas.", WHITE, BODY_BOLD)
            self._text(painter, body.left() + 20, body.top() + 64,
                       "Di «crea un mapa de ideas sobre mi negocio» o «crea un diagrama de flujo de mi proyecto».", MUTED)
            return
        if self.map_id not in [m["id"] for m in maps]:
            self.map_id = maps[0]["id"]
        tab_w = min(220, (body.width() - (len(maps) - 1) * 6) / len(maps))
        for i, chart in enumerate(maps):
            icon = "FLUJO · " if chart["kind"] == "flujo" else "IDEAS · "
            self._button(painter, QRectF(body.left() + i * (tab_w + 6), body.top(), tab_w, 30), icon + chart["name"],
                         ("map", chart["id"]), hover, active=chart["id"] == self.map_id, accent=VIOLET_SOFT)
        chart = next(m for m in maps if m["id"] == self.map_id)
        self.canvas = QRectF(body.left() + 70, body.top() + 70, body.width() - 140, body.height() - 110)
        hud_frame(painter, QRectF(body.left(), body.top() + 40, body.width(), body.height() - 40), VIOLET_SOFT)
        nodes = {n["id"]: n for n in chart["nodes"]}
        for link in chart["links"]:
            if link["from"] in nodes and link["to"] in nodes:
                a, b = QPointF(*self._to_canvas(nodes[link["from"]])), QPointF(*self._to_canvas(nodes[link["to"]]))
                painter.setPen(QPen(faded(VIOLET_SOFT, 200), 2))
                painter.drawLine(a, b)
                if chart["kind"] == "flujo":  # flecha hacia el nodo de destino
                    angle = math.atan2(b.y() - a.y(), b.x() - a.x())
                    tip = QPointF(b.x() - math.cos(angle) * 34, b.y() - math.sin(angle) * 34)
                    for side in (-0.5, 0.5):
                        painter.drawLine(tip, QPointF(tip.x() - math.cos(angle + side) * 12, tip.y() - math.sin(angle + side) * 12))
                if link.get("label"):
                    self._text(painter, (a.x() + b.x()) / 2 + 6, (a.y() + b.y()) / 2 - 6, link["label"], AMBER, SMALL)
        for node in chart["nodes"]:
            x, y = self._to_canvas(node)
            painter.setFont(BODY_BOLD)
            width = max(110, painter.fontMetrics().horizontalAdvance(node["text"]) + 30)
            rect = QRectF(x - width / 2, y - 22, width, 44)
            grabbed = self.dragging and self.dragging[1] == node["id"]
            hot = hover is not None and rect.contains(QPointF(*hover))
            painter.setPen(QPen(AMBER if grabbed else VIOLET_SOFT, 2.5 if grabbed or hot else 1.6))
            painter.setBrush(QColor(20, 10, 40, 220))
            if node["shape"] == "diamond":
                path = QPainterPath(QPointF(x, y - 30))
                for px, py in ((x + width / 2 + 10, y), (x, y + 30), (x - width / 2 - 10, y)):
                    path.lineTo(QPointF(px, py))
                path.closeSubpath()
                painter.drawPath(path)
            elif node["shape"] == "oval":
                painter.drawRoundedRect(rect, 22, 22)
            else:
                painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(WHITE)
            painter.drawText(rect, Qt.AlignCenter, node["text"])
            self.buttons.append((rect, ("node", chart["id"], node["id"])))
        self._text(painter, body.left() + 12, body.bottom() - 6,
                   "Pellizca y arrastra un nodo para moverlo · di «agrega la idea … al mapa … conectada a …»", MUTED, SMALL)
