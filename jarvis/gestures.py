"""Gestos de las manos: cursor, clic, doble clic, clic derecho, mover y estirar ventanas,
scroll, maximizar, minimizar, mostrar el escritorio, cambiar de ventana o de pestaña,
atrás y adelante, y acoplar ventanas a los bordes.

No sabe nada de cámaras ni de Windows: recibe manos ya ubicadas en la pantalla y actúa
a través de los objetos `windows` y `cursor`, así se puede probar sin hardware.
"""
import math
from dataclasses import dataclass

PINCH_ON = 0.30  # distancia pulgar-índice relativa al tamaño de la mano
PINCH_OFF = 0.45
HOLD_TO_GRAB = 0.35  # segundos pellizcando sobre una ventana para agarrarla
CLICK_SLOP = 30  # píxeles que se tolera mover la mano en un clic
MIN_WIDTH = 320
MIN_HEIGHT = 220
MAX_SCALE = 4.0
POSE_SETTLE = 0.15  # segundos que una postura debe mantenerse para contar
FIST_TO_MINIMIZE = 0.6
OPEN_AFTER_FIST = 0.6  # segundos para abrir la palma tras un puño corto y maximizar
DOUBLE_CLICK_TIME = 0.5
FLASH_SECONDS = 1.2  # cuánto se ve en pantalla el aviso de una acción
PALMS_TO_DESKTOP = 1.0
SCROLL_DEAD_ZONE = 30  # píxeles que puedes mover la mano sin que haga scroll
SCROLL_SPEED = 20  # cada 20 píxeles más lejos del punto de inicio, un paso más por segundo
SCROLL_MAX = 25  # pasos de rueda por segundo, como máximo
SWIPE_TIME = 0.35
SWIPE_DISTANCE = 0.25  # fracción del ancho de la pantalla
SWIPE_COOLDOWN = 1.0
SNAP_EDGE = 40  # píxeles desde el borde para acoplar al soltar
ERASE_FIST = 0.4  # en modo dibujo, el puño borra
MAX_STROKES = 80
GLOBE_DRAG = 0.006  # radianes por píxel al girar la esfera
GLOBE_IDLE_SPIN = 0.35  # radianes por segundo cuando nadie la toca
KNOB_TURN = math.pi  # media vuelta de muñeca = volumen de 0 a 100
MENU_INNER = 70  # píxeles desde el centro del menú radial para elegir una opción
MENU_TIMEOUT = 6.0
TAP_TIME = 0.35  # un pellizco más corto que esto, sin mover la mano, es un toque


@dataclass
class HandInput:
    id: str
    point: tuple[float, float]  # en píxeles físicos de pantalla
    ratio: float  # distancia pulgar-índice / tamaño de la mano
    pose: str = "other"  # "palm", "fist", "two", "three", "shaka", "rock" u "other"
    middle_ratio: float = 9.9  # distancia pulgar-medio / tamaño de la mano (clic derecho)
    angle: float = 0.0  # giro de la mano en la pantalla, en radianes (perilla de volumen)


def distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pinch_ratio(points: list[tuple[float, float]]) -> float:
    """points: los 21 puntos de MediaPipe en píxeles."""
    return distance(points[4], points[8]) / max(distance(points[0], points[9]), 1e-6)


def middle_pinch_ratio(points: list[tuple[float, float]]) -> float:
    return distance(points[4], points[12]) / max(distance(points[0], points[9]), 1e-6)


def hand_angle(points: list[tuple[float, float]]) -> float:
    """Dirección de la muñeca a los nudillos del medio. Crece al girar la mano en sentido horario."""
    return math.atan2(points[9][1] - points[0][1], points[9][0] - points[0][0])


def pinch_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Punto medio entre pulgar e índice: no salta al cerrar el pellizco."""
    return ((points[4][0] + points[8][0]) / 2, (points[4][1] + points[8][1]) / 2)


def hand_pose(points: list[tuple[float, float]]) -> str:
    """Postura de la mano según qué dedos están estirados."""
    wrist = points[0]

    def extended(tip, joint):
        return distance(points[tip], wrist) > distance(points[joint], wrist) * 1.1

    def folded(tip, joint):
        return distance(points[tip], wrist) < distance(points[joint], wrist)

    fingers = [(8, 6), (12, 10), (16, 14), (20, 18)]
    if all(folded(tip, joint) for tip, joint in fingers):
        return "fist"
    if all(extended(tip, joint) for tip, joint in fingers):
        thumb_out = distance(points[4], points[17]) > distance(points[2], points[17]) * 1.2
        return "palm" if thumb_out else "other"
    if extended(8, 6) and extended(12, 10) and extended(16, 14) and folded(20, 18):
        return "three"
    thumb_out = distance(points[4], points[5]) > distance(points[0], points[9]) * 0.6
    if folded(8, 6) and folded(12, 10) and folded(16, 14) and extended(20, 18) and thumb_out:
        return "shaka"  # pulgar y meñique: la perilla de volumen
    if extended(8, 6) and folded(12, 10) and folded(16, 14) and extended(20, 18):
        return "rock"  # índice y meñique: el menú radial
    if extended(8, 6) and extended(12, 10) and folded(16, 14) and folded(20, 18) and pinch_ratio(points) > PINCH_OFF:
        return "two"
    return "other"


class OneEuro:
    """Filtro 1€: quita el temblor en reposo sin añadir retraso a los movimientos rápidos."""

    def __init__(self, min_cutoff=1.2, beta=0.004, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.value = self.speed = self.time = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1 / (2 * math.pi * cutoff)
        return 1 / (1 + tau / dt)

    def __call__(self, value: float, now: float) -> float:
        if self.time is None or now <= self.time:
            self.value, self.speed, self.time = value, 0.0, now
            return value
        dt = now - self.time
        speed = (value - self.value) / dt
        self.speed += self._alpha(self.d_cutoff, dt) * (speed - self.speed)
        cutoff = self.min_cutoff + self.beta * abs(self.speed)
        self.value += self._alpha(cutoff, dt) * (value - self.value)
        self.time = now
        return self.value


class Engine:
    def __init__(self, windows, cursor, keys=None, work_area=None, volume=None, ui=None, menu=None):
        """keys pulsa un atajo como "alt+tab". work_area: (x, y, ancho, alto) sin la barra de tareas.
        volume: objeto con get() y set(nivel de 0 a 1).
        ui: elementos flotantes que se pellizcan (teclado, notas), con hit, press, drag, release y fist.
        menu: (cantidad de opciones, función que abre la opción n) para el menú radial."""
        self.windows = windows
        self.volume = volume
        self.ui = ui
        self.menu_items, self.open_item = menu or (0, None)
        self.menu = None  # {"center", "selected", "since"} mientras el menú radial está abierto
        self.effects_mode = False
        self.tap = None  # (punto, cuándo) del último toque sobre un objeto 3D
        self.draw_mode = False
        self.globe_mode = False
        self.strokes = []  # trazos del modo dibujo, en píxeles de pantalla
        self.globe = {"yaw": 0.0, "pitch": 0.35, "scale": 1.0, "spin": GLOBE_IDLE_SPIN, "tilt": 0.0}
        self.knob = None  # (punto, nivel) mientras se gira la perilla
        self.angles = {}
        self._last_update = None
        self.cursor = cursor
        self.keys = keys or (lambda combo: None)
        self.work_area = work_area
        self.mode = "idle"
        self.status = ""
        self.primary = None
        self.pinching = {}
        self.right_pinching = {}
        self.points = {}
        self.poses = {}
        self._filters = {}
        self._trail = []
        self._trail_pose = None
        self._minimized = []  # ventanas minimizadas con el puño, la última al final
        self._cooldown_until = 0.0
        self._flash_until = 0.0
        self._cursor_point = None
        self._fist_start = None
        self._fist_point = None
        self._fist_opened = None
        self._last_click = None
        self._palms_since = None
        self._palms_fired = False
        self._hidden_windows = []

    def update(self, hands: list[HandInput], now: float) -> None:
        started = self._read_hands(hands, now)
        for hand in hands:
            self.angles[hand.id] = hand.angle
        dt = 0.0 if self._last_update is None else min(0.2, now - self._last_update)
        self._last_update = now
        if self.globe_mode:
            self._globe_physics(dt)
        handler = getattr(self, "_" + self.mode)
        handler(started, now)

    def _read_hands(self, hands, now) -> set:
        """Devuelve qué manos empezaron un pellizco: "R" para índice, ("R", "right") para el medio."""
        started = set()
        seen = set()
        for hand in hands:
            seen.add(hand.id)
            fx, fy = self._filters.setdefault(hand.id, (OneEuro(), OneEuro()))
            self.points[hand.id] = (fx(hand.point[0], now), fy(hand.point[1], now))
            pose, since = self.poses.get(hand.id, (None, now))
            if hand.pose != pose:
                since = now
            self.poses[hand.id] = (hand.pose, since)
            was = self.pinching.get(hand.id, False)
            # Al cerrar el puño, el pulgar toca el índice: eso no es un pellizco.
            now_pinching = hand.pose != "fist" and hand.ratio < (PINCH_OFF if was else PINCH_ON)
            self.pinching[hand.id] = now_pinching
            if now_pinching and not was:
                started.add(hand.id)
            # Clic derecho: pulgar con el medio, con el índice bien separado del pulgar.
            was_right = self.right_pinching.get(hand.id, False)
            if was_right:
                right = hand.pose != "fist" and not now_pinching and hand.middle_ratio < PINCH_OFF
            else:
                right = (hand.pose != "fist" and not now_pinching and hand.middle_ratio < PINCH_ON
                         and hand.ratio > PINCH_OFF)
            self.right_pinching[hand.id] = right
            if right and not was_right:
                started.add((hand.id, "right"))
        for gone in set(self.points) - seen:
            del self.points[gone]
            self.pinching.pop(gone, None)
            self.right_pinching.pop(gone, None)
            self.poses.pop(gone, None)
            self._filters.pop(gone, None)
        return started

    def _holding(self, hand_id) -> bool:
        return hand_id in self.points and self.pinching.get(hand_id, False)

    def _pose(self, hand_id, now) -> str:
        """La postura de la mano, solo si ya se mantuvo un momento (evita parpadeos)."""
        pose, since = self.poses.get(hand_id, ("other", now))
        return pose if now - since >= POSE_SETTLE else "settling"

    def _other(self):
        return next((hand_id for hand_id in self.points if hand_id != self.primary), None)

    def _flash(self, text, now):
        self.status = text
        self._flash_until = now + FLASH_SECONDS

    def _move_cursor(self, point):
        self.cursor.move(*point)
        self._cursor_point = point

    def _idle(self, started, now):
        if now >= self._flash_until:
            self.status = ""
        if not self.points:
            return
        pinched = [hand for hand in started if not isinstance(hand, tuple)]
        right = [hand[0] for hand in started if isinstance(hand, tuple)]
        if pinched or right:
            self.primary = (pinched or right)[0]
        elif self.primary not in self.points:
            self.primary = next(iter(self.points))
        point = self.points[self.primary]
        if self.menu is not None:
            return self._menu_idle(pinched, point, now)
        if self.ui is not None and self.primary in pinched:
            token = self.ui.hit(point)
            if token is not None:
                self.ui.press(token, point)
                self.ui_token, self.mode = token, "ui_holding"
                return
        if self.draw_mode:
            return self._draw_idle(pinched, point, now)
        if self.globe_mode:
            return self._globe_idle(pinched, point, now)
        if self._both_palms(now) or now < self._cooldown_until:
            return
        pose = self._pose(self.primary, now)
        raw_pose, since = self.poses[self.primary]
        if self._cursor_point is None:
            self._cursor_point = point

        # Puño: mantenerlo minimiza; cerrarlo un instante y abrir la palma maximiza.
        if pose == "fist":
            if self._fist_start is None:
                self._fist_start, self._fist_point = since, self._cursor_point
            if now - self._fist_start >= FIST_TO_MINIMIZE:
                target = self.windows.at(*self._fist_point)
                if self.ui is not None and self.ui.fist(self._fist_point):
                    self.status = "BORRADO"
                elif target is not None:
                    self.windows.minimize(target)
                    self._minimized.append(target)
                    self.status = "VENTANA MINIMIZADA"
                self._fist_start = None
                self.mode = "fist_done"
            return
        if self._fist_start is not None and raw_pose != "fist":
            self._fist_opened = (now, self._fist_point)
            self._fist_start = None
        if self._fist_opened and now - self._fist_opened[0] > OPEN_AFTER_FIST:
            self._fist_opened = None
        if self._fist_opened:
            if pose == "palm":
                self._toggle_maximize(self._fist_opened[1], now)
                self._fist_opened = None
            # Al abrir la mano el punto entre pulgar e índice salta: el cursor espera.
            return

        if pose == "rock" and self.menu_items:
            self.menu = {"center": point, "selected": None, "since": now}
            self.status = "MENÚ: APUNTA Y PELLIZCA"
            return
        if pose == "shaka" and self.volume is not None:
            self.mode = "volume"
            self.knob_angle, self.knob_turned = self.angles.get(self.primary, 0.0), 0.0
            self.knob_start = self.volume.get()
            self.knob = (point, self.knob_start)
            return
        if pose == "two" and not self.pinching.get(self.primary):
            self.mode = "scrolling"
            self.scroll_anchor, self.scroll_rest, self.scroll_time = point, 0.0, now
            self._trail = []
            return
        if self.primary in right:
            self.mode = "right_pressing"
            self.press_point, self.press_hand, self.press_time = self._cursor_point, point, now
            return
        self._move_cursor(point)
        if pose in ("palm", "three") and self._swiped(point, now, pose):
            return
        if self.primary in pinched:
            self.mode = "pressing"
            self.press_time, self.press_point = now, point
            self.target = self.windows.at(*point)

    def _ui_holding(self, started, now):
        if not self._holding(self.primary):
            self.ui.release(self.ui_token, self.points.get(self.primary))
            self.mode = "idle"
            return
        point = self.points[self.primary]
        self._move_cursor(point)
        self.ui.drag(self.ui_token, point)

    def _menu_idle(self, pinched, point, now):
        """Menú radial: apuntas hacia una opción alejando la mano del centro y pellizcas."""
        menu = self.menu
        self._move_cursor(point)
        dx, dy = point[0] - menu["center"][0], point[1] - menu["center"][1]
        if math.hypot(dx, dy) >= MENU_INNER:
            turn = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)  # 0 arriba, crece en sentido horario
            slice_ = 2 * math.pi / self.menu_items
            menu["selected"] = int(((turn + slice_ / 2) % (2 * math.pi)) // slice_)
        else:
            menu["selected"] = None
        if self.primary in pinched:
            if menu["selected"] is not None:
                self.open_item(menu["selected"])
                self._flash("ABRIENDO", now)
                self._cooldown_until = now + 0.6
            self.menu = None
            self.mode = "pressing_ignored"
        elif self._pose(self.primary, now) == "fist" or (menu["selected"] is None and now - menu["since"] > MENU_TIMEOUT):
            self.menu = None
            self.status = ""

    def _pressing_ignored(self, started, now):
        """El pellizco que eligió en el menú no debe hacer además un clic."""
        if not self._holding(self.primary):
            self.mode = "idle"

    def _toggle_maximize(self, point, now):
        """Sobre una ventana: maximizarla o restaurarla. Fuera de ventanas: traer la última minimizada."""
        target = self.windows.at(*point)
        if target is None:
            self._bring_back_minimized(now)
            return
        if self.windows.is_maximized(target):
            self.windows.restore(target)
            self._flash("VENTANA RESTAURADA", now)
        else:
            self.windows.maximize(target)
            self._flash("VENTANA MAXIMIZADA", now)
        self._cooldown_until = now + 0.5

    def _bring_back_minimized(self, now):
        while self._minimized:
            hwnd = self._minimized.pop()
            if self.windows.is_minimized(hwnd):
                break
        else:
            hwnd = self.windows.last_minimized()  # minimizada de otra forma, por ejemplo con el mouse
        if hwnd is None:
            return
        self.windows.restore(hwnd)
        self.windows.bring_to_front(hwnd)
        self._flash("VENTANA DE VUELTA", now)
        self._cooldown_until = now + 0.5

    def _both_palms(self, now) -> bool:
        """Las dos manos abiertas un segundo: minimizar todo; otra vez, devolverlo.

        Se dispara una sola vez: para repetirlo hay que bajar o cerrar una mano antes.
        """
        if self.effects_mode:
            return False  # con los efectos, las dos palmas hacen la bola de energía
        palms = len(self.points) >= 2 and all(self._pose(hand_id, now) == "palm" for hand_id in self.points)
        if not palms:
            self._palms_since = None
            self._palms_fired = False
            return False
        if self._palms_fired:
            return True
        if self._palms_since is None:
            self._palms_since = now
        elif now - self._palms_since >= PALMS_TO_DESKTOP:
            if self._hidden_windows:
                self.windows.restore_all(self._hidden_windows)
                self._hidden_windows = []
                self.status = "VENTANAS DE VUELTA"
            else:
                self._hidden_windows = self.windows.minimize_all()
                self.status = "ESCRITORIO"
            self._palms_fired = True
        return True

    SWIPES = {
        # postura: (hacia tu derecha, hacia tu izquierda, aviso derecha, aviso izquierda)
        "palm": ("alt+tab", "alt+shift+tab", "CAMBIO DE VENTANA", "CAMBIO DE VENTANA"),
        "three": ("ctrl+tab", "ctrl+shift+tab", "PESTAÑA SIGUIENTE", "PESTAÑA ANTERIOR"),
        "two": ("alt+left", "alt+right", "ATRÁS", "ADELANTE"),
    }

    def _swiped(self, point, now, pose) -> bool:
        """Barrido rápido de lado: la acción depende de la postura de la mano."""
        if pose != self._trail_pose:
            self._trail, self._trail_pose = [], pose
        self._trail = [(t, x, y) for t, x, y in self._trail if now - t <= SWIPE_TIME] + [(now, *point)]
        width = self.work_area[2] if self.work_area else 1920
        _, x0, y0 = self._trail[0]
        dx, dy = point[0] - x0, point[1] - y0
        if abs(dx) < width * SWIPE_DISTANCE or abs(dy) > abs(dx) * 0.5:
            return False
        to_right, to_left, said_right, said_left = self.SWIPES[pose]
        self.keys(to_right if dx > 0 else to_left)
        self._flash(said_right if dx > 0 else said_left, now)
        self._trail = []
        self._cooldown_until = now + SWIPE_COOLDOWN
        return True

    def _scrolling(self, started, now):
        """Dos dedos: como un joystick. Cuanto más alejes la mano del punto de inicio, más rápido."""
        if self.primary not in self.points or self._pose(self.primary, now) not in ("two", "settling"):
            self.mode = "idle"
            self.status = ""
            return
        point = self.points[self.primary]
        if self._swiped(point, now, "two"):
            self.mode = "idle"
            return
        dt, self.scroll_time = now - self.scroll_time, now
        offset = self.scroll_anchor[1] - point[1]  # positivo: la mano subió
        beyond = abs(offset) - SCROLL_DEAD_ZONE
        if beyond <= 0:
            self.status = "SCROLL: SUBE O BAJA LA MANO"
            self.scroll_rest = 0.0
            return
        direction = 1 if offset > 0 else -1
        self.status = "SCROLL ARRIBA" if direction > 0 else "SCROLL ABAJO"
        self.scroll_rest += direction * min(SCROLL_MAX, beyond / SCROLL_SPEED) * dt
        steps = int(self.scroll_rest)
        if steps:
            self.cursor.scroll(steps)
            self.scroll_rest -= steps

    def _right_pressing(self, started, now):
        if self.primary not in self.points or self.poses[self.primary][0] == "fist":
            self.mode = "idle"  # cerrar el puño pasa por aquí: no es un clic derecho
            return
        if not self.right_pinching.get(self.primary):
            if distance(self.points[self.primary], self.press_hand) <= CLICK_SLOP * 2:
                self.cursor.right_click(*self.press_point)
                self._flash("CLIC DERECHO", now)
            self.mode = "idle"

    # Perilla de volumen: pulgar y meñique estirados, y girar la mano.

    def _volume(self, started, now):
        if self.primary not in self.points or self._pose(self.primary, now) not in ("shaka", "settling"):
            self.mode = "idle"
            self.knob = None
            return
        angle = self.angles.get(self.primary, self.knob_angle)
        turn = (angle - self.knob_angle + math.pi) % (2 * math.pi) - math.pi  # sin saltos al pasar de 180°
        self.knob_angle = angle
        self.knob_turned += turn
        level = min(1.0, max(0.0, self.knob_start + self.knob_turned / KNOB_TURN))
        if self.knob is None or abs(level - self.knob[1]) >= 0.01:
            self.volume.set(level)
        self.knob = (self.points[self.primary], level)
        self.status = f"VOLUMEN {round(level * 100)}%"

    # Modo dibujo: pellizcar dibuja, el puño borra.

    def _draw_idle(self, pinched, point, now):
        self._move_cursor(point)
        pose = self._pose(self.primary, now)
        if pose == "fist" and now - self.poses[self.primary][1] >= ERASE_FIST:
            if self.strokes:
                self.strokes = []
                self._flash("DIBUJO BORRADO", now)
            self.mode = "fist_done"
            return
        if self.primary in pinched:
            self.strokes = (self.strokes + [[point]])[-MAX_STROKES:]
            self.mode = "drawing"
            self.status = "DIBUJANDO"

    def _drawing(self, started, now):
        if not self._holding(self.primary):
            self.mode = "idle"
            self.status = ""
            return
        point = self.points[self.primary]
        self._move_cursor(point)
        if distance(point, self.strokes[-1][-1]) >= 4:
            self.strokes[-1].append(point)

    # Esfera holográfica: pellizcar y arrastrar la gira, con dos manos se agranda.

    def _globe_idle(self, pinched, point, now):
        self._move_cursor(point)
        if self.primary in pinched:
            self.mode = "globe_rotating"
            self.globe_last, self.globe_last_time = point, now
            self.globe_pressed, self.globe_moved = (point, now), 0.0
            self.status = "GIRANDO ESFERA"

    def _globe_rotating(self, started, now):
        if not self._holding(self.primary):
            press_point, pressed_at = self.globe_pressed
            if now - pressed_at <= TAP_TIME and self.globe_moved <= CLICK_SLOP:
                self.tap = (press_point, now)
            self.mode = "idle"
            self.status = ""
            return
        point = self.points[self.primary]
        other = self._other()
        if other in started:
            self.second = other
            self.start_distance = max(distance(point, self.points[other]), 1)
            self.start_scale = self.globe["scale"]
            self.mode = "globe_scaling"
            self.status = "AGRANDANDO ESFERA"
            return
        dx, dy = point[0] - self.globe_last[0], point[1] - self.globe_last[1]
        dt = max(1 / 120, now - self.globe_last_time)
        self.globe_moved += math.hypot(dx, dy)
        self.globe_last, self.globe_last_time = point, now
        self.globe["yaw"] += dx * GLOBE_DRAG
        self.globe["pitch"] = min(1.4, max(-1.4, self.globe["pitch"] + dy * GLOBE_DRAG))
        # Al soltar sigue girando con el impulso que le diste.
        self.globe["spin"] = self.globe["spin"] * 0.6 + (dx * GLOBE_DRAG / dt) * 0.4
        self._move_cursor(point)

    def _globe_scaling(self, started, now):
        if not (self._holding(self.primary) and self._holding(self.second)):
            self.mode = "globe_rotating" if self._holding(self.primary) else "idle"
            if self.mode == "globe_rotating":
                self.globe_last, self.globe_last_time = self.points[self.primary], now
            else:
                self.status = ""
            return
        ratio = distance(self.points[self.primary], self.points[self.second]) / self.start_distance
        self.globe["scale"] = min(3.0, max(0.4, self.start_scale * ratio))

    def _globe_physics(self, dt):
        globe = self.globe
        grabbed = self.mode in ("globe_rotating", "globe_scaling")
        if not grabbed:
            globe["yaw"] += globe["spin"] * dt
            # El impulso se apaga poco a poco hasta volver al giro lento de siempre.
            globe["spin"] += (globe.get("idle", GLOBE_IDLE_SPIN) - globe["spin"]) * min(1.0, dt * 0.8)
        globe["tilt"] += dt * 0.6

    def _fist_done(self, started, now):
        if self.primary not in self.points or self.poses[self.primary][0] != "fist":
            self.mode = "idle"
            self.status = ""

    def _pressing(self, started, now):
        if self.primary in self.points and self.poses[self.primary][0] == "fist":
            self.mode = "idle"  # cerrar el puño pasa por un pellizco: no es un clic
            return
        if not self._holding(self.primary):
            if self.primary in self.points and distance(self.points[self.primary], self.press_point) <= CLICK_SLOP:
                self._click(now)
            self.mode = "idle"
            return
        point = self.points[self.primary]
        self.cursor.move(*point)
        moved = distance(point, self.press_point) > CLICK_SLOP * 2
        if now - self.press_time >= HOLD_TO_GRAB or moved:
            if self.target is None:
                self.mode = "holding_nothing"
            else:
                self._start_drag(point, restore=True)

    def _click(self, now):
        """Dos clics seguidos cerca caen en el mismo punto, para que Windows los tome como doble clic."""
        point = self.press_point
        last = self._last_click
        if last and now - last[0] <= DOUBLE_CLICK_TIME and distance(point, last[1]) <= CLICK_SLOP * 1.5:
            point = last[1]
            self._flash("DOBLE CLIC", now)
            self._last_click = None
        else:
            self._last_click = (now, point)
        self.cursor.click(*point)

    def _holding_nothing(self, started, now):
        if not self._holding(self.primary):
            self.mode = "idle"
        else:
            self.cursor.move(*self.points[self.primary])

    def _start_drag(self, point, restore=False):
        x, y, width, height = self.windows.rect(self.target)
        if restore and self.windows.is_maximized(self.target):
            # Al restaurar, la ventana cambia de tamaño: se conserva el punto relativo agarrado.
            fx, fy = (point[0] - x) / width, (point[1] - y) / height
            self.windows.restore(self.target)
            x, y, width, height = self.windows.rect(self.target)
            self.offset = (fx * width, min(fy * height, 40))
        else:
            self.offset = (point[0] - x, point[1] - y)
        self.windows.bring_to_front(self.target)
        self.mode = "dragging"
        self.status = "MOVIENDO VENTANA"

    def _dragging(self, started, now):
        if not self._holding(self.primary):
            if self.primary in self.points:
                self._snap(self.points[self.primary])
            self.mode = "idle"
            self.status = ""
            return
        point = self.points[self.primary]
        other = self._other()
        if other in started:
            self.second = other
            self.start_distance = max(distance(point, self.points[other]), 1)
            self.start_mid = self._mid(point, self.points[other])
            self.start_rect = self.windows.rect(self.target)
            self.mode = "resizing"
            self.status = "ESTIRANDO VENTANA"
            return
        _, _, width, height = self.windows.rect(self.target)
        self.windows.set_rect(self.target, round(point[0] - self.offset[0]), round(point[1] - self.offset[1]), width, height)
        self.cursor.move(*point)

    def _resizing(self, started, now):
        if not (self._holding(self.primary) and self._holding(self.second)):
            if self._holding(self.primary):
                self._start_drag(self.points[self.primary])
            else:
                self.mode = "idle"
                self.status = ""
            return
        a, b = self.points[self.primary], self.points[self.second]
        scale = min(max(distance(a, b) / self.start_distance, 1 / MAX_SCALE), MAX_SCALE)
        x0, y0, w0, h0 = self.start_rect
        mid = self._mid(a, b)
        width = max(MIN_WIDTH, round(w0 * scale))
        height = max(MIN_HEIGHT, round(h0 * scale))
        center_x = x0 + w0 / 2 + mid[0] - self.start_mid[0]
        center_y = y0 + h0 / 2 + mid[1] - self.start_mid[1]
        self.windows.set_rect(self.target, round(center_x - width / 2), round(center_y - height / 2), width, height)

    def _snap(self, point):
        """Soltar una ventana en un borde la acopla: mitad izquierda, mitad derecha o maximizada."""
        if not self.work_area:
            return
        left, top, width, height = self.work_area
        if point[0] <= left + SNAP_EDGE:
            self.windows.set_rect(self.target, left, top, width // 2, height)
        elif point[0] >= left + width - SNAP_EDGE:
            self.windows.set_rect(self.target, left + width // 2, top, width - width // 2, height)
        elif point[1] <= top + SNAP_EDGE:
            self.windows.maximize(self.target)

    @staticmethod
    def _mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
