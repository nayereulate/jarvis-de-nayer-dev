"""Comandos locales: las órdenes del día a día se resuelven aquí al instante, sin pasar por Claude.

route(texto) devuelve la respuesta si la frase es un comando conocido, o None para que la responda Claude.
Las frases compuestas ("abre Chrome y busca…") y las preguntas libres siempre van a Claude.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

from . import briefing, tools, winctl
from .textutil import NUMBERS, UNITS, align, number  # noqa: F401  (los tests los usan desde aquí)
from .memory import memory
from .notes import notes
from .reminders import reminders


class CommandError(Exception):
    pass


# ---------------------------------------------------------------- Texto

def parse_duration(text: str) -> float | None:
    """'5 minutos', 'media hora', 'una hora y media', '1 hora y 20 minutos' -> segundos."""
    words = text.replace("y media", "y_media").replace("y medio", "y_medio").split()
    total, pending, last_unit, found = 0.0, None, 0, False
    for word in words:
        value = number(word)
        if word in ("y", "de"):
            continue
        if value is not None:
            pending = value if pending is None else pending + value
        elif word in UNITS:
            last_unit = UNITS[word]
            total += (1 if pending is None else pending) * last_unit
            pending, found = None, True
        elif word in ("y_media", "y_medio") and last_unit:
            total += last_unit / 2
        else:
            return None
    return total if found and pending is None and total > 0 else None


def parse_clock(text: str, now: datetime) -> datetime | None:
    """'7', '7:30', '7 y media', 'siete y cuarto de la tarde', '19:00' -> la próxima vez que sea esa hora."""
    text = re.sub(r"^(?:a\s+)?(?:las|la)\s+", "", text.strip())
    period = None
    found = re.search(r"\s+(?:de|en|por)\s+la\s+(manana|tarde|noche|madrugada)$|\s+(am|pm|a m|p m)$", text)
    if found:
        period = found.group(1) or found.group(2).replace(" ", "")
        text = text[:found.start()]
    match = re.fullmatch(r"(\S+?)(?::(\d{2}))?(?:\s+(?:y\s+)?(media|cuarto|\S+)(?:\s+minutos)?)?", text.strip())
    if not match:
        return None
    hour = number(match.group(1))
    if hour is None or hour != int(hour) or not 0 <= hour <= 23:
        return None
    minute = 0
    if match.group(2):
        minute = int(match.group(2))
    elif match.group(3):
        minute = {"media": 30, "cuarto": 15}.get(match.group(3)) or number(match.group(3))
        if minute is None or not 0 <= minute < 60:
            return None
    hour, minute = int(hour), int(minute)
    if period in ("tarde", "noche", "pm") and hour < 12:
        hour += 12
    elif period in ("manana", "madrugada", "am") and hour == 12:
        hour = 0
    options = [hour] if period or hour >= 13 or hour == 0 else [hour, hour + 12]
    moments = []
    for h in options:
        moment = now.replace(hour=h % 24, minute=minute, second=0, microsecond=0)
        moments.append(moment if moment > now else moment + timedelta(days=1))
    return min(moments)  # sin "de la tarde", la próxima vez que el reloj marque esa hora


# ---------------------------------------------------------------- Registro de comandos

PREFIX = r"\s*(?:(?:hey|oye|ok|okay|ey)\s+)?(?:jarvis\b\s*)?(?:(?:por\s+favor|porfa|puedes|podrias|me\s+puedes|me\s+podrias|quiero\s+que|necesito\s+que)\s+)*"
SUFFIX = r"\s*(?:jarvis)?\s*(?:por\s+favor|porfa)?\s*(?:jarvis)?\s*$"
# Frases con dos órdenes van a Claude, que sabe encadenarlas.
COMPOUND = re.compile(r"\s(?:y|luego|despues|tambien|y\s+luego|y\s+despues)\s+(?:abre|busca|pon|cierra|escribe|crea|haz|dime|apaga|muestra|activa|reproduce|manda|envia|ve|cambia)\b")


@dataclass
class Command:
    name: str
    regex: re.Pattern
    handler: object
    category: str
    examples: tuple
    free_text: bool


COMMANDS: list[Command] = []


def command(pattern: str, category: str, *examples: str, free_text: bool = False):
    """Los espacios del patrón aceptan uno o más espacios (los signos quitados dejan espacios dobles)."""
    def register(handler):
        regex = re.compile(PREFIX + "(?:" + pattern.replace(" ", r"\s+") + ")" + SUFFIX)
        COMMANDS.append(Command(handler.__name__, regex, handler, category, examples, free_text))
        return handler
    return register


class Context:
    def __init__(self, original: str, aligned: str, match: re.Match):
        self.original, self.aligned, self.match = original, aligned, match

    def text(self, *names) -> str | None:
        """El grupo capturado tal como se dijo (con tildes y mayúsculas)."""
        for name in names:
            if self.match.group(name) is not None:
                start, end = self.match.span(name)
                return self.original[start:end].strip(" :,")
        return None

    def plain(self, *names) -> str | None:
        for name in names:
            if self.match.group(name) is not None:
                return self.match.group(name).strip(" :,")
        return None


def do(tool: str, **args):
    outcome = tools.execute(tool, args)
    if not outcome["ok"]:
        raise CommandError(outcome["error"])
    return outcome["result"]


def keys(combo: str, say: str = "Listo."):
    do("press_keys", keys=combo)
    return {"say": say}


def said(text: str) -> dict:
    return {"say": text}


def confirm(say: str, *actions: dict) -> dict:
    return {"say": say, "confirm": list(actions)}


def route(text: str) -> dict | None:
    aligned = align(text)
    if not aligned.strip():
        return None
    if COMPOUND.search(aligned):
        return None  # dos órdenes en una frase: Claude sabe encadenarlas
    too_long = len(aligned.split()) > 14
    for cmd in COMMANDS:
        if too_long and not cmd.free_text:
            continue
        match = cmd.regex.match(aligned)
        if not match:
            continue
        try:
            result = cmd.handler(Context(text, aligned, match))
        except CommandError as error:
            return {"say": str(error), "command": cmd.name}
        if result is None:
            continue  # el patrón encajó pero no era esto (por ejemplo, "abre" algo que no es un holograma)
        result["command"] = cmd.name
        return result
    return None


def catalog() -> list[dict]:
    """La lista de comandos para la página, por categoría."""
    groups = {}
    for cmd in COMMANDS:
        if cmd.examples:
            groups.setdefault(cmd.category, []).extend(cmd.examples)
    return [{"category": name, "examples": examples} for name, examples in groups.items()]


# ---------------------------------------------------------------- Escribir, notas y memoria (texto libre)

@command(r"(?:escribe|escribir|escribeme|teclea el texto)(?:\s*:)? (?P<text>.+)", "Escribir y teclado",
         "escribe: hola, ¿cómo estás?", free_text=True)
def write(c):
    do("type_text", text=c.text("text"))
    return said("Escrito.")


@command(r"(?:crea|haz|toma|agrega|anade|nueva)(?: una)? nota(?:\s*:)?(?: que diga| de| sobre)? (?P<text>.+)|(?:anota|apunta)(?:\s*:)? (?P<text2>.+)",
         "Notas y memoria", "crea una nota: comprar leche", "anota llamar al banco", free_text=True)
def note(c):
    do("create_note", text=c.text("text", "text2"))
    return said("Nota creada.")


@command(r"(?:borra|elimina|quita)(?: todas)? (?:las|mis) notas", "Notas y memoria", "borra todas las notas")
def clear_notes(c):
    for item in notes.all():
        notes.delete(item["id"])
    return said("Borré tus notas.")


@command(r"recuerda que (?P<fact>.+)", "Notas y memoria", "recuerda que mi color favorito es el azul", free_text=True)
def remember(c):
    do("remember", fact=c.text("fact"))
    return said("Lo recordaré.")


@command(r"olvida (?:mi cara|mi rostro)", "Presencia y cámara", "olvida mi cara")
def forget_face(c):
    from . import tools as t

    presence = t.hooks.get("presence")
    people = presence.known_people() if presence else []
    if len(people) != 1:
        return None  # con varias personas, Claude pregunta a quién
    do("forget_face", name=people[0])
    return said(f"Olvidé la cara de {people[0]}.")


@command(r"olvida(?: que| lo de)? (?P<fact>.+)", "Notas y memoria", "olvida lo de mi color favorito", free_text=True)
def forget(c):
    do("forget", text=c.plain("fact"))
    return said("Olvidado.")


@command(r"aprende (?:mi cara|mi rostro|quien soy)(?:,? (?:me llamo|soy|mi nombre es) (?P<name>.+))?",
         "Presencia y cámara", "aprende mi cara, me llamo Nayer")
def learn_face(c):
    name = c.text("name")
    if not name:
        return said("Dime tu nombre: «aprende mi cara, me llamo…».")
    return said(do("learn_face", name=name.title()))


# ---------------------------------------------------------------- Recordatorios, alarmas y temporizadores

DURATION = r"(?:\S+ ){0,3}?(?:segundos?|minutos?|horas?|seg|min)(?: y (?:media|medio|\S+ (?:minutos?|segundos?)))?"


@command(r"(?:(?:pon|crea|inicia|programa|activa) )?(?:un )?temporizador(?: de| por| para)? (?P<dur>.+?)(?: para (?P<label>.+))?"
         r"|(?:avisame|cuenta) (?:en )?(?P<dur2>" + DURATION + r")(?: para (?P<label2>.+))?",
         "Tiempo", "pon un temporizador de 5 minutos", "temporizador de media hora para el té", "avísame en 10 minutos",
         free_text=True)
def timer(c):
    seconds = parse_duration(c.plain("dur", "dur2") or "")
    if seconds is None:
        return None
    label = c.text("label", "label2") or ""
    do("set_timer", seconds=seconds, label=label)
    minutes, rest = divmod(round(seconds), 60)
    length = f"{minutes} minuto{'s' if minutes != 1 else ''}" if minutes else ""
    length += (" y " if minutes and rest else "") + (f"{rest} segundos" if rest else "")
    return said(f"Temporizador de {length}{' para ' + label if label else ''}.")


@command(r"recuerdame (?:en )?(?P<dur>" + DURATION + r") (?:que |de |a )?(?P<text>.+)"
         r"|recuerdame (?P<text2>.+?) en (?P<dur2>" + DURATION + r")",
         "Tiempo", "recuérdame en 20 minutos sacar la comida", free_text=True)
def remind_in(c):
    seconds = parse_duration(c.plain("dur", "dur2"))
    if seconds is None:
        return None
    text = c.text("text", "text2")
    do("set_reminder", text=text, minutes=seconds / 60)
    return said(f"Te lo recordaré en {round(seconds / 60)} minutos.")


@command(r"recuerdame a las (?P<clock>\S+(?::\d\d)?(?: y \S+)?(?: (?:de|en|por) la (?:manana|tarde|noche|madrugada))?) (?:que |de |a )?(?P<text>.+)"
         r"|recuerdame (?P<text2>.+?) a las (?P<clock2>.+)",
         "Tiempo", "recuérdame a las 6 de la tarde llamar a mamá", free_text=True)
def remind_at(c):
    moment = parse_clock(c.plain("clock", "clock2"), datetime.now())
    if moment is None:
        return None  # "mañana", "el lunes"…: Claude lo entiende mejor
    do("set_reminder", text=c.text("text", "text2"), at=moment.isoformat(timespec="minutes"))
    return said(f"Te lo recordaré a las {moment:%H:%M}.")


@command(r"(?:(?:pon|programa|crea|activa) )?(?:una )?alarma (?:para |a )?(?:las )?(?P<clock>.+?)(?: para (?P<label>.+))?"
         r"|despiertame a las (?P<clock2>.+)",
         "Tiempo", "pon una alarma a las 7 de la mañana", "despiértame a las 6 y media")
def alarm(c):
    moment = parse_clock(c.plain("clock", "clock2"), datetime.now())
    if moment is None:
        return None
    do("set_reminder", text=c.text("label") or "alarma", at=moment.isoformat(timespec="minutes"), alarm=True)
    day = "mañana" if moment.date() > datetime.now().date() else "hoy"
    return said(f"Alarma para {day} a las {moment:%H:%M}.")


@command(r"(?:que |cuales son mis |mis )?(?:recordatorios|alarmas|temporizadores)(?: tengo| hay)?|que (?:recordatorios|alarmas|temporizadores) (?:tengo|hay)",
         "Tiempo", "¿qué recordatorios tengo?")
def list_reminders(c):
    items = reminders.all()
    if not items:
        return said("No tienes recordatorios, alarmas ni temporizadores.")
    parts = [f"{'temporizador' if i.get('kind') == 'timer' else 'alarma' if i.get('alarm') else 'recordatorio'} "
             f"a las {datetime.fromisoformat(i['due']):%H:%M}: {i['text']}" for i in items[:6]]
    return said(f"Tienes {len(items)}: " + "; ".join(parts) + ".")


@command(r"(?:cancela|quita|para|deten|borra|elimina)(?: el| la| los| las| todos los| todas las)? (?P<what>temporizador(?:es)?|alarmas?|recordatorios?)",
         "Tiempo", "cancela el temporizador", "borra las alarmas")
def cancel(c):
    what = c.plain("what")
    kind = "timer" if what.startswith("temporizador") else "alarm" if what.startswith("alarma") else "reminder"
    removed = 0
    for item in reminders.all():
        item_kind = "timer" if item.get("kind") == "timer" else "alarm" if item.get("alarm") else "reminder"
        if item_kind == kind:
            reminders.cancel(item["id"])
            removed += 1
    return said(f"Cancelé {removed}." if removed else "No había ninguno.")


# ---------------------------------------------------------------- Hora, clima, estado

@command(r"(?:que hora es|que horas son|dime la hora|la hora|me dices la hora)", "Información", "¿qué hora es?")
def what_time(c):
    now = datetime.now()
    return said(f"Son las {now:%H:%M}.")


DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


@command(r"(?:que dia es(?: hoy)?|que fecha es(?: hoy)?|a que estamos(?: hoy)?|(?:dime )?la fecha(?: de hoy)?|que dia)",
         "Información", "¿qué día es hoy?")
def what_day(c):
    now = datetime.now()
    return said(f"Hoy es {DAYS[now.weekday()]} {now.day} de {MONTHS[now.month - 1]} de {now.year}.")


@command(r"(?:que |como esta el |como esta )?(?:clima|tiempo|temperatura)(?: hace)?(?: hoy)?(?: en (?P<city>.+))?"
         r"|que tiempo hace(?: hoy)?(?: en (?P<city2>.+))?|va a llover(?: hoy)?(?: en (?P<city3>.+))?",
         "Información", "¿qué clima hace?", "clima en Madrid")
def weather(c):
    city = c.text("city", "city2", "city3")
    text = briefing.weather(city)
    if not text:
        raise CommandError("No pude consultar el clima ahora.")
    return said(text)


@command(r"(?:dime el |como esta el )?estado(?: de la pc| del sistema| de la computadora| del equipo)?"
         r"|como esta la (?:pc|computadora|compu)|(?:uso de|cuanta|cuanto) (?:cpu|ram|memoria|disco)",
         "Información", "estado de la PC")
def status(c):
    s = do("system_status")
    return said(f"CPU al {s['cpu_percent']:.0f} por ciento, RAM al {s['ram_percent']:.0f} y disco al {s['disk_percent']:.0f}.")


@command(r"(?:dame |hazme )?(?:el )?(?:informe|resumen)(?: del dia| de hoy| diario)?|buenos dias", "Información",
         "dame el informe", "buenos días")
def report(c):
    return said(do("briefing"))


@command(r"(?:que puedes hacer|ayuda|que comandos (?:hay|tienes|conoces|entiendes)|(?:lista de |dime los )?comandos)",
         "Jarvis", "¿qué puedes hacer?")
def help_(c):
    return said("Puedo controlar la música, abrir y cerrar apps, navegar por páginas y pestañas, manejar ventanas, "
                "escribir, poner temporizadores, alarmas y notas, y mostrar hologramas. "
                "La lista completa está en la página de Jarvis, en el botón COMANDOS.")


@command(r"(?:hola|que tal|buenas(?: tardes| noches)?|como estas|hey)", "Jarvis", "hola")
def hello(c):
    name = next((fact.split()[-1] for fact in memory.facts() if "llama" in fact.lower()), "")
    return said(f"Hola{', ' + name if name else ''}. ¿En qué te ayudo?")


@command(r"(?:muchas )?gracias|genial|perfecto|excelente|buen trabajo", "Jarvis", "gracias")
def thanks(c):
    return said("A tu servicio.")


@command(r"(?:callate|para de hablar|basta|ya|silencio jarvis|cancela|nada|olvidalo)", "Jarvis", "cállate", "olvídalo")
def stop(c):
    return said("")  # al decir "Hey Jarvis" ya dejó de hablar; no hace falta responder


# ---------------------------------------------------------------- Modos de Jarvis y hologramas

ON = r"activa|activar|enciende|encender|muestra|muestrame|ensename|abre|pon|ponme|saca|prende|inicia|ver|quiero ver"
OFF = r"desactiva|desactivar|apaga|apagar|oculta|ocultar|quita|quitar|cierra|cerrar|esconde|retira|sal del|sal de"
HOLO = {
    "escaner": "scanner", "escaner de identidad": "scanner", "efectos": "effects", "particulas": "effects",
    "bola de energia": "effects", "dibujo": "draw", "modo dibujo": "draw", "pizarra": "draw", "esfera": "globe",
    "esfera holografica": "globe", "sistema solar": "solar", "planetas": "solar", "tierra": "earth",
    "globo terraqueo": "earth", "globo": "earth", "mundo": "earth", "planeta tierra": "earth", "mapa del mundo": "earth",
    "teclado": "keyboard", "teclado holografico": "keyboard", "notas": "notes", "notas adhesivas": "notes",
    "visualizador": "visualizer", "ecualizador": "visualizer", "visualizador de audio": "visualizer",
    "paneles": "panels", "paneles laterales": "panels", "barra de tareas": "taskbar", "barra": "taskbar",
    "barra de tareas holografica": "taskbar", "mi vida": "life", "vida": "life", "panel de mi vida": "life",
    "mi panel": "life", "panel personal": "life", "mi dashboard": "life",
}
OTHER_MODES = {"subtitulos": ("subtitles_on", "subtitles_off"), "orbe": ("orb_on", "orb_off"),
               "modo guardia": ("guard_on", "guard_off"), "guardia": ("guard_on", "guard_off"),
               "presencia": ("presence_on", "presence_off"), "deteccion de presencia": ("presence_on", "presence_off"),
               "dictado": ("dictation_on", "dictation_off"), "modo dictado": ("dictation_on", "dictation_off"),
               "modo presentacion": ("subtitles_on", "subtitles_off")}


@command(r"(?:" + ON + r")(?: el| la)?(?: modo)? holograma", "Hologramas", "activa el holograma")
def hologram_on(c):
    do("hologram_on")
    return said("Modo holograma activado.")


@command(r"(?:" + OFF + r")(?: el| la)?(?: modo)? holograma", "Hologramas", "apaga el holograma")
def hologram_off(c):
    do("hologram_off")
    return said("Modo holograma desactivado.")


def _mode(c, enabled: bool):
    what = re.sub(r"^(?:el|la|los|las|mis|mi|un|una)\s+", "", c.plain("what"))
    what = re.sub(r"\s+(?:holografic[oa]s?|en pantalla)$", "", what)
    if what in HOLO:
        do("holo", name=HOLO[what], enabled=enabled)
        return said(("Mostrando " if enabled else "Ocultando ") + what + ".")
    if what in OTHER_MODES:
        do(OTHER_MODES[what][0 if enabled else 1])
        return said(("Activé " if enabled else "Desactivé ") + ("el " if not what.endswith("s") else "los ") + what + ".")
    return None


@command(r"(?:" + ON + r") (?P<what>.+)", "Hologramas", "muestra el sistema solar", "activa el escáner",
         "muestra la tierra", "activa los efectos", "muestra el teclado", "activa los subtítulos", "modo dictado")
def mode_on(c):
    return _mode(c, True)


@command(r"(?:" + OFF + r") (?P<what>.+)", "Hologramas", "oculta los paneles laterales", "desactiva la guardia")
def mode_off(c):
    return _mode(c, False)


@command(r"(?:muestra(?:me)? |marca |pon )?(?:el )?clima de (?P<city>.+?) en (?:el globo|la tierra|el mapa)",
         "Hologramas", "muestra el clima de Madrid en el globo")
def city_on_earth(c):
    do("earth_city", city=c.text("city").title())
    return said("Marcado en el globo.")


@command(r"(?:deja de grabar|para(?: de grabar| la grabacion)|deten(?: la)? grabacion|termina(?: la)? grabacion|corta(?: la)? grabacion|stop)",
         "Grabación", "deja de grabar")
def record_stop(c):
    return said(do("record_stop"))


@command(r"(?:empieza a |comienza a |inicia la |inicia |)grab(?:a|ar|acion)(?: la pantalla| el video| un video)?",
         "Grabación", "empieza a grabar")
def record_start(c):
    do("record_start")
    return said("Grabando.")


@command(r"(?:activa el |entra en |pon el |usa el )?modo (?:local|sin claude|sin internet|offline|solo comandos)",
         "Jarvis", "modo local")
def local_on(c):
    do("local_only", enabled=True)
    return said("Modo local: solo usaré comandos, sin Claude.")


@command(r"(?:desactiva el modo local|sal del modo local|modo (?:claude|completo|normal|inteligente)|usa claude|vuelve a usar claude)",
         "Jarvis", "usa Claude")
def local_off(c):
    do("local_only", enabled=False)
    return said("Listo, vuelvo a usar a Claude para lo que no sea un comando.")


@command(r"(?P<what>modo dictado|dictado|voy a dictar|modo guardia|modo presentacion)", "Jarvis", "modo dictado", "modo guardia")
def mode_alone(c):
    return _mode(c, True)


@command(r"(?:activa |inicia |pon |entra en |entra al )?(?:el )?modo (?P<name>\w+(?: \w+)?)", "Rutinas",
         "modo trabajo", "modo juego", "modo descanso")
def routine(c):
    name = c.plain("name")
    if name not in tools.routines.all():
        return None
    result = do("run_routine", name=name)
    if result["needs_approval"]:
        return confirm(result.get("say") or "Esta rutina necesita tu aprobación.", *result["needs_approval"])
    return said(result.get("say") or f"Modo {name} activado.")


# ---------------------------------------------------------------- Música y volumen

@command(r"(?:pon |ajusta |deja |sube |baja )?(?:el )?volumen (?:al|a|en) (?P<n>\S+)(?: por ciento)?", "Música y volumen",
         "volumen al 50")
def volume_to(c):
    level = number(c.plain("n"))
    if level is None:
        return None
    do("set_volume", level=level)
    return said(f"Volumen al {level:.0f}.")


@command(r"(?:que|cual es el|cuanto) volumen(?: tengo| hay| esta)?|a cuanto esta el volumen", "Música y volumen",
         "¿qué volumen hay?")
def volume_now(c):
    return said(f"El volumen está al {tools.get_volume()} por ciento.")


def _step_volume(c, key: str):
    times = 10 if c.plain("much") else 5  # cada pulsación son 2 puntos
    for _ in range(times):
        do("media_key", key=key)
    return said("")


@command(r"(?:sube(?:le)?|aumenta|mas)(?: el| al)? (?:volumen|sonido|audio)(?P<much> mucho| bastante| a tope)?|subele(?P<much2> mucho)?|mas alto|mas volumen",
         "Música y volumen", "sube el volumen", "súbele mucho")
def volume_up(c):
    return _step_volume(c, "volume_up")


@command(r"(?:baja(?:le)?|disminuye|menos)(?: el| al)? (?:volumen|sonido|audio)(?P<much> mucho| bastante)?|bajale(?P<much2> mucho)?|mas bajo|menos volumen",
         "Música y volumen", "baja el volumen")
def volume_down(c):
    return _step_volume(c, "volume_down")


@command(r"(?:silencia(?: todo| el sonido| el audio)?|mutea|silencio|quita(?:le)? el (?:sonido|audio)|activa el sonido|desmutea|pon el sonido)",
         "Música y volumen", "silencio", "activa el sonido")
def mute(c):
    do("media_key", key="mute")
    return said("")


@command(r"(?:pausa(?:r)?(?: la)?(?: musica| cancion| video)?|para la musica|deten la musica|reanuda|continua|play|dale play|sigue la musica|quita la pausa)",
         "Música y volumen", "pausa", "reanuda")
def play_pause(c):
    do("media_key", key="play_pause")
    return said("")


@command(r"(?:siguiente(?: cancion| tema| video)?|salta(?: la| esta)?(?: cancion)?|otra cancion|cambia(?: de)? cancion|pasa la cancion)",
         "Música y volumen", "siguiente canción")
def next_track(c):
    do("media_key", key="next")
    return said("")


@command(r"(?:anterior|cancion anterior|tema anterior|la anterior|regresa la cancion|pon la anterior)", "Música y volumen",
         "canción anterior")
def previous_track(c):
    do("media_key", key="previous")
    return said("")


@command(r"(?:pon|ponme|reproduce|toca|escuchar)(?: musica de| canciones de| la cancion| el tema| a)? (?P<q>.+?) en spotify"
         r"|(?:pon|ponme|reproduce) musica(?: de (?P<q2>.+))?",
         "Música y volumen", "pon música de Queen", "reproduce Bohemian Rhapsody en Spotify", free_text=True)
def spotify(c):
    query = c.text("q", "q2")
    if query:
        tools._start("spotify:search:" + quote(query))
        return said(f"Buscando {query} en Spotify.")
    do("launch", name="spotify")
    return said("Abriendo Spotify.")


# ---------------------------------------------------------------- Búsquedas

@command(r"(?:busca|buscame|pon|ponme|reproduce)(?: en youtube)? (?P<q>.+?) en youtube|(?:busca|buscame|pon|ponme) en youtube (?P<q2>.+)|youtube (?P<q3>.+)",
         "Búsquedas", "busca gatos graciosos en YouTube", "pon en YouTube música lofi", free_text=True)
def youtube(c):
    query = c.text("q", "q2", "q3")
    do("open_url", url="https://www.youtube.com/results?search_query=" + quote(query))
    return said(f"Buscando {query} en YouTube.")


@command(r"(?:busca|buscame|googlea|investiga)(?: en google)? (?P<q>.+?) en google|(?:busca|buscame) en google (?P<q2>.+)|googlea (?P<q3>.+)",
         "Búsquedas", "busca recetas de pollo en Google", free_text=True)
def google(c):
    query = c.text("q", "q2", "q3")
    do("open_url", url="https://www.google.com/search?q=" + quote(query))
    return said(f"Buscando {query}.")


@command(r"(?:busca en wikipedia|wikipedia(?: de)?) (?P<q>.+)|(?:busca )?(?P<q2>.+?) en wikipedia", "Búsquedas",
         "busca en Wikipedia Albert Einstein", free_text=True)
def wikipedia(c):
    query = c.text("q", "q2")
    do("open_url", url="https://es.wikipedia.org/w/index.php?search=" + quote(query))
    return said(f"Buscando {query} en Wikipedia.")


@command(r"(?:como llego a|donde (?:queda|esta)|mapa de|ubicacion de|llevame a|ruta a) (?P<q>.+)", "Búsquedas",
         "¿cómo llego a la plaza principal?", free_text=True)
def maps(c):
    query = c.text("q")
    do("open_url", url="https://www.google.com/maps/search/" + quote(query))
    return said(f"Abriendo el mapa de {query}.")


@command(r"(?:busca|buscame) (?P<q>.+)", "Búsquedas", "busca precios de laptops", free_text=True)
def search(c):
    if not tools.settings.get("local_only") or re.match(r"en (?:la|esta) pagina\b", c.plain("q")):
        return None  # con Claude, "busca" da una respuesta resumida en vez de abrir la página
    query = c.text("q")
    do("open_url", url="https://www.google.com/search?q=" + quote(query))
    return said(f"Buscando {query}.")


@command(r"busca en (?:la |esta )?pagina (?P<q>.+)", "Navegador", "busca en la página precio", free_text=True)
def find_in_page(c):
    do("press_keys", keys="ctrl+f")
    do("type_text", text=c.text("q"))
    return said("")


# ---------------------------------------------------------------- Navegador y pestañas

@command(r"(?:abre |pon )?(?:una )?(?:nueva pestana|pestana nueva)|abre (?:una )?pestana", "Navegador", "nueva pestaña")
def new_tab(c):
    return keys("ctrl+t", "")


@command(r"cierra (?:esta |la )?pestana(?: actual)?", "Navegador", "cierra la pestaña")
def close_tab(c):
    return keys("ctrl+w", "")


@command(r"(?:reabre|recupera|vuelve a abrir|abre de nuevo) (?:la )?(?:ultima )?pestana(?: cerrada)?", "Navegador",
         "reabre la pestaña")
def reopen_tab(c):
    return keys("ctrl+shift+t", "")


@command(r"(?:siguiente pestana|pestana siguiente|cambia de pestana|otra pestana)", "Navegador", "siguiente pestaña")
def next_tab(c):
    return keys("ctrl+tab", "")


@command(r"(?:pestana anterior|la pestana de antes)", "Navegador", "pestaña anterior")
def previous_tab(c):
    return keys("ctrl+shift+tab", "")


@command(r"(?:ve a la |ir a la |cambia a la |abre la )?(?:pestana (?:numero )?(?P<n>\S+)|(?P<last>ultima) pestana)", "Navegador",
         "pestaña 3", "última pestaña")
def tab_number(c):
    if c.plain("last"):
        return keys("ctrl+9", "")
    n = number(c.plain("n") or "")
    if n is None or not 1 <= n <= 8:
        return None
    return keys(f"ctrl+{int(n)}", "")


@command(r"(?:ve |vuelve |)atras|regresa|pagina anterior|retrocede", "Navegador", "atrás")
def back(c):
    return keys("alt+left", "")


@command(r"(?:ve |)adelante|pagina siguiente|avanza", "Navegador", "adelante")
def forward(c):
    return keys("alt+right", "")


@command(r"(?:recarga|actualiza|refresca)(?: la pagina)?", "Navegador", "recarga la página")
def reload(c):
    return keys("f5", "")


@command(r"(?:pantalla completa|(?:sal de|quita) (?:la )?pantalla completa)", "Navegador", "pantalla completa")
def fullscreen(c):
    return keys("f11", "")


@command(r"(?:acerca(?:r)?|zoom(?: mas)?|agranda(?: la pagina| el texto)?|mas grande|aumenta el zoom)", "Navegador",
         "agranda el texto", "zoom")
def zoom_in(c):
    return keys("ctrl+=", "")


@command(r"(?:aleja(?:r)?|menos zoom|achica(?: la pagina| el texto)?|mas pequeno|reduce el zoom)", "Navegador", "achica")
def zoom_out(c):
    return keys("ctrl+-", "")


@command(r"(?:zoom normal|tamano normal|restablece el zoom|quita el zoom)", "Navegador", "zoom normal")
def zoom_reset(c):
    return keys("ctrl+0", "")


@command(r"(?:abre )?(?:una )?nueva ventana(?: del navegador)?", "Navegador", "nueva ventana")
def new_window(c):
    return keys("ctrl+n", "")


@command(r"(?:abre )?(?:una )?(?:ventana de )?(?:incognito|ventana privada|modo incognito)", "Navegador", "modo incógnito")
def incognito(c):
    return keys("ctrl+shift+n", "")


@command(r"(?:abre el |muestra el )?historial(?: del navegador)?", "Navegador", "historial")
def history(c):
    return keys("ctrl+h", "")


@command(r"(?:abre las |muestra las )?descargas del navegador", "Navegador", "descargas del navegador")
def browser_downloads(c):
    return keys("ctrl+j", "")


@command(r"(?:guarda en |agrega a |anade a )?(?:favoritos|marcadores)|marca(?: esta)? pagina", "Navegador", "guarda en favoritos")
def bookmark(c):
    return keys("ctrl+d", "")


@command(r"(?:ve a|ir a|abre la pagina|abre|entra a|entra en) (?P<site>[\w-]+(?:\.[\w-]+)+(?:/\S*)?)", "Navegador",
         "ve a wikipedia.org")
def go_to_site(c):
    site = re.sub(r"\s+", "", c.plain("site"))
    do("open_url", url="https://" + site)
    return said(f"Abriendo {site}.")


# ---------------------------------------------------------------- Scroll

def _scroll(c, steps):
    much = c.plain("much") or ""
    steps = steps * (3 if "mucho" in much else 0.4 if "poco" in much else 1)
    from . import screen

    screen.scroll(round(steps))
    return said("")


@command(r"(?:baja|bajar|scroll(?: hacia)? abajo|desplazate(?: hacia)? abajo|mas abajo|baja la pagina|sigue bajando)(?P<much> mucho| un poco)?",
         "Navegador", "baja", "baja mucho")
def scroll_down(c):
    return _scroll(c, -5)


@command(r"(?:sube|subir|scroll(?: hacia)? arriba|desplazate(?: hacia)? arriba|mas arriba|sube la pagina)(?P<much> mucho| un poco)?",
         "Navegador", "sube", "sube un poco")
def scroll_up(c):
    return _scroll(c, 5)


@command(r"(?:ve |ir |vete |)al (?:principio|inicio)(?: de la pagina)?|arriba del todo", "Navegador", "ve al principio")
def to_top(c):
    return keys("home", "")


@command(r"(?:ve |ir |vete |)al final(?: de la pagina)?|abajo del todo", "Navegador", "ve al final")
def to_bottom(c):
    return keys("end", "")


# ---------------------------------------------------------------- Ventanas y escritorio

@command(r"minimiza (?:todo|todas las ventanas)|muestra el escritorio|ve al escritorio|limpia la pantalla", "Ventanas",
         "minimiza todo", "muestra el escritorio")
def minimize_all(c):
    do("window_action", action="minimize_all")
    return said("")


@command(r"minimiza(?: la ventana| esta ventana| esto)?", "Ventanas", "minimiza")
def minimize(c):
    do("window_action", action="minimize")
    return said("")


@command(r"maximiza(?: la ventana| esta ventana| esto)?|agranda la ventana", "Ventanas", "maximiza")
def maximize(c):
    do("window_action", action="maximize")
    return said("")


@command(r"restaura(?: la ventana| esta ventana)?", "Ventanas", "restaura")
def restore(c):
    do("window_action", action="restore")
    return said("")


@command(r"cierra (?:esta |la )?ventana|cierra esto", "Ventanas", "cierra esta ventana")
def close_window(c):
    hwnd = winctl.user32.GetForegroundWindow()
    if not hwnd or not winctl.Windows(exclude=set())._is_app_window(hwnd):
        raise CommandError("No hay una ventana activa que cerrar.")
    winctl.close_window(hwnd)
    return said("")


@command(r"(?:cambia de ventana|siguiente ventana|otra ventana|alterna(?: ventana)?)", "Ventanas", "cambia de ventana")
def switch_window(c):
    return keys("alt+tab", "")


@command(r"(?:pon |manda |mueve )?(?:la |esta )?ventana a la (?P<side>izquierda|derecha)|(?P<side2>izquierda|derecha)", "Ventanas",
         "ventana a la izquierda")
def snap(c):
    side = c.plain("side", "side2")
    return keys("win+left" if side == "izquierda" else "win+right", "")


@command(r"(?:vista de tareas|muestra(?:me)? todas las ventanas|todas las ventanas)", "Ventanas", "vista de tareas")
def task_view(c):
    return keys("win+tab", "")


@command(r"(?:nuevo escritorio|crea un escritorio(?: virtual)?|escritorio nuevo)", "Ventanas", "nuevo escritorio")
def new_desktop(c):
    return keys("win+ctrl+d", "")


@command(r"(?:siguiente escritorio|escritorio de la derecha)", "Ventanas", "siguiente escritorio")
def next_desktop(c):
    return keys("win+ctrl+right", "")


@command(r"(?:escritorio anterior|escritorio de la izquierda)", "Ventanas", "escritorio anterior")
def previous_desktop(c):
    return keys("win+ctrl+left", "")


@command(r"(?:abre |muestra )?(?:el )?menu (?:de )?inicio|tecla windows", "Ventanas", "menú inicio")
def start_menu(c):
    return keys("win", "")


@command(r"(?:abre |muestra )?(?:el )?(?:centro de notificaciones|panel de notificaciones)", "Ventanas", "centro de notificaciones")
def notifications(c):
    return keys("win+n", "")


@command(r"(?:abre |muestra )?(?:el )?(?:historial del )?portapapeles", "Escribir y teclado", "portapapeles")
def clipboard(c):
    return keys("win+v", "")


@command(r"(?:abre |muestra )?(?:el panel de |los )?emojis?", "Escribir y teclado", "emojis")
def emojis(c):
    return keys("win+.", "")


@command(r"(?:haz|toma|saca)(?: una)? captura(?: de pantalla)?|captura(?: la| de)? pantalla|screenshot", "Ventanas",
         "haz una captura de pantalla")
def screenshot(c):
    do("take_screenshot")
    return said("Captura guardada en Imágenes, carpeta Jarvis.")


@command(r"(?:haz un |)recorte(?: de pantalla)?|recorta(?: la pantalla)?", "Ventanas", "recorte de pantalla")
def snip(c):
    return keys("win+shift+s", "")


@command(r"(?:cambia|cambiate|ve|vete|pasa|salta|regresa|vuelve|muestrame) (?:a|al|a la|a el) (?P<name>.+)", "Ventanas",
         "cambia a Chrome", "ve a Spotify")
def focus(c):
    name = c.text("name")
    try:
        return said("") if do("focus_window", name=name) else None
    except CommandError:
        if tools.plain(name) in tools.LAUNCH:
            do("launch", name=name)
            return said(f"No estaba abierto; abriendo {name}.")
        raise


# ---------------------------------------------------------------- Apps

@command(r"(?:abre|abrir|abreme|inicia|ejecuta|lanza|arranca|entra a|entra en)(?: el| la| mi| mis| los| las)? (?P<name>.+)",
         "Apps", "abre Chrome", "abre Spotify", "abre descargas", "abre YouTube", "abre OBS")
def open_(c):
    name = c.text("name")
    return said(do("launch", name=name) + ".")


@command(r"(?:cierra|cerrar|cierrame|sal de|salte de)(?: el| la| los| las)? (?P<name>.+)", "Apps", "cierra Spotify",
         "cierra el bloc de notas")
def close(c):
    return said(do("close_app", name=c.text("name")) + ".")


# ---------------------------------------------------------------- Teclado y mouse

@command(r"copia(?P<all> todo)?(?: eso| esto| el texto)?", "Escribir y teclado", "copia", "copia todo")
def copy(c):
    if c.plain("all"):
        do("press_keys", keys="ctrl+a")
    return keys("ctrl+c", "")


@command(r"pega(?: eso| esto| aqui| el texto)?", "Escribir y teclado", "pega")
def paste(c):
    return keys("ctrl+v", "")


@command(r"corta(?: eso| esto)?", "Escribir y teclado", "corta")
def cut(c):
    return keys("ctrl+x", "")


@command(r"(?:deshaz|deshacer|deshaz eso|control z)", "Escribir y teclado", "deshaz")
def undo(c):
    return keys("ctrl+z", "")


@command(r"(?:rehaz|rehacer|control y)", "Escribir y teclado", "rehaz")
def redo(c):
    return keys("ctrl+y", "")


@command(r"selecciona todo", "Escribir y teclado", "selecciona todo")
def select_all(c):
    return keys("ctrl+a", "")


@command(r"guarda(?: el archivo| esto| los cambios| el documento)?", "Escribir y teclado", "guarda")
def save(c):
    return keys("ctrl+s", "")


@command(r"imprime(?: esto| la pagina)?", "Escribir y teclado", "imprime")
def print_(c):
    return keys("ctrl+p", "")


@command(r"(?:enter|intro|dale enter|presiona enter|envia(?:lo)?|acepta(?:r)?|confirma)", "Escribir y teclado", "enter", "envía")
def enter(c):
    return keys("enter", "")


@command(r"(?:escape|presiona escape|sal|salir)", "Escribir y teclado", "escape")
def escape(c):
    return keys("esc", "")


@command(r"(?:tabulador|tab)", "Escribir y teclado", "tabulador")
def tab(c):
    return keys("tab", "")


@command(r"(?:espacio|barra espaciadora)", "Escribir y teclado", "espacio")
def space(c):
    return keys("space", "")


@command(r"borra (?:la ultima palabra|la palabra|una palabra)", "Escribir y teclado", "borra la última palabra")
def delete_word(c):
    return keys("ctrl+backspace", "")


@command(r"borra todo(?: el texto)?", "Escribir y teclado", "borra todo el texto")
def delete_all_text(c):
    do("press_keys", keys="ctrl+a")
    return keys("backspace", "")


@command(r"borra(?: eso| una letra)?|borrar|retroceso", "Escribir y teclado", "borra")
def backspace(c):
    return keys("backspace", "")


SPOKEN_KEYS = {
    "control": "ctrl", "ctrl": "ctrl", "alt": "alt", "shift": "shift", "mayusculas": "shift", "mayuscula": "shift",
    "windows": "win", "win": "win", "enter": "enter", "intro": "enter", "escape": "esc", "esc": "esc",
    "tabulador": "tab", "tab": "tab", "espacio": "space", "retroceso": "backspace", "borrar": "backspace",
    "suprimir": "delete", "supr": "delete", "inicio": "home", "fin": "end", "arriba": "up", "abajo": "down",
    "izquierda": "left", "derecha": "right", "flecha": None, "y": None, "mas": None, "la": None, "tecla": None,
    "re pag": "pageup", "av pag": "pagedown",
}


@command(r"(?:presiona|pulsa|aprieta|oprime|teclea) (?P<keys>.+)", "Escribir y teclado", "presiona control z", "pulsa alt f4")
def press(c):
    parts = []
    for word in c.plain("keys").replace("+", " ").split():
        if word in SPOKEN_KEYS:
            if SPOKEN_KEYS[word]:
                parts.append(SPOKEN_KEYS[word])
        elif re.fullmatch(r"f\d{1,2}|[a-z0-9]", word):
            parts.append(word)
        else:
            return None
    if not parts:
        return None
    combo = "+".join(parts)
    if tools.needs_confirmation("press_keys", {"keys": combo}):
        return confirm("Suprimir puede borrar archivos. ¿Lo pulso?", {"tool": "press_keys", "args": {"keys": combo}})
    return keys(combo, "")


def _cursor():
    return winctl.Cursor(), winctl.cursor_position()


@command(r"(?:haz |da )?doble clic", "Mouse", "doble clic")
def double_click(c):
    cursor, (x, y) = _cursor()
    cursor.click(x, y)
    cursor.click(x, y)
    return said("")


@command(r"(?:haz |da )?clic derecho", "Mouse", "clic derecho")
def right_click(c):
    cursor, (x, y) = _cursor()
    cursor.right_click(x, y)
    return said("")


@command(r"(?:haz |da )?(?:clic|click)(?: aqui)?", "Mouse", "haz clic")
def click(c):
    cursor, (x, y) = _cursor()
    cursor.click(x, y)
    return said("")


@command(r"mueve el (?:mouse|raton|cursor) (?:a la |hacia |hacia la |para )?(?P<dir>arriba|abajo|izquierda|derecha)(?P<much> mucho| un poco)?",
         "Mouse", "mueve el mouse a la derecha")
def move_mouse(c):
    distance = {" mucho": 600, " un poco": 80}.get(c.plain("much") and " " + c.plain("much"), 250)
    dx, dy = {"arriba": (0, -1), "abajo": (0, 1), "izquierda": (-1, 0), "derecha": (1, 0)}[c.plain("dir")]
    cursor, (x, y) = _cursor()
    cursor.move(x + dx * distance, y + dy * distance)
    return said("")


@command(r"(?:centra|pon) el (?:mouse|raton|cursor)(?: en el centro)?", "Mouse", "centra el mouse")
def center_mouse(c):
    left, top, width, height = winctl.work_area()
    winctl.Cursor().move(left + width / 2, top + height / 2)
    return said("")


# ---------------------------------------------------------------- Sistema

@command(r"bloquea(?: la (?:pc|computadora|compu|pantalla|sesion)| el equipo)?", "Sistema", "bloquea la PC")
def lock(c):
    do("lock_pc")
    return said("")


@command(r"apaga(?: la| el)? (?:pc|computadora|compu|ordenador|equipo|sistema)", "Sistema", "apaga la PC")
def shutdown(c):
    return confirm("¿Apago la PC? Necesito tu aprobación.", {"tool": "shutdown_pc", "args": {}})


@command(r"reinicia(?: la| el)? (?:pc|computadora|compu|ordenador|equipo|sistema)", "Sistema", "reinicia la PC")
def restart(c):
    return confirm("¿Reinicio la PC? Necesito tu aprobación.", {"tool": "restart_pc", "args": {}})


@command(r"suspende(?: la (?:pc|computadora))?|modo suspension|pon(?: la pc)? a dormir", "Sistema", "suspende la PC")
def suspend(c):
    return confirm("¿Suspendo la PC?", {"tool": "run_powershell",
                                        "args": {"command": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"}})


# ---------------------------------------------------------------- Mi vida
# Se cargan al final pero se revisan primero: "abre mis tareas" no debe buscar "mis tareas" en el menú Inicio.
_general = len(COMMANDS)
from . import life_commands  # noqa: E402,F401

COMMANDS[:] = COMMANDS[_general:] + COMMANDS[:_general]
