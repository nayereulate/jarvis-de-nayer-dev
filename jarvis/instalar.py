"""Termina la instalación: descarga la voz, crea el token y revisa lo que hace falta.

Lo ejecuta instalar.bat. El resto de modelos (manos, caras, «Hey Jarvis», Whisper) se bajan solos
la primera vez que se usan.
"""
import shutil
import sys
import urllib.request

from .paths import DATA_DIR, ROOT

VOICE = "es_ES-davefx-medium"
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/"


def download_voice() -> None:
    folder = ROOT / "voices"
    folder.mkdir(exist_ok=True)
    for name in (f"{VOICE}.onnx", f"{VOICE}.onnx.json"):
        target = folder / name
        if target.exists():
            print(f"  ya está: {name}")
            continue
        print(f"  descargando {name}...")
        urllib.request.urlretrieve(VOICE_URL + name, target)


def check(name: str, ok: bool, advice: str) -> bool:
    print(f"  [{'OK' if ok else '!!'}] {name}" + ("" if ok else f" -> {advice}"))
    return ok


def main() -> int:
    print("Voz de Jarvis:")
    download_voice()

    print("Token de acceso:")
    from .server import TOKEN_FILE, load_token  # crea data/token.txt si no existe

    load_token()
    print(f"  guardado en {TOKEN_FILE} (no lo compartas)")

    print("Revisando el equipo:")
    from .brain import BrainError, find_claude

    try:
        claude = find_claude()
    except BrainError:
        claude = None
    ready = check("Claude Code", bool(claude), "instálalo: https://claude.com/claude-code y ejecuta «claude» una vez para iniciar sesión")
    check("ffmpeg (para grabar la pantalla)", bool(shutil.which("ffmpeg")), "winget install Gyan.FFmpeg")
    check("Tailscale (para usarlo desde el celular)", bool(shutil.which("tailscale")), "opcional: https://tailscale.com/download")
    check("Tarjeta NVIDIA (Whisper más rápido)", bool(shutil.which("nvidia-smi")), "opcional: sin ella usa el procesador")
    DATA_DIR.mkdir(exist_ok=True)
    print()
    print("Listo. Ejecuta iniciar.bat para encender a Jarvis." if ready else "Falta Claude Code: instálalo y vuelve a ejecutar instalar.bat.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
