"""Capturas de la pantalla principal y clics remotos desde el celular."""
import ctypes

import cv2
import numpy as np

from . import winctl

try:
    # Coordenadas en píxeles reales aunque Windows tenga escala (125 %, 150 %...).
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def _primary(monitors: list[dict]) -> dict:
    """La pantalla principal; con varios monitores no siempre es la primera de la lista."""
    screens = monitors[1:]
    primary = next((m for m in screens if m.get("is_primary")), None)
    return primary or next((m for m in screens if m["left"] == 0 and m["top"] == 0), screens[0])


def grab(max_width: int) -> np.ndarray:
    import mss

    with mss.mss() as capture:
        shot = np.asarray(capture.grab(_primary(capture.monitors)))[:, :, :3]
    height, width = shot.shape[:2]
    if width > max_width:
        shot = cv2.resize(shot, (max_width, round(height * max_width / width)), interpolation=cv2.INTER_AREA)
    return shot


def jpeg(max_width: int = 1280, quality: int = 60) -> bytes:
    ok, data = cv2.imencode(".jpg", grab(max_width), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("No pude comprimir la captura")
    return data.tobytes()


def save_png(path, max_width: int = 1600) -> None:
    path.parent.mkdir(exist_ok=True)
    if not cv2.imwrite(str(path), grab(max_width)):
        raise RuntimeError("No pude guardar la captura")


def primary_monitor() -> dict:
    import mss

    with mss.mss() as capture:
        return dict(_primary(capture.monitors))


def click(fx: float, fy: float, button: str = "left") -> None:
    """fx, fy: posición relativa (0 a 1) dentro de la pantalla principal."""
    if not (0 <= fx <= 1 and 0 <= fy <= 1):
        raise ValueError("Posición fuera de la pantalla")
    monitor = primary_monitor()
    x = monitor["left"] + fx * (monitor["width"] - 1)
    y = monitor["top"] + fy * (monitor["height"] - 1)
    cursor = winctl.Cursor()
    if button == "right":
        cursor.right_click(x, y)
    else:
        cursor.click(x, y)


def scroll(steps: int) -> None:
    winctl.Cursor().scroll(max(-20, min(20, int(steps))))
