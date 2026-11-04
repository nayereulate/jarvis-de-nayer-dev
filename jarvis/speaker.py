"""Altavoces de la PC. Un solo dueño del audio para que Jarvis no se pise y se le pueda interrumpir."""
import io
import logging
import threading
import time
import wave

import numpy as np

from . import voice

log = logging.getLogger("jarvis.speaker")


def tone(frequency: float, seconds: float, volume: float = 0.25, rate: int = 16000) -> np.ndarray:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    fade = np.minimum(1, np.minimum(t, seconds - t) / 0.02)
    return (volume * np.sin(2 * np.pi * frequency * t) * fade).astype(np.float32)


def chime(rate: int = 16000) -> np.ndarray:
    """Tres tonos ascendentes, para alarmas y recordatorios."""
    gap = np.zeros(int(rate * 0.06), dtype=np.float32)
    notes = [tone(f, 0.16, 0.3, rate) for f in (660, 880, 1100)]
    return np.concatenate([part for note in notes for part in (note, gap)] * 2)


def startup_sound(rate: int = 22050) -> np.ndarray:
    """Arranque: un barrido que sube y dos tonos limpios, como un sistema encendiéndose."""
    seconds = 0.9
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    sweep_phase = 2 * np.pi * (180 * t + (1100 - 180) * t**2 / (2 * seconds))
    fade = np.minimum(1, t / 0.05) * np.minimum(1, (seconds - t) / 0.25)
    sweep = (0.18 * np.sin(sweep_phase) + 0.06 * np.sin(2 * sweep_phase)) * fade
    gap = np.zeros(int(rate * 0.05), dtype=np.float32)
    return np.concatenate([sweep.astype(np.float32), gap, tone(880, 0.12, 0.22, rate), gap,
                           tone(1320, 0.35, 0.22, rate)])


class Speaker:
    def __init__(self):
        self._lock = threading.Lock()
        self._until = 0.0

    def busy(self) -> bool:
        return time.monotonic() < self._until

    def stop(self) -> None:
        import sounddevice as sd

        self._until = 0.0
        sd.stop()

    def play(self, samples: np.ndarray, rate: int, wait: bool = False) -> None:
        import sounddevice as sd

        with self._lock:
            sd.play(samples, rate)
            self._until = time.monotonic() + len(samples) / rate
        if wait:
            self.wait()

    def wait(self) -> None:
        while self.busy():
            time.sleep(0.05)

    def say(self, text: str, wait: bool = False, alarm: bool = False) -> None:
        """alarm: suena una campanilla antes de la voz."""
        try:
            with wave.open(io.BytesIO(voice.synthesize(text))) as audio:
                rate = audio.getframerate()
                samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype=np.int16)
            samples = samples.astype(np.float32) / 32768
            if alarm:
                samples = np.concatenate([chime(rate), np.zeros(int(rate * 0.2), dtype=np.float32), samples])
            self.play(samples, rate, wait)
        except Exception:
            log.exception("No pude reproducir la voz")
