"""Reconocer caras conocidas con los modelos YuNet (detectar) y SFace (reconocer) de OpenCV."""
import json
import threading
import urllib.request

import numpy as np

from .paths import DATA_DIR, MODELS_DIR

ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
DETECTOR = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
URLS = {
    DETECTOR: ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    RECOGNIZER: ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
FACES_FILE = DATA_DIR / "faces.npz"
MATCH = 0.36  # similitud coseno mínima para decir que es la misma persona (valor recomendado de SFace)
MIN_FACE = 60  # píxeles: caras más chicas están demasiado lejos para reconocerlas bien


class FaceBook:
    """Las caras aprendidas: nombre y varias huellas por persona."""

    def __init__(self, path=FACES_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.names, self.features = self._load()

    def _load(self):
        if not self.path.exists():
            return [], np.zeros((0, 128), dtype=np.float32)
        data = np.load(self.path)
        return json.loads(str(data["names"])), data["features"]

    def _save(self):
        self.path.parent.mkdir(exist_ok=True)
        np.savez(self.path, names=json.dumps(self.names), features=self.features)

    def known(self) -> list[str]:
        return sorted(set(self.names))

    def add(self, name: str, features: list[np.ndarray]) -> None:
        """Guarda las huellas de una persona; si ya existía, reemplaza las anteriores."""
        with self._lock:
            keep = [i for i, n in enumerate(self.names) if n.lower() != name.lower()]
            new = np.array([normalize(f) for f in features], dtype=np.float32).reshape(-1, 128)
            self.names = [self.names[i] for i in keep] + [name] * len(new)
            self.features = np.concatenate([self.features[keep].reshape(-1, 128), new])
            self._save()

    def forget(self, name: str | None = None) -> int:
        """Olvida a una persona, o a todas si name es None."""
        with self._lock:
            keep = [i for i, n in enumerate(self.names) if name is not None and n.lower() != name.lower()]
            removed = len(self.names) - len(keep)
            self.names = [self.names[i] for i in keep]
            self.features = self.features[keep].reshape(-1, 128)
            self._save()
        return removed

    def match(self, feature: np.ndarray) -> tuple[str | None, float]:
        if not self.names:
            return None, 0.0
        scores = self.features @ normalize(feature)
        best = int(np.argmax(scores))
        score = float(scores[best])
        return (self.names[best] if score >= MATCH else None), score


def normalize(feature: np.ndarray) -> np.ndarray:
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    return feature / max(float(np.linalg.norm(feature)), 1e-6)


class FaceID:
    def __init__(self):
        import cv2

        for path, url in URLS.items():
            if not path.exists():
                MODELS_DIR.mkdir(exist_ok=True)
                urllib.request.urlretrieve(url, path)
        self.detector = cv2.FaceDetectorYN.create(str(DETECTOR), "", (320, 320), 0.7)
        self.recognizer = cv2.FaceRecognizerSF.create(str(RECOGNIZER), "")

    def faces(self, frame: np.ndarray) -> list[np.ndarray]:
        """Caras de la imagen (BGR), de la más grande a la más chica."""
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, found = self.detector.detect(frame)
        if found is None:
            return []
        return sorted(found, key=lambda face: face[2] * face[3], reverse=True)

    def feature(self, frame: np.ndarray, face: np.ndarray) -> np.ndarray | None:
        if min(face[2], face[3]) < MIN_FACE:
            return None
        aligned = self.recognizer.alignCrop(frame, face)
        return self.recognizer.feature(aligned)
