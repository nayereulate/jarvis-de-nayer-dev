"""Elegir la webcam física. Lo usan el modo holograma y la detección de presencia."""
import os

import cv2

VIRTUAL_CAMERAS = ("droidcam", "camo", "obs", "virtual", "broadcast", "bytecast", "lsvcam")


def pick_camera() -> tuple[int, str]:
    """JARVIS_CAMERA elige por nombre; si no, la C920 o la primera cámara que no sea virtual."""
    from cv2_enumerate_cameras import enumerate_cameras

    cameras = enumerate_cameras(cv2.CAP_MSMF)
    wanted = [os.environ["JARVIS_CAMERA"].lower()] if os.environ.get("JARVIS_CAMERA") else []
    for name in wanted + ["c920"]:
        for camera in cameras:
            if name in camera.name.lower():
                return camera.index, camera.name
    for camera in cameras:
        if not any(virtual in camera.name.lower() for virtual in VIRTUAL_CAMERAS):
            return camera.index, camera.name
    raise RuntimeError("No encontré una cámara física conectada")


def open_camera(width: int, height: int) -> tuple[cv2.VideoCapture, str]:
    index, name = pick_camera()
    capture = cv2.VideoCapture(index, cv2.CAP_MSMF)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not capture.isOpened():
        raise RuntimeError(f"No pude abrir la cámara {name}; puede que otra app la esté usando")
    return capture, name
