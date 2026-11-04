from jarvis import gestures, tools
from jarvis.gestures import Engine, HandInput, hand_pose

OPEN, PINCH = 0.8, 0.1


class FakeWindows:
    def __init__(self, rect=(100, 100, 800, 600), maximized=False):
        self.rects = {"win": rect}
        self.maximized = maximized

    def at(self, x, y):
        if self.hidden:
            return None
        left, top, width, height = self.rects["win"]
        return "win" if left <= x < left + width and top <= y < top + height else None

    def rect(self, hwnd):
        return self.rects[hwnd]

    def is_maximized(self, hwnd):
        return self.maximized

    def restore(self, hwnd):
        self.maximized = False
        self.hidden = False
        self.rects[hwnd] = (300, 200, 1000, 700)

    def bring_to_front(self, hwnd):
        pass

    def set_rect(self, hwnd, x, y, width, height):
        self.rects[hwnd] = (x, y, width, height)

    def minimize(self, hwnd):
        self.minimized = hwnd
        self.hidden = True

    hidden = False

    def is_minimized(self, hwnd):
        return self.hidden

    def last_minimized(self):
        return None

    minimize_all_calls = 0
    restored = []

    def minimize_all(self):
        self.minimize_all_calls += 1
        return ["a", "b"]

    def restore_all(self, hwnds):
        self.restored = list(hwnds)

    def maximize(self, hwnd):
        self.maximized = True


class FakeCursor:
    def __init__(self):
        self.position = None
        self.clicks = []
        self.scrolled = 0
        self.right_clicks = []

    def move(self, x, y):
        self.position = (x, y)

    def click(self, x, y):
        self.clicks.append((round(x), round(y)))

    def scroll(self, steps):
        self.scrolled += steps

    def right_click(self, x, y):
        self.right_clicks.append((round(x), round(y)))


def run(engine, steps, start=0.0, dt=1 / 30):
    """steps: lista de listas de (id, (x, y), ratio[, postura]). Cada paso es un cuadro de cámara."""
    now = start
    for hands in steps:
        engine.update([HandInput(*hand) for hand in hands], now)
        now += dt
    return now


def hold(hand_id, point, ratio, frames):
    return [[(hand_id, point, ratio)]] * frames


def test_quick_pinch_clicks_where_it_started():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    run(engine, hold("R", (400, 300), OPEN, 10) + hold("R", (400, 300), PINCH, 3) + hold("R", (402, 301), OPEN, 3))
    assert cursor.clicks == [(400, 300)]


def test_pinch_and_hold_moves_the_window():
    windows = FakeWindows(rect=(100, 100, 800, 600))
    engine = Engine(windows, FakeCursor())
    now = run(engine, hold("R", (400, 300), OPEN, 10) + hold("R", (400, 300), PINCH, 15))
    assert engine.mode == "dragging"
    now = run(engine, hold("R", (900, 700), PINCH, 60), start=now)
    x, y, width, height = windows.rects["win"]
    assert (width, height) == (800, 600)
    assert abs(x - 600) < 5 and abs(y - 500) < 5  # se movió lo mismo que la mano
    run(engine, hold("R", (900, 700), OPEN, 3), start=now)
    assert engine.mode == "idle"


def test_holding_a_window_does_not_click():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 20) + hold("R", (400, 300), OPEN, 3))
    assert cursor.clicks == []


def test_two_hands_stretch_the_window():
    windows = FakeWindows(rect=(100, 100, 800, 600))
    engine = Engine(windows, FakeCursor())
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 15))
    now = run(engine, [[("R", (400, 300), PINCH), ("L", (600, 300), OPEN)]] * 10, start=now)
    now = run(engine, [[("R", (400, 300), PINCH), ("L", (600, 300), PINCH)]] * 3, start=now)
    assert engine.mode == "resizing"
    run(engine, [[("R", (300, 300), PINCH), ("L", (700, 300), PINCH)]] * 60, start=now)
    _, _, width, height = windows.rects["win"]
    assert 1500 < width < 1700 and 1100 < height < 1300  # manos al doble de distancia


def test_window_never_shrinks_below_minimum():
    windows = FakeWindows(rect=(100, 100, 800, 600))
    engine = Engine(windows, FakeCursor())
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 15))
    now = run(engine, [[("R", (400, 300), PINCH), ("L", (800, 300), OPEN)]] * 10, start=now)
    now = run(engine, [[("R", (400, 300), PINCH), ("L", (800, 300), PINCH)]] * 3, start=now)
    run(engine, [[("R", (590, 300), PINCH), ("L", (610, 300), PINCH)]] * 60, start=now)
    _, _, width, height = windows.rects["win"]
    assert width == gestures.MIN_WIDTH and height == gestures.MIN_HEIGHT


def test_maximized_window_is_restored_under_the_hand():
    windows = FakeWindows(rect=(0, 0, 2560, 1400), maximized=True)
    engine = Engine(windows, FakeCursor())
    now = run(engine, hold("R", (1280, 20), OPEN, 5) + hold("R", (1280, 20), PINCH, 15))
    run(engine, hold("R", (1280, 20), PINCH, 5), start=now)
    x, y, width, height = windows.rects["win"]
    assert not windows.maximized and (width, height) == (1000, 700)
    assert x <= 1280 < x + width and y <= 20 < y + height


def test_losing_the_hand_releases_the_window():
    engine = Engine(FakeWindows(), FakeCursor())
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 15))
    run(engine, [[]] * 3, start=now)
    assert engine.mode == "idle"


def test_pinch_on_empty_space_grabs_nothing():
    windows = FakeWindows(rect=(100, 100, 800, 600))
    engine = Engine(windows, FakeCursor())
    run(engine, hold("R", (2000, 1200), OPEN, 5) + hold("R", (2000, 1200), PINCH, 20) + hold("R", (2200, 1300), PINCH, 20))
    assert windows.rects["win"] == (100, 100, 800, 600)


def test_parse_keys():
    from pynput.keyboard import Key
    assert tools.parse_keys("Ctrl + Z") == [Key.ctrl, "z"]
    assert tools.parse_keys("enter") == [Key.enter]


def test_delete_key_asks_permission():
    assert tools.needs_confirmation("press_keys", {"keys": "delete"})
    assert tools.needs_confirmation("press_keys", {"keys": "shift+Supr"})
    assert not tools.needs_confirmation("press_keys", {"keys": "ctrl+backspace"})
    assert not tools.needs_confirmation("type_text", {"text": "hola"})


def fake_hand(extended=(True, True, True, True)):
    """21 puntos de MediaPipe con la muñeca abajo y los dedos hacia arriba."""
    points = [(0, 0), (-20, -15), (-40, -30), (-55, -40), (-70, -50)]
    for x, out in zip((-30, -10, 10, 30), extended):
        tip = -120 if out else -40
        points += [(x, -50), (x, -80), (x, (tip - 80) / 2), (x, tip)]
    return points


def test_hand_poses():
    assert hand_pose(fake_hand()) == "palm"
    assert hand_pose(fake_hand((False, False, False, False))) == "fist"
    assert hand_pose(fake_hand((True, True, False, False))) == "two"
    assert hand_pose(fake_hand((True, True, True, False))) == "three"
    assert hand_pose(fake_hand((False, False, False, True))) == "shaka"
    rock = fake_hand((True, False, False, True))
    rock[4] = (-25, -45)  # pulgar recogido
    assert hand_pose(rock) == "rock"
    assert hand_pose(fake_hand((True, False, False, False))) == "other"


def test_two_fingers_scroll_like_a_joystick_and_do_not_click():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    now = run(engine, [[("R", (400, 500), OPEN, "two")]] * 10)
    assert engine.mode == "scrolling"
    # Dentro de la zona muerta no pasa nada.
    now = run(engine, [[("R", (400, 480), OPEN, "two")]] * 30, start=now)
    assert cursor.scrolled == 0
    # 200 px arriba del inicio durante 2 s: unos 8,5 pasos por segundo hacia arriba.
    now = run(engine, [[("R", (400, 300), OPEN, "two")]] * 60, start=now)
    assert 14 <= cursor.scrolled <= 19
    # Bajar la mano invierte el sentido.
    before = cursor.scrolled
    now = run(engine, [[("R", (400, 700), OPEN, "two")]] * 60, start=now)
    assert cursor.scrolled < before
    run(engine, [[("R", (400, 700), OPEN, "other")]] * 10, start=now)
    assert engine.mode == "idle" and cursor.clicks == []


def test_fist_minimizes_the_window_once():
    windows = FakeWindows()
    engine = Engine(windows, FakeCursor())
    run(engine, [[("R", (400, 300), PINCH, "fist")]] * 40)
    assert windows.minimized == "win"
    assert engine.mode == "fist_done" and not engine.pinching["R"]


def test_two_open_palms_minimize_once_then_bring_windows_back():
    windows = FakeWindows()
    pressed = []
    engine = Engine(windows, FakeCursor(), keys=pressed.append)
    palms = [("R", (400, 300), OPEN, "palm"), ("L", (900, 300), OPEN, "palm")]
    now = run(engine, [palms] * 150)  # 5 segundos con las manos abiertas
    assert windows.minimize_all_calls == 1 and windows.restored == []
    now = run(engine, [[palms[0]]] * 5, start=now)  # baja una mano
    run(engine, [palms] * 40, start=now)
    assert windows.minimize_all_calls == 1 and windows.restored == ["a", "b"]
    assert pressed == []  # sin Win+D: escondería el fondo del holograma


def test_fast_open_hand_swipe_switches_window():
    pressed = []
    engine = Engine(FakeWindows(), FakeCursor(), keys=pressed.append, work_area=(0, 0, 1920, 1040))
    now = run(engine, [[("R", (300, 500), OPEN, "palm")]] * 10)
    now = run(engine, [[("R", (300 + i * 80, 500), OPEN, "palm")] for i in range(10)], start=now)
    assert pressed == ["alt+tab"]
    # Moverse despacio no cambia de ventana.
    run(engine, [[("R", (1100 - i * 5, 500), OPEN, "palm")] for i in range(90)], start=now + 2)
    assert pressed == ["alt+tab"]


def test_dropping_a_window_on_the_left_edge_snaps_it():
    windows = FakeWindows(rect=(100, 100, 800, 600))
    engine = Engine(windows, FakeCursor(), work_area=(0, 0, 1920, 1040))
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 15))
    now = run(engine, hold("R", (5, 300), PINCH, 60), start=now)
    run(engine, hold("R", (5, 300), OPEN, 3), start=now)
    assert windows.rects["win"] == (0, 0, 960, 1040)


def test_thumb_and_middle_pinch_right_clicks():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    now = run(engine, [[("R", (400, 300), OPEN, "other", OPEN)]] * 10)
    now = run(engine, [[("R", (405, 302), OPEN, "other", PINCH)]] * 4, start=now)
    run(engine, [[("R", (404, 301), OPEN, "other", OPEN)]] * 3, start=now)
    assert cursor.right_clicks == [(400, 300)] and cursor.clicks == []


def test_closing_the_fist_is_not_a_click():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    now = run(engine, [[("R", (400, 300), OPEN, "other", OPEN)]] * 10)
    # Al cerrar la mano el pulgar pasa cerca del índice y del medio antes de ser puño.
    now = run(engine, [[("R", (400, 300), PINCH, "other", PINCH)]] * 2, start=now)
    run(engine, [[("R", (400, 300), PINCH, "fist", PINCH)]] * 10, start=now)
    assert cursor.clicks == [] and cursor.right_clicks == []


def test_quick_fist_then_open_palm_maximizes_and_again_restores():
    windows = FakeWindows()
    engine = Engine(windows, FakeCursor())
    now = run(engine, [[("R", (400, 300), OPEN, "other")]] * 10)
    now = run(engine, [[("R", (400, 300), OPEN, "fist")]] * 9, start=now)  # 0,3 s de puño
    now = run(engine, [[("R", (430, 260), OPEN, "palm")]] * 10, start=now)
    assert windows.maximized and engine.status == "VENTANA MAXIMIZADA"
    assert getattr(windows, "minimized", None) is None
    now = run(engine, [[("R", (400, 300), OPEN, "other")]] * 30, start=now)
    now = run(engine, [[("R", (400, 300), OPEN, "fist")]] * 9, start=now)
    run(engine, [[("R", (430, 260), OPEN, "palm")]] * 10, start=now)
    assert not windows.maximized


def test_two_quick_pinches_land_on_the_same_point():
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor)
    now = run(engine, hold("R", (400, 300), OPEN, 10) + hold("R", (400, 300), PINCH, 3) + hold("R", (400, 300), OPEN, 2))
    run(engine, hold("R", (420, 310), PINCH, 3) + hold("R", (420, 310), OPEN, 2), start=now)
    assert len(cursor.clicks) == 2 and cursor.clicks[0] == cursor.clicks[1]


def test_three_fingers_swipe_changes_tab_and_two_fingers_go_back():
    pressed = []
    engine = Engine(FakeWindows(), FakeCursor(), keys=pressed.append, work_area=(0, 0, 1920, 1040))
    now = run(engine, [[("R", (1300, 500), OPEN, "three")]] * 10)
    now = run(engine, [[("R", (1300 - i * 80, 500), OPEN, "three")] for i in range(10)], start=now)
    assert pressed == ["ctrl+shift+tab"]
    now = run(engine, [[("R", (300, 500), OPEN, "two")]] * 45, start=now)
    run(engine, [[("R", (300 + i * 80, 500), OPEN, "two")] for i in range(10)], start=now)
    assert pressed == ["ctrl+shift+tab", "alt+left"]


def test_opening_the_fist_off_any_window_brings_back_the_minimized_one():
    windows = FakeWindows()
    engine = Engine(windows, FakeCursor())
    now = run(engine, [[("R", (400, 300), OPEN, "other")]] * 10)
    now = run(engine, [[("R", (400, 300), OPEN, "fist")]] * 30, start=now)  # puño largo: minimiza
    assert windows.hidden
    now = run(engine, [[("R", (400, 300), OPEN, "other")]] * 30, start=now)
    # La ventana ya no está bajo el cursor: abrir el puño la devuelve.
    now = run(engine, [[("R", (400, 300), OPEN, "fist")]] * 9, start=now)
    run(engine, [[("R", (430, 260), OPEN, "palm")]] * 10, start=now)
    assert not windows.hidden and engine.status == "VENTANA DE VUELTA"


class FakeVolume:
    def __init__(self, level=0.5):
        self.level = level

    def get(self):
        return self.level

    def set(self, level):
        self.level = level


def test_shaka_and_turning_the_hand_changes_the_volume():
    import math
    volume = FakeVolume(0.5)
    engine = Engine(FakeWindows(), FakeCursor(), volume=volume)
    hand = lambda angle: [("R", (400, 300), OPEN, "shaka", 9.9, angle)]
    now = run(engine, [hand(-math.pi / 2)] * 10)
    assert engine.mode == "volume"
    # Un cuarto de vuelta en sentido horario: +50 %.
    now = run(engine, [hand(-math.pi / 2 + i * math.pi / 40) for i in range(1, 21)], start=now)
    assert abs(volume.level - 1.0) < 0.02 and engine.status == "VOLUMEN 100%"
    now = run(engine, [hand(-math.pi / 2 - i * math.pi / 40) for i in range(1, 41)], start=now)
    assert volume.level < 0.3
    run(engine, [[("R", (400, 300), OPEN, "other")]] * 10, start=now)
    assert engine.mode == "idle" and engine.knob is None


def test_draw_mode_pinch_draws_and_fist_erases():
    engine = Engine(FakeWindows(), FakeCursor())
    engine.draw_mode = True
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 3))
    now = run(engine, [[("R", (400 + i * 10, 300), PINCH)] for i in range(20)], start=now)
    now = run(engine, hold("R", (600, 300), OPEN, 3), start=now)
    assert len(engine.strokes) == 1 and len(engine.strokes[0]) > 10
    run(engine, [[("R", (600, 300), OPEN, "fist")]] * 30, start=now)
    assert engine.strokes == []


def test_globe_turns_with_a_pinch_and_grows_with_two_hands():
    engine = Engine(FakeWindows(), FakeCursor())
    engine.globe_mode = True
    yaw = engine.globe["yaw"]
    now = run(engine, hold("R", (400, 300), OPEN, 5) + hold("R", (400, 300), PINCH, 3))
    now = run(engine, [[("R", (400 + i * 10, 300), PINCH)] for i in range(20)], start=now)
    assert engine.globe["yaw"] > yaw + 0.5
    now = run(engine, [[("R", (600, 300), PINCH), ("L", (800, 300), OPEN)]] * 5, start=now)
    now = run(engine, [[("R", (600, 300), PINCH), ("L", (800, 300), PINCH)]] * 3, start=now)
    run(engine, [[("R", (500, 300), PINCH), ("L", (900, 300), PINCH)]] * 30, start=now)
    assert 1.8 < engine.globe["scale"] < 2.2
    assert windows_untouched(engine)


def windows_untouched(engine):
    return engine.windows.rects["win"] == (100, 100, 800, 600)


def test_rock_opens_the_radial_menu_and_pinch_picks_the_pointed_item():
    opened = []
    cursor = FakeCursor()
    engine = Engine(FakeWindows(), cursor, menu=(4, opened.append))
    now = run(engine, [[("R", (1000, 600), OPEN, "rock")]] * 10)
    assert engine.menu is not None
    # Apunta a la derecha: con 4 opciones, la 1 (0 arriba, en sentido horario).
    now = run(engine, [[("R", (1150, 600), OPEN, "other")]] * 5, start=now)
    assert engine.menu["selected"] == 1
    run(engine, [[("R", (1150, 600), PINCH, "other")]] * 3 + [[("R", (1150, 600), OPEN, "other")]] * 3, start=now)
    assert opened == [1] and engine.menu is None and cursor.clicks == []


class FakeUI:
    def __init__(self):
        self.log = []

    def hit(self, point):
        return "key" if point[0] < 200 else None

    def press(self, token, point):
        self.log.append(("press", token))

    def drag(self, token, point):
        self.log.append(("drag", token))

    def release(self, token, point):
        self.log.append(("release", token))

    def fist(self, point):
        return point[0] < 200


def test_pinching_a_floating_element_does_not_click_the_window_below():
    ui = FakeUI()
    cursor = FakeCursor()
    windows = FakeWindows(rect=(0, 0, 800, 600))
    engine = Engine(windows, cursor, ui=ui)
    run(engine, hold("R", (150, 300), OPEN, 5) + hold("R", (150, 300), PINCH, 20) + hold("R", (150, 300), OPEN, 3))
    assert ui.log[0] == ("press", "key") and ui.log[-1] == ("release", "key")
    assert cursor.clicks == [] and windows.rects["win"] == (0, 0, 800, 600)
    # Un puño sobre el elemento lo borra en vez de minimizar la ventana.
    run(engine, [[("R", (150, 300), OPEN, "fist")]] * 30, start=10)
    assert getattr(windows, "minimized", None) is None


def test_effects_mode_keeps_two_palms_for_the_energy_ball():
    windows = FakeWindows()
    engine = Engine(windows, FakeCursor())
    engine.effects_mode = True
    run(engine, [[("R", (400, 300), OPEN, "palm"), ("L", (900, 300), OPEN, "palm")]] * 60)
    assert windows.minimize_all_calls == 0


def test_quick_pinch_on_a_3d_object_is_a_tap():
    engine = Engine(FakeWindows(), FakeCursor())
    engine.globe_mode = True
    run(engine, hold("R", (500, 400), OPEN, 5) + hold("R", (500, 400), PINCH, 4) + hold("R", (500, 400), OPEN, 2))
    assert engine.tap is not None and engine.tap[0] == (500, 400)
