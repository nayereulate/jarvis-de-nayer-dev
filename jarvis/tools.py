"""Acciones de la PC. La política de confirmación se decide aquí, nunca en el modelo."""
import ctypes
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import psutil
from pynput.keyboard import Controller, Key

from . import briefing as briefing_module
from . import files, recorder
from .memory import memory
from .notes import notes
from .paths import DATA_DIR, ROOT
from .reminders import parse_when, reminders
from .routines import routines

MAX_OUTPUT = 8000
_keyboard = Controller()
# Modos que leen las ventanas de Jarvis (holograma y orbe) cada vez que preguntan al servidor.
settings = {"subtitles": False, "draw": False, "globe": False, "solar": False, "earth": False,
            "scanner": False, "effects": False, "keyboard": False, "notes": False, "visualizer": False,
            "earth_cities": []}
HOLO_MODES = {
    "draw": "dibujo en el aire", "globe": "esfera holográfica", "solar": "sistema solar",
    "earth": "globo terráqueo", "scanner": "escáner de identidad", "effects": "efectos de partículas y bola de energía",
    "keyboard": "teclado holográfico", "notes": "notas adhesivas", "visualizer": "visualizador de audio",
}
# Estos usan el pellizco para sí mismos: solo uno a la vez.
EXCLUSIVE = {"draw", "globe", "solar", "earth"}
# El servidor conecta aquí lo que vive fuera de este módulo: la escucha, la presencia, los avisos.
hooks = {}

KEY_NAMES = {
    "ctrl": Key.ctrl, "control": Key.ctrl, "alt": Key.alt, "shift": Key.shift, "win": Key.cmd,
    "enter": Key.enter, "tab": Key.tab, "esc": Key.esc, "escape": Key.esc, "space": Key.space,
    "backspace": Key.backspace, "delete": Key.delete, "supr": Key.delete,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "home": Key.home, "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down,
    **{f"f{number}": getattr(Key, f"f{number}") for number in range(1, 13)},
}

APPS = {
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador": "explorer",
    "chrome": "chrome",
    "edge": "msedge",
    "administrador_tareas": "taskmgr",
}

MEDIA_KEYS = {
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
    "next": 0xB0,
    "previous": 0xB1,
    "play_pause": 0xB3,
}


def system_status() -> dict:
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    memory = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "ram_percent": memory.percent,
        "ram_total_gb": round(memory.total / 1024**3, 1),
        "disk_percent": disk.percent,
    }


def list_processes(limit: int = 10) -> list[dict]:
    limit = max(1, min(int(limit), 50))
    processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        memory = process.info["memory_info"]
        if memory:
            processes.append({
                "pid": process.info["pid"],
                "name": process.info["name"],
                "ram_mb": round(memory.rss / 1024**2),
            })
    return sorted(processes, key=lambda p: p["ram_mb"], reverse=True)[:limit]


def open_app(name: str) -> str:
    if name not in APPS:
        raise ValueError(f"App no permitida: {name}. Disponibles: {', '.join(APPS)}")
    subprocess.Popen(["cmd", "/c", "start", "", APPS[name]], creationflags=subprocess.CREATE_NO_WINDOW)
    return f"Abierto: {name}"


def open_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(ord(c) < 33 for c in url):
        raise ValueError("Solo se permiten URLs http o https válidas")
    os.startfile(url)
    return f"Abierto: {url}"


def media_key(key: str) -> str:
    if key not in MEDIA_KEYS:
        raise ValueError(f"Tecla no válida: {key}. Disponibles: {', '.join(MEDIA_KEYS)}")
    code = MEDIA_KEYS[key]
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)
    return f"Tecla enviada: {key}"


def lock_pc() -> str:
    ctypes.windll.user32.LockWorkStation()
    return "PC bloqueada"


def shutdown_pc() -> str:
    subprocess.run(["shutdown", "/s", "/t", "30"], check=True)
    return "La PC se apagará en 30 segundos"


def restart_pc() -> str:
    subprocess.run(["shutdown", "/r", "/t", "30"], check=True)
    return "La PC se reiniciará en 30 segundos"


def kill_process(name: str) -> str:
    killed = 0
    for process in psutil.process_iter(["name"]):
        if (process.info["name"] or "").lower() == name.lower():
            process.terminate()
            killed += 1
    if not killed:
        raise ValueError(f"No hay procesos llamados {name}")
    return f"Procesos terminados: {killed}"


def run_powershell(command: str) -> dict:
    done = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return {
        "exit_code": done.returncode,
        "stdout": done.stdout[-MAX_OUTPUT:],
        "stderr": done.stderr[-MAX_OUTPUT:],
    }


def type_text(text: str) -> str:
    _keyboard.type(text)
    return f"Escritos {len(text)} caracteres en la ventana activa"


def parse_keys(keys: str) -> list:
    parsed = []
    for name in keys.lower().replace(" ", "").split("+"):
        if name in KEY_NAMES:
            parsed.append(KEY_NAMES[name])
        elif len(name) == 1:
            parsed.append(name)
        else:
            raise ValueError(f"Tecla desconocida: {name}")
    return parsed


def press_keys(keys: str) -> str:
    """keys como "ctrl+z", "enter" o "alt+tab"."""
    parsed = parse_keys(keys)
    for key in parsed:
        _keyboard.press(key)
    for key in reversed(parsed):
        _keyboard.release(key)
    return f"Teclas pulsadas: {keys}"


class Child:
    """Una ventana de Jarvis que corre como proceso aparte (Qt necesita su propio hilo principal)."""

    def __init__(self, module: str, log_name: str, start_timeout: float):
        self.module = module
        self.log = DATA_DIR / log_name
        self.start_timeout = start_timeout
        self.process = None

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, **env) -> bool:
        """False si ya estaba corriendo. Espera a que el proceso diga LISTO, para poder avisar si falla."""
        if self.running():
            return False
        self.log.parent.mkdir(exist_ok=True)
        log = self.log.open("w", encoding="utf-8")
        env = {**os.environ, "PYTHONUTF8": "1", "JARVIS_PARENT": str(os.getpid()), **env}
        self.process = subprocess.Popen(
            [sys.executable, "-m", self.module],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + self.start_timeout
        while time.monotonic() < deadline:
            output = self.log.read_text(encoding="utf-8", errors="replace")
            if "LISTO" in output:
                return True
            if self.process.poll() is not None:
                error = next((line for line in output.splitlines() if line.startswith("ERROR")), output[-300:])
                raise RuntimeError(f"No pudo iniciar: {error}")
            time.sleep(0.3)
        return True

    def stop(self) -> bool:
        if not self.running():
            return False
        self.process.terminate()
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process = None
        return True


# La primera vez cargan MediaPipe y Qt: pueden tardar.
hologram = Child("jarvis.hologram", "hologram.log", 45)
desktop = Child("jarvis.desktop", "desktop.log", 30)


def hologram_running() -> bool:
    return hologram.running()


def hologram_on() -> str:
    try:
        started = hologram.start()
    except RuntimeError as error:
        raise RuntimeError(f"El modo holograma no pudo iniciar: {error}") from error
    return "Modo holograma activado" if started else "El modo holograma ya está activo"


def hologram_off() -> str:
    settings.update({name: False for name in HOLO_MODES})
    return "Modo holograma desactivado" if hologram.stop() else "El modo holograma ya estaba apagado"


def orb_on(boot: bool = False) -> str:
    started = desktop.start(JARVIS_BOOT="1" if boot else "0")
    return "Orbe de escritorio activado" if started else "El orbe ya está en pantalla"


def orb_off() -> str:
    return "Orbe de escritorio oculto" if desktop.stop() else "El orbe ya estaba oculto"


def subtitles_on() -> str:
    settings["subtitles"] = True
    if not desktop.running():
        orb_on()
    return "Subtítulos activados: lo que digamos aparecerá grande en pantalla"


def subtitles_off() -> str:
    settings["subtitles"] = False
    return "Subtítulos desactivados"


HOW_TO = {
    "draw": "pellizca y mueve la mano para dibujar; puño para borrar",
    "globe": "pellizca y arrastra para girarla; con dos manos, agrándala",
    "solar": "pellizca y arrastra para girarlo; un pellizco rápido sobre un planeta muestra sus datos",
    "earth": "pellizca y arrastra para girarlo; pídeme el clima de una ciudad para marcarla",
    "scanner": "mira a la cámara",
    "effects": "mueve los dedos; junta las dos palmas abiertas para crear la bola de energía y cierra los puños para soltarla",
    "keyboard": "pellizca las teclas; escribe en la ventana activa",
    "notes": "pellizca una nota para moverla; un puño sobre ella la borra",
    "visualizer": "pon música",
}


def holo(name: str, enabled: bool = True) -> str:
    """Muestra u oculta un holograma; enciende el modo holograma si hace falta."""
    if name not in HOLO_MODES:
        raise ValueError(f"Holograma desconocido: {name}. Disponibles: {', '.join(HOLO_MODES)}")
    if not enabled:
        settings[name] = False
        return f"{HOLO_MODES[name].capitalize()}: oculto"
    hologram_on()
    if name in EXCLUSIVE:
        settings.update({other: False for other in EXCLUSIVE})
    settings[name] = True
    return f"{HOLO_MODES[name].capitalize()} en pantalla: {HOW_TO[name]}"


def draw_on() -> str:
    return holo("draw")


def draw_off() -> str:
    return holo("draw", False)


def globe_on() -> str:
    return holo("globe")


def globe_off() -> str:
    return holo("globe", False)


def earth_city(city: str) -> str:
    """Marca una ciudad con su clima en el globo terráqueo."""
    city = city.strip()
    cities = [c for c in settings["earth_cities"] if c.lower() != city.lower()]
    settings["earth_cities"] = (cities + [city])[-6:]
    message = holo("earth")
    return f"{message}. Marqué {city} con su clima"


def create_note(text: str) -> str:
    item = notes.add(text)
    settings["notes"] = True
    shown = "Se ve en el holograma" if hologram_running() else "La verás cuando actives el holograma"
    return f"Nota creada ({item['id']}). {shown}"


def delete_note(id: str) -> str:
    return f"Nota borrada: {notes.delete(id)['text']}"


def list_notes() -> list[dict]:
    return [{"id": item["id"], "text": item["text"]} for item in notes.all()]


def set_timer(minutes: float | None = None, seconds: float | None = None, label: str = "") -> dict:
    total = float(minutes or 0) * 60 + float(seconds or 0)
    if total <= 0:
        raise ValueError("Indica minutes o seconds")
    item = reminders.add(label or "temporizador", datetime.now() + timedelta(seconds=total), alarm=True, kind="timer")
    return {"id": item["id"], "ends": item["due"], "seconds": round(total)}


def web_search(query: str) -> str:
    from . import brain

    return brain.search(query)


def record_start() -> str:
    return recorder.start()


def record_stop() -> str:
    return recorder.stop()


def _hook(name: str):
    if name not in hooks:
        raise RuntimeError("Esa función necesita que Jarvis esté corriendo con la escucha de la PC")
    return hooks[name]


def dictation_on() -> str:
    _hook("dictation")(True)
    return "Modo dictado activado: lo que digas se escribirá en la ventana activa hasta que digas «fin del dictado»"


def dictation_off() -> str:
    _hook("dictation")(False)
    return "Modo dictado desactivado"


def presence_on() -> str:
    _hook("presence").set_enabled(True)
    return "Detección de presencia activada"


def presence_off() -> str:
    _hook("presence").set_enabled(False)
    return "Detección de presencia desactivada; la cámara queda libre"


def learn_face(name: str) -> str:
    return _hook("presence").enroll(name)


def forget_face(name: str | None = None) -> str:
    removed = _hook("presence").forget(name)
    if not removed:
        raise ValueError("No tenía esa cara guardada")
    return f"Olvidé {'a ' + name if name else 'todas las caras'}"


def guard_on() -> str:
    presence = _hook("presence")
    presence.set_guard(True)
    if not presence.known_people():
        return "Modo guardia activado, pero aún no conozco tu cara: pídeme «aprende mi cara»"
    return "Modo guardia activado: si se sienta alguien que no conozco, bloquearé la PC"


def guard_off() -> str:
    _hook("presence").set_guard(False)
    return "Modo guardia desactivado"


def look_screen(question: str = "Describe lo que hay en la pantalla.") -> str:
    from . import brain, screen

    screen.save_png(brain.VISION_DIR / "screen.png")
    return brain.look(question)


def remember(fact: str) -> str:
    return memory.remember(fact)


def forget(text: str) -> str:
    return memory.forget(text)


def set_reminder(text: str, minutes: float | None = None, at: str | None = None, alarm: bool = False) -> dict:
    item = reminders.add(text, parse_when(minutes, at), alarm)
    return {"id": item["id"], "due": item["due"], "text": item["text"], "alarm": item["alarm"]}


def list_reminders() -> list[dict]:
    return reminders.all()


def cancel_reminder(id: str) -> str:
    item = reminders.cancel(id)
    return f"Cancelado: {item['text']}"


def run_routine(name: str) -> dict:
    """Ejecuta los pasos seguros; los que requieren permiso se devuelven para pedirlos aparte."""
    routine = routines.get(name)
    results, needs_approval = [], []
    for action in routine["actions"]:
        tool, args = action["tool"], action.get("args") or {}
        if tool in ("run_routine", "save_routine"):
            results.append({"tool": tool, "outcome": {"ok": False, "error": "Una rutina no puede lanzar rutinas"}})
        elif needs_confirmation(tool, args):
            needs_approval.append({"tool": tool, "args": args})
        else:
            results.append({"tool": tool, "args": args, "outcome": execute(tool, args)})
    return {"say": routine.get("say", ""), "results": results, "needs_approval": needs_approval}


def save_routine(name: str, actions: list, say: str = "") -> str:
    unknown = [action.get("tool") for action in actions if action.get("tool") not in ALL_TOOLS]
    if unknown:
        raise ValueError(f"Herramientas desconocidas: {', '.join(map(str, unknown))}")
    routines.save(name, actions, say)
    return f"Rutina guardada: {name}"


def delete_routine(name: str) -> str:
    routines.delete(name)
    return f"Rutina eliminada: {name}"


def list_routines() -> dict:
    return routines.all()


def briefing(name: str = "") -> str:
    upcoming = [item for item in reminders.all() if item.get("kind") != "timer"]
    return briefing_module.build(datetime.now(), system_status(), briefing_module.weather(), upcoming, name)


def share_file(path: str) -> str:
    name = files.share_file(path)
    if "notify" in hooks:
        hooks["notify"]("Archivo listo", f"{name} está en Archivos de Jarvis")
    return f"Copiado a {files.SHARE_DIR}: {name}. Ya se puede bajar desde el celular, en ARCHIVOS."


def list_shared_files() -> list[dict]:
    return files.list_files()


SAFE_TOOLS = {
    "system_status": system_status,
    "type_text": type_text,
    "press_keys": press_keys,
    "hologram_on": hologram_on,
    "hologram_off": hologram_off,
    "list_processes": list_processes,
    "open_app": open_app,
    "open_url": open_url,
    "media_key": media_key,
    "lock_pc": lock_pc,
    "kill_process": kill_process,
    "run_powershell": run_powershell,
    "dictation_on": dictation_on,
    "dictation_off": dictation_off,
    "presence_on": presence_on,
    "presence_off": presence_off,
    "look_screen": look_screen,
    "remember": remember,
    "forget": forget,
    "set_reminder": set_reminder,
    "list_reminders": list_reminders,
    "cancel_reminder": cancel_reminder,
    "run_routine": run_routine,
    "save_routine": save_routine,
    "delete_routine": delete_routine,
    "list_routines": list_routines,
    "briefing": briefing,
    "share_file": share_file,
    "list_shared_files": list_shared_files,
    "web_search": web_search,
    "learn_face": learn_face,
    "forget_face": forget_face,
    "guard_on": guard_on,
    "guard_off": guard_off,
    "orb_on": orb_on,
    "orb_off": orb_off,
    "subtitles_on": subtitles_on,
    "subtitles_off": subtitles_off,
    "draw_on": draw_on,
    "draw_off": draw_off,
    "globe_on": globe_on,
    "globe_off": globe_off,
    "holo": holo,
    "earth_city": earth_city,
    "create_note": create_note,
    "delete_note": delete_note,
    "list_notes": list_notes,
    "set_timer": set_timer,
    "record_start": record_start,
    "record_stop": record_stop,
}

CONFIRM_TOOLS = {
    "shutdown_pc": shutdown_pc,
    "restart_pc": restart_pc,
}

ALL_TOOLS = SAFE_TOOLS | CONFIRM_TOOLS

SENSITIVE_COMMAND = re.compile(
    r"shutdown|stop-computer|restart-computer|powrprof|win32shutdown|initiatesystemshutdown|exitwindows"
    r"|remove-item|clear-recyclebin|format-volume|sdelete|deletefile|recycle"
    r"|(?:\.|::)delete\b|\b(?:rm|ri|del|erase|rd|rmdir)\b|\brobocopy\b.*/(?:mir|purge)\b",
    re.IGNORECASE,
)


def needs_confirmation(tool: str, args: dict | None = None) -> bool:
    """Lo desconocido también se trata como sensible; execute() luego lo rechaza."""
    if tool == "run_powershell":
        return bool(SENSITIVE_COMMAND.search(str((args or {}).get("command", ""))))
    if tool == "press_keys":
        # Supr en el Explorador elimina archivos.
        return bool(re.search(r"delete|supr", str((args or {}).get("keys", "")), re.IGNORECASE))
    return tool not in SAFE_TOOLS


def execute(tool: str, args: dict | None = None) -> dict:
    function = ALL_TOOLS.get(tool)
    if function is None:
        return {"ok": False, "error": f"Herramienta desconocida: {tool}"}
    try:
        return {"ok": True, "result": function(**(args or {}))}
    except Exception as error:
        return {"ok": False, "error": str(error)}
