"""Los hologramas que se dibujan sobre la pantalla: esfera, sistema solar, globo terráqueo,
teclado, notas, menú radial, partículas, bola de energía, escáner de identidad y visualizador.

Solo dibuja y guarda estado visual; los gestos los decide gestures.Engine.
"""
import json
import math
import random
import time
import urllib.request
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient

from .paths import MODELS_DIR

CYAN = QColor(79, 216, 255)
AMBER = QColor(255, 181, 71)
RED = QColor(255, 77, 94)
GREEN = QColor(90, 255, 180)
WHITE = QColor(239, 252, 255)
MUTED = QColor(111, 157, 179)
PANEL = QColor(2, 14, 24, 190)
FONT = QFont("Consolas", 11)
SMALL = QFont("Consolas", 9)
BIG = QFont("Consolas", 18)


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

ROWS = ["1234567890", "qwertyuiop", "asdfghjklñ", "⇧zxcvbnm,.⌫", "␣↵"]


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
            if row == "␣↵":
                self.keys.append((QRectF(left + key_w * 2, top + r * key_h, key_w * 6.5, key_h - 6), "␣"))
                self.keys.append((QRectF(left + key_w * 8.7, top + r * key_h, key_w * 2.3, key_h - 6), "↵"))
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
        if key == "⇧":
            self.shift = not self.shift
        elif key == "⌫":
            self.press_keys("backspace")
        elif key == "↵":
            self.press_keys("enter")
        elif key == "␣":
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
            pressed = now - self.flash.get(key, 0) < 0.18 or (key == "⇧" and self.shift)
            painter.setPen(QPen(faded(CYAN, 230 if hot else 110), 1.5))
            painter.setBrush(faded(CYAN, 150 if pressed else 55 if hot else 18))
            painter.drawRoundedRect(rect, 4, 4)
            label = {"␣": "ESPACIO", "↵": "ENTER", "⌫": "BORRAR", "⇧": "MAYÚS"}.get(key, key.upper() if self.shift else key)
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
