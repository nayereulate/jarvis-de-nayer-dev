"""Grabar la pantalla principal y el micrófono con ffmpeg, usando la tarjeta NVIDIA.

La captura (ddagrab) ve todo lo que hay en pantalla, también el holograma y los subtítulos.
JARVIS_REC_MIC elige el micrófono por nombre; JARVIS_REC_OUTPUT, otra pantalla (0 es la principal).
"""
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

VIDEOS_DIR = Path.home() / "Videos" / "Jarvis"
MIN_FREE_GB = 1.0
VIRTUAL_MICS = ("droidcam", "camo", "bytecast", "virtual")

_process = None
_file = None
_started = None
_lock = threading.Lock()


def ffmpeg() -> str:
    path = os.environ.get("JARVIS_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("No encontré ffmpeg. Instálalo con: winget install Gyan.FFmpeg")
    return path


def microphones() -> list[str]:
    done = subprocess.run([ffmpeg(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW)
    return re.findall(r'"([^"]+)" \(audio\)', done.stderr)


def pick_microphone(names: list[str]) -> str | None:
    wanted = [os.environ["JARVIS_REC_MIC"].lower()] if os.environ.get("JARVIS_REC_MIC") else []
    for wish in wanted + ["fifine"]:
        for name in names:
            if wish in name.lower():
                return name
    return next((name for name in names if not any(v in name.lower() for v in VIRTUAL_MICS)), None)


def recording() -> bool:
    return _process is not None and _process.poll() is None


def status() -> dict:
    if not recording():
        return {"recording": False}
    return {"recording": True, "file": str(_file), "seconds": round(time.monotonic() - _started)}


def start() -> str:
    global _process, _file, _started
    with _lock:
        if recording():
            return f"Ya estoy grabando en {_file.name}"
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(VIDEOS_DIR).free / 1024**3
        if free < MIN_FREE_GB:
            raise RuntimeError(f"Solo quedan {free:.1f} GB libres: libera espacio antes de grabar")
        _file = VIDEOS_DIR / f"jarvis-{datetime.now():%Y%m%d-%H%M%S}.mp4"
        screen = os.environ.get("JARVIS_REC_OUTPUT", "0")
        command = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", f"ddagrab=output_idx={screen}:framerate=30"]
        mic = pick_microphone(microphones())
        if mic:
            command += ["-f", "dshow", "-i", f"audio={mic}", "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
        command += ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21", "-movflags", "+faststart", str(_file)]
        log = (VIDEOS_DIR / "ultima-grabacion.log").open("w", encoding="utf-8")
        _process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        _started = time.monotonic()
        time.sleep(1.5)
        if _process.poll() is not None:
            raise RuntimeError("ffmpeg no pudo empezar a grabar; mira " + str(VIDEOS_DIR / "ultima-grabacion.log"))
        free_minutes = free * 1024 / 75  # unos 75 MB por minuto a 1440p
        return (f"Grabando la pantalla{' y el micrófono ' + mic if mic else ' (sin micrófono)'} en {_file}. "
                f"Con el espacio libre caben unos {free_minutes:.0f} minutos")


def stop() -> str:
    global _process
    with _lock:
        if not recording():
            return "No estaba grabando"
        seconds = round(time.monotonic() - _started)
        # "q" deja que ffmpeg cierre el archivo bien; matarlo dejaría el MP4 roto.
        try:
            _process.stdin.write(b"q")
            _process.stdin.flush()
            _process.wait(20)
        except Exception:
            _process.kill()
        _process = None
        return f"Grabación guardada: {_file} ({seconds // 60} min {seconds % 60} s)"
