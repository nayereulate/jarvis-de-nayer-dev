"""Texto a voz local con Piper. La voz se carga en el primer uso."""
import io
import re
import threading
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

VOICE_NAME = "es_ES-davefx-medium"
# Menos de 1 habla más rápido.
SPEED = SynthesisConfig(length_scale=0.85)
VOICE_FILE = Path(__file__).resolve().parent.parent / "voices" / f"{VOICE_NAME}.onnx"
MAX_CHARS = 1500
_voice = None
_lock = threading.Lock()


def clean(text: str) -> str:
    text = re.sub(r"https?://\S+", "el enlace", text)
    text = re.sub(r"[*_#`>|~]", "", text)
    return " ".join(text.split())[:MAX_CHARS]


def synthesize(text: str) -> bytes:
    global _voice
    text = clean(text)
    if not text:
        raise ValueError("No hay texto para leer")
    with _lock:
        if _voice is None:
            if not VOICE_FILE.exists():
                raise FileNotFoundError(
                    f"Falta la voz. Descárgala con: python -m piper.download_voices --download-dir voices {VOICE_NAME}"
                )
            _voice = PiperVoice.load(VOICE_FILE)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            _voice.synthesize_wav(text, wav, syn_config=SPEED)
        return buffer.getvalue()
