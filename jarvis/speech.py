"""Voz a texto local. Usa la tarjeta NVIDIA si puede; si no, el procesador.

JARVIS_WHISPER elige otro modelo, por ejemplo "small" o "medium".
"""
import io
import logging
import os
import sys
import threading
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

GPU_MODEL = "large-v3-turbo"
CPU_MODEL = "small"
_model = None
_lock = threading.Lock()
device = "sin cargar"

log = logging.getLogger("jarvis.speech")


def _add_cuda_libraries() -> None:
    """Las DLL de CUDA vienen en los paquetes nvidia-* de pip; Windows no las busca ahí solo."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for folder in nvidia.glob("*/bin"):
        os.add_dll_directory(str(folder))
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ["PATH"]


def _load() -> WhisperModel:
    global device
    wanted = os.environ.get("JARVIS_WHISPER")
    try:
        _add_cuda_libraries()
        model = WhisperModel(wanted or GPU_MODEL, device="cuda", compute_type="float16")
        # Las DLL que faltan solo fallan al transcribir: se prueba con medio segundo de ruido.
        segments, _ = model.transcribe(np.random.default_rng(0).normal(0, 0.01, 8000).astype(np.float32),
                                       language="es", vad_filter=False)
        list(segments)
        device = f"GPU ({wanted or GPU_MODEL})"
        return model
    except Exception as error:
        log.warning("Whisper no pudo usar la GPU (%s); uso el procesador", error)
    device = f"CPU ({wanted or CPU_MODEL})"
    return WhisperModel(wanted or CPU_MODEL, device="cpu", compute_type="int8")


def warm_up() -> None:
    """Carga el modelo de antemano para que la primera orden no tarde."""
    global _model
    with _lock:
        if _model is None:
            _model = _load()


def transcribe(audio) -> str:
    """Acepta un archivo de audio en bytes o muestras float32 a 16 kHz."""
    warm_up()
    with _lock:
        segments, _ = _model.transcribe(
            io.BytesIO(audio) if isinstance(audio, bytes) else audio,
            language="es",
            vad_filter=True,
            initial_prompt="Órdenes para Jarvis, el asistente de la PC.",
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
