import asyncio
import logging
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import briefing, files, push, recorder, screen, speech, tools, voice
from .brain import DATA_DIR, Brain, BrainError, audit
from .events import Events
from .listener import Listener
from .presence import Presence
from .reminders import reminders
from .speaker import Speaker, startup_sound

MAX_AUDIO_BYTES = 25 * 1024 * 1024
TOKEN_FILE = DATA_DIR / "token.txt"
STATIC = Path(__file__).resolve().parent / "static"
INDEX = STATIC / "index.html"
QUICK_ACTIONS = {
    **{key: ("media_key", {"key": key}) for key in tools.MEDIA_KEYS},
    "lock": ("lock_pc", {}),
}
WELCOME_BACK_AFTER = 10 * 60  # segundos fuera para que salude al volver
BRIEFING_DELAY = 20  # sin detección de presencia, el informe del día se da al arrancar
TOGGLES = {  # lo que la página puede encender y apagar directamente
    "subtitles": ("subtitles_on", "subtitles_off"),
    "draw": ("draw_on", "draw_off"),
    "globe": ("globe_on", "globe_off"),
    "orb": ("orb_on", "orb_off"),
    "guard": ("guard_on", "guard_off"),
    "record": ("record_start", "record_stop"),
}

log = logging.getLogger("jarvis.server")


def load_token() -> str:
    DATA_DIR.mkdir(exist_ok=True)
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


TOKEN = load_token()
brain = Brain()
events = Events()
speaker = Speaker()
listener = Listener(brain, events, speaker)


def in_background(function, *args) -> None:
    threading.Thread(target=function, args=args, daemon=True).start()


def notify_phone(title: str, body: str) -> None:
    def send():
        try:
            push.send(title, body)
        except Exception:
            log.exception("No pude enviar la notificación")
    in_background(send)


_announcing = threading.Lock()


def announce(text: str, title: str | None = None, alarm: bool = False, then=None) -> None:
    """Jarvis habla por su cuenta: en la página, por los altavoces y, con title, en el celular.
    Los avisos van en fila para no pisarse. then: qué hacer cuando termine de hablar."""
    events.publish("jarvis", text=text, pending=None)

    def speak():
        with _announcing:
            speaker.say(text, alarm=alarm, wait=True)
        if then:
            then()
    in_background(speak)
    if title:
        notify_phone(title, text)


def on_reminder(item: dict) -> None:
    audit("reminder_due", **item)
    if item.get("alarm"):
        announce(f"Alarma: {item['text']}. Repito: {item['text']}.", title="⏰ Alarma", alarm=True)
    else:
        announce(f"Recordatorio: {item['text']}", title="Recordatorio", alarm=True)


def give_briefing(name: str | None = None) -> None:
    briefing.mark_done()
    announce(tools.briefing(name or ""))


def on_presence(kind: str, info: dict) -> None:
    audit("presence_" + kind, **info)
    if kind == "arrive":
        name, away = info.get("name"), info.get("away")
        if not briefing.done_today():
            give_briefing(name)
        elif away is not None and away >= WELCOME_BACK_AFTER:
            announce(f"Bienvenido de nuevo{', ' + name if name else ''}. Estuviste fuera {round(away / 60)} minutos.")
    elif kind == "leave":
        tools.lock_pc()
        events.publish("jarvis", text="No te vi frente a la PC: la bloqueé.", pending=None)
    elif kind == "stranger":
        notify_phone("⚠ Jarvis", "Alguien que no conozco se sentó frente a tu PC. La bloqueé.")
        announce("No te reconozco. Por seguridad, bloqueo el equipo.", then=tools.lock_pc)


presence = Presence(on_presence, paused=tools.hologram_running)
reminders.on_due = on_reminder
tools.hooks.update(dictation=listener.set_dictation, presence=presence, notify=notify_phone)


def boot() -> None:
    """Arranque: la animación del orbe, el sonido y "sistemas en línea"."""
    if os.environ.get("JARVIS_ORB", "1") != "0":
        try:
            tools.orb_on(boot=True)
        except Exception:
            log.exception("No pude mostrar el orbe")
    with _announcing:
        speaker.play(startup_sound(), 22050, wait=True)
    announce("Todos los sistemas en línea.")


def briefing_without_presence() -> None:
    time.sleep(BRIEFING_DELAY)
    if not presence.enabled or presence.state.startswith("error"):
        if not briefing.done_today():
            give_briefing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # JARVIS_WAKE=0 apaga la escucha de fondo (por ejemplo, en pruebas).
    if os.environ.get("JARVIS_WAKE", "1") != "0":
        listener.start()
    reminders.start()
    presence.start()
    in_background(speech.warm_up)
    in_background(boot)
    in_background(briefing_without_presence)
    yield
    # Al cerrar Jarvis: guardar la grabación y cerrar sus ventanas.
    recorder.stop()
    tools.hologram.stop()
    tools.desktop.stop()


app = FastAPI(title="Jarvis", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def require_token(authorization: str = Header(default="")) -> None:
    if not secrets.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(status_code=401, detail="Token inválido")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class ConfirmRequest(BaseModel):
    approved: bool


class ListenerRequest(BaseModel):
    enabled: bool


class ClickRequest(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    button: str = Field(default="left", pattern="^(left|right)$")


class ScrollRequest(BaseModel):
    steps: int = Field(ge=-20, le=20)


class TypeRequest(BaseModel):
    text: str = Field(default="", max_length=4000)
    keys: str = Field(default="", max_length=60)


class SubscribeRequest(BaseModel):
    subscription: dict


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX)


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(STATIC / "sw.js", media_type="text/javascript")


@app.get("/api/status", dependencies=[Depends(require_token)])
async def status() -> dict:
    return await asyncio.to_thread(tools.system_status)


@app.get("/api/events", dependencies=[Depends(require_token)])
def get_events(after: int = -1) -> dict:
    items, last = events.since(after)
    return {
        "events": items,
        "last": last,
        "listener": {"enabled": listener.enabled, "state": listener.state, "dictation": listener.dictation},
        "hologram": tools.hologram_running(),
        "presence": {"enabled": presence.enabled, "state": presence.state, "guard": presence.guard,
                     "people": presence.known_people()},
        "whisper": speech.device,
        "modes": {**tools.settings, "orb": tools.desktop.running()},
        "recording": recorder.status(),
    }


@app.post("/api/toggle/{name}", dependencies=[Depends(require_token)])
async def toggle(name: str, request: ListenerRequest) -> dict:
    if name not in TOGGLES:
        raise HTTPException(status_code=404, detail="Modo desconocido")
    tool = TOGGLES[name][0 if request.enabled else 1]
    outcome = await asyncio.to_thread(tools.execute, tool)
    audit("toggle", tool=tool, ok=outcome["ok"])
    if not outcome["ok"]:
        raise HTTPException(status_code=409, detail=outcome["error"])
    return {"message": outcome["result"]}


@app.post("/api/hologram", dependencies=[Depends(require_token)])
async def set_hologram(request: ListenerRequest) -> dict:
    tool = "hologram_on" if request.enabled else "hologram_off"
    outcome = await asyncio.to_thread(tools.execute, tool)
    audit("hologram", tool=tool, ok=outcome["ok"])
    if not outcome["ok"]:
        raise HTTPException(status_code=500, detail=outcome["error"])
    return {"running": tools.hologram_running(), "message": outcome["result"]}


@app.post("/api/listener", dependencies=[Depends(require_token)])
def set_listener(request: ListenerRequest) -> dict:
    listener.set_enabled(request.enabled)
    return {"enabled": listener.enabled, "state": listener.state, "dictation": listener.dictation}


@app.post("/api/dictation", dependencies=[Depends(require_token)])
def set_dictation(request: ListenerRequest) -> dict:
    try:
        listener.set_dictation(request.enabled)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"dictation": listener.dictation}


@app.post("/api/presence", dependencies=[Depends(require_token)])
def set_presence(request: ListenerRequest) -> dict:
    presence.set_enabled(request.enabled)
    audit("presence", enabled=request.enabled)
    return {"enabled": presence.enabled, "state": presence.state}


@app.post("/api/quick/{action}", dependencies=[Depends(require_token)])
async def quick(action: str) -> dict:
    if action not in QUICK_ACTIONS:
        raise HTTPException(status_code=404, detail="Acción desconocida")
    tool, args = QUICK_ACTIONS[action]
    outcome = await asyncio.to_thread(tools.execute, tool, args)
    audit("quick", tool=tool, args=args, ok=outcome["ok"])
    if not outcome["ok"]:
        raise HTTPException(status_code=500, detail=outcome["error"])
    return outcome


@app.post("/api/chat", dependencies=[Depends(require_token)])
async def chat(request: ChatRequest) -> dict:
    try:
        return await asyncio.to_thread(brain.chat, request.message)
    except BrainError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/transcribe", dependencies=[Depends(require_token)])
async def transcribe(request: Request) -> dict:
    audio = await request.body()
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="El audio está vacío o es demasiado largo")
    try:
        return {"text": await asyncio.to_thread(speech.transcribe, audio)}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"No pude transcribir el audio: {error}") from error


@app.post("/api/speak", dependencies=[Depends(require_token)])
async def speak(request: SpeakRequest) -> Response:
    try:
        audio = await asyncio.to_thread(voice.synthesize, request.text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"No pude generar la voz: {error}") from error
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/confirm/{pending_id}", dependencies=[Depends(require_token)])
async def confirm(pending_id: str, request: ConfirmRequest) -> dict:
    try:
        return await asyncio.to_thread(brain.resolve, pending_id, request.approved)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Esa confirmación ya no existe") from error
    except BrainError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


# Pantalla en vivo desde el celular.

@app.get("/api/screen", dependencies=[Depends(require_token)])
async def screen_image(width: int = 1280, quality: int = 60) -> Response:
    width, quality = max(320, min(width, 2560)), max(20, min(quality, 90))
    image = await asyncio.to_thread(screen.jpeg, width, quality)
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/screen/click", dependencies=[Depends(require_token)])
async def screen_click(request: ClickRequest) -> dict:
    await asyncio.to_thread(screen.click, request.x, request.y, request.button)
    return {"ok": True}


@app.post("/api/screen/scroll", dependencies=[Depends(require_token)])
async def screen_scroll(request: ScrollRequest) -> dict:
    await asyncio.to_thread(screen.scroll, request.steps)
    return {"ok": True}


@app.post("/api/screen/type", dependencies=[Depends(require_token)])
async def screen_type(request: TypeRequest) -> dict:
    if request.keys:
        # Supr en el Explorador elimina archivos: eso se pide por el chat, con aprobación.
        if tools.needs_confirmation("press_keys", {"keys": request.keys}):
            raise HTTPException(status_code=403, detail="Esa tecla puede eliminar archivos; pídela por el chat")
        outcome = await asyncio.to_thread(tools.execute, "press_keys", {"keys": request.keys})
    else:
        outcome = await asyncio.to_thread(tools.execute, "type_text", {"text": request.text})
    if not outcome["ok"]:
        raise HTTPException(status_code=400, detail=outcome["error"])
    return outcome


# Archivos entre el celular y la PC (carpeta Descargas\Jarvis).

@app.get("/api/files", dependencies=[Depends(require_token)])
def list_shared() -> dict:
    return {"folder": str(files.SHARE_DIR), "files": files.list_files()}


@app.post("/api/files", dependencies=[Depends(require_token)])
async def upload(request: Request, name: str) -> dict:
    files.SHARE_DIR.mkdir(parents=True, exist_ok=True)
    target = files.unique_path(files.SHARE_DIR, files.safe_name(name))
    partial = target.with_name(target.name + ".subiendo")
    size = 0
    try:
        with partial.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > files.MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail="El archivo pasa de 2 GB")
                output.write(chunk)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    audit("upload", name=target.name, size=size)
    return {"name": target.name, "size": size}


@app.get("/api/files/{name}", dependencies=[Depends(require_token)])
def download(name: str) -> FileResponse:
    try:
        path = files.shared_file(name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="No existe ese archivo") from error
    return FileResponse(path, filename=path.name)


# Notificaciones push al celular.

@app.get("/api/push/key", dependencies=[Depends(require_token)])
async def push_key() -> dict:
    return {"key": await asyncio.to_thread(push.public_key)}


@app.post("/api/push/subscribe", dependencies=[Depends(require_token)])
async def push_subscribe(request: SubscribeRequest) -> dict:
    try:
        push.subscribe(request.subscription)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    sent = await asyncio.to_thread(push.send, "Jarvis", "Notificaciones activadas.")
    return {"sent": sent}
