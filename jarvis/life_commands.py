"""Comandos de voz de «Mi vida»: tareas, cuerpo, comidas, agua, sueño, ejercicio, dinero, ánimo,
hábitos, rutina, clases, calendario, feriados y mapas de ideas. Se registran en commands.py."""
import re
from datetime import date, datetime, timedelta

from .commands import CommandError, command, number, said
from .life import DAYS, MOODS, LifeError, life
from .textutil import align

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]
WEEKDAYS = [align(day) for day in DAYS]  # sin tildes: "miercoles", "sabado"


def act(action: str, **args) -> dict:
    try:
        return said(life.apply(action, args)["say"])
    except LifeError as error:
        raise CommandError(str(error)) from error


def parse_day(text: str, today: date | None = None) -> date | None:
    """'hoy', 'mañana', 'pasado mañana', 'el viernes', 'el 20 de noviembre', 'el 20' -> fecha."""
    today = today or date.today()
    text = re.sub(r"^(?:el|este|para el|para)\s+", "", align(text).strip())
    if text in ("hoy", ""):
        return today
    if text == "manana":
        return today + timedelta(days=1)
    if text == "pasado manana":
        return today + timedelta(days=2)
    weekday = text.replace("proximo ", "").replace(" que viene", "")
    if weekday in WEEKDAYS:
        ahead = (WEEKDAYS.index(weekday) - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    match = re.fullmatch(r"(\S+)(?: de (\w+))?(?: de(?:l)? (\d{4}))?", text)
    if match:
        day = number(match.group(1))
        if day is None or day != int(day):
            return None
        month = MONTHS.index(match.group(2)) + 1 if match.group(2) in MONTHS else None
        year = int(match.group(3)) if match.group(3) else today.year
        if month is None:
            if match.group(2):
                return None
            month = today.month if day >= today.day else today.month % 12 + 1
            if month < today.month:
                year += 1
        try:
            found = date(year, month, int(day))
        except ValueError:
            return None
        if found < today and not match.group(3):
            found = found.replace(year=found.year + 1)
        return found
    return None


def hhmm(text: str) -> str | None:
    """'8', '8:30', '8 y media', '2 de la tarde', '14' -> 'HH:MM'."""
    text = re.sub(r"^(?:a\s+)?(?:las|la)\s+", "", align(text).strip())
    afternoon = re.search(r"\s+de la (tarde|noche)$", text)
    text = re.sub(r"\s+de la (manana|tarde|noche)$", "", text)
    match = re.fullmatch(r"(\S+?)(?::(\d{2}))?(?:\s+y\s+(media|cuarto|\S+))?", text)
    if not match or number(match.group(1)) is None:
        return None
    hour = int(number(match.group(1)))
    minute = int(match.group(2) or {"media": 30, "cuarto": 15}.get(match.group(3) or "", number(match.group(3) or "0") or 0))
    if afternoon and hour < 12:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


TIME = r"(?:\d{1,2}(?::\d\d)?|\w+)(?: y (?:media|cuarto|\d+))?(?: de la (?:manana|tarde|noche))?"
DATE = r"(?:hoy|manana|pasado manana|el \w+(?: de \w+)?(?: del? \d{4})?|este \w+|para el \w+(?: de \w+)?)"


# ---------------------------------------------------------------- Tareas

@command(r"(?:agrega|anade|apunta|crea|nueva|pon)(?: una)?(?: nueva)? tarea(?:\s*:)? (?P<text>.+?)(?: (?P<when>para (?:hoy|manana|pasado manana|el \w+(?: de \w+)?)))?(?P<urgent> (?:es )?(?:urgente|importante))?"
         r"|tengo que (?P<text2>.+?)(?: (?P<when2>para (?:hoy|manana|pasado manana|el \w+(?: de \w+)?)))?",
         "Mi vida: tareas", "agrega tarea pagar la luz para mañana", "tengo que estudiar cálculo", free_text=True)
def task_add(c):
    when = c.plain("when", "when2")
    due = parse_day(when.replace("para ", "", 1)) if when else None
    return act("task_add", text=c.text("text", "text2"), due=due.isoformat() if due else None,
               priority="alta" if c.plain("urgent") else "normal")


@command(r"(?:que tareas tengo|mis tareas|tareas pendientes|que tengo pendiente|que me falta hacer|lista de tareas)",
         "Mi vida: tareas", "¿qué tareas tengo?")
def task_list(c):
    tasks = life.summary()["tasks"]
    if not tasks:
        return said("No tienes tareas pendientes. ¡Bien hecho!")
    names = "; ".join(t["text"] + (" (urgente)" if t["priority"] == "alta" else "") for t in tasks[:6])
    return said(f"Tienes {len(tasks)} pendiente{'s' if len(tasks) > 1 else ''}: {names}.")


@command(r"(?:ya )?(?:hice|termine|complete|acabe|cumpli|marca(?: como hecha)?|lista)(?: la tarea| el habito| mi| la| el)? (?P<what>.+?)(?: como hecha)?",
         "Mi vida: tareas", "terminé la tarea de cálculo", "hice ejercicio de lectura")
def done(c):
    """'Hice X': primero un hábito, luego algo de la rutina y si no, una tarea."""
    what = c.plain("what")
    data = life.load()
    for action, items, field, key in (("habit_check", data["habits"], "name", "habit"),
                                      ("routine_check", data["routine"], "text", "item"),
                                      ("task_done", [t for t in data["tasks"] if not t["done"]], "text", "task")):
        if any(what in align(i[field]) or align(i[field]) in what for i in items):
            match = next(i for i in items if what in align(i[field]) or align(i[field]) in what)
            return act(action, **{key: match["id"]})
    return None


# ---------------------------------------------------------------- Cuerpo

@command(r"(?:hoy )?(?:peso|pese|mi peso es|estoy pesando)(?: de)? (?P<kg>[\d.,]+)(?: kilos| kg| kilogramos)?", "Mi vida: cuerpo",
         "peso 72 kilos", "hoy peso 71.5")
def weight(c):
    return act("weight", kg=number(c.plain("kg")))


@command(r"(?:mido|mi estatura es(?: de)?|mi altura es(?: de)?)(?: un)? (?P<h>[\d.,]+)(?: metros| centimetros| cm| m)?(?: con (?P<cm>\d+))?",
         "Mi vida: cuerpo", "mido 1.75", "mi estatura es 175")
def height(c):
    value = number(c.plain("h"))
    if c.plain("cm"):
        value = value * 100 + float(c.plain("cm"))  # "uno setenta" -> "1 con 70"
    return act("height", cm=value)


@command(r"tengo (?P<age>\d+) anos", "Mi vida: cuerpo", "tengo 23 años")
def age(c):
    return act("profile", age=int(c.plain("age")))


@command(r"soy (?P<sex>hombre|mujer|varon)", "Mi vida: cuerpo", "soy hombre")
def sex(c):
    return act("profile", sex="hombre" if c.plain("sex") in ("hombre", "varon") else "mujer")


@command(r"(?:mi )?meta (?:de peso )?es (?:llegar a |pesar )?(?P<kg>[\d.,]+)(?: kilos| kg)?", "Mi vida: cuerpo", "mi meta es llegar a 75 kilos")
def target(c):
    return act("profile", target_kg=number(c.plain("kg")))


# ---------------------------------------------------------------- Comidas, agua, sueño y ejercicio

@command(r"(?:tome|bebi|me tome)(?: (?P<n>\S+))? (?:vasos?|botellas?) de agua|(?:un |otro )?vaso de agua|agua mas (?P<n2>\S+)",
         "Mi vida: salud", "tomé 2 vasos de agua", "otro vaso de agua")
def water(c):
    n = number(c.plain("n", "n2") or "1")
    return act("water", glasses=int(n or 1))


MEAL_VERBS = {"desayune": "desayuno", "almorce": "almuerzo", "cene": "cena", "merende": "merienda",
              "comi": None, "me comi": None, "tome de desayuno": "desayuno", "de desayuno": "desayuno",
              "de almuerzo": "almuerzo", "de cena": "cena"}


@command(r"(?:hoy |ya )?(?P<verb>desayune|almorce|cene|merende|me comi|comi|tome de desayuno)(?:\s*:)? (?P<food>.+)",
         "Mi vida: salud", "almorcé un silpancho y una coca", "desayuné 3 huevos y un café con leche", free_text=True)
def meal(c):
    return act("meal", text=c.text("food"), meal=MEAL_VERBS[c.plain("verb")])


@command(r"(?:cuantas calorias|cuanta proteina|cuanto (?:he )?comido)(?: llevo| he comido| comi)?(?: hoy)?", "Mi vida: salud",
         "¿cuántas calorías llevo?")
def food_today(c):
    food = life.summary()["food"]
    goals = food["goals"]
    return said(f"Hoy llevas {food['kcal']} de {goals['kcal']:.0f} calorías y {food['protein']:.0f} de "
                f"{goals['protein']} gramos de proteína.")


@command(r"dormi (?P<h>\S+)(?: horas?)?(?P<half> y media)?", "Mi vida: salud", "dormí 7 horas y media")
def sleep(c):
    hours = number(c.plain("h"))
    if hours is None:
        return None
    return act("sleep", hours=hours + (0.5 if c.plain("half") else 0))


@command(r"(?:hice|entrene|corri|nade)(?: (?P<min>\S+) minutos(?: de)?)? (?P<kind>.+?)(?: (?P<min2>\S+) minutos)?"
         r"|fui al (?P<gym>gimnasio|gym)(?: (?P<min3>\S+) minutos)?",
         "Mi vida: salud", "hice 45 minutos de pesas", "fui al gimnasio")
def exercise(c):
    minutes = number(c.plain("min", "min2", "min3") or ("60" if c.plain("gym") else ""))
    if minutes is None:
        return None  # "hice la tarea": no es ejercicio
    return act("exercise", kind=c.text("kind") or "gimnasio", minutes=minutes)


# ---------------------------------------------------------------- Dinero

@command(r"gaste (?P<n>[\d.,]+)(?: bolivianos| bs| pesos)?(?: en (?P<what>.+))?", "Mi vida: dinero",
         "gasté 25 bolivianos en comida", free_text=True)
def spend(c):
    return act("money", amount=number(c.plain("n")), category=c.text("what") or "otros")


@command(r"(?:me pagaron|recibi|cobre|gane) (?P<n>[\d.,]+)(?: bolivianos| bs)?(?: (?:de|por) (?P<what>.+))?", "Mi vida: dinero",
         "me pagaron 500 bolivianos", free_text=True)
def income(c):
    return act("money", amount=number(c.plain("n")), category="ingreso", note=c.text("what") or "", kind="ingreso")


@command(r"(?:ahorre|guarde) (?P<n>[\d.,]+)(?: bolivianos| bs)?", "Mi vida: dinero", "ahorré 100 bolivianos")
def save_money(c):
    return act("money", amount=number(c.plain("n")), category="ahorro", kind="ahorro")


@command(r"(?:cuanto (?:he )?gaste|cuanto gaste|mis gastos)(?: este mes| en el mes)?", "Mi vida: dinero", "¿cuánto gasté este mes?")
def spent(c):
    money = life.summary()["money"]
    top = ", ".join(f"{k} {v:g}" for k, v in list(money["categories"].items())[:3])
    return said(f"Este mes gastaste {money['spent']:g} bolivianos" + (f": {top}." if top else ".") +
                f" Llevas {money['saved']:g} ahorrados.")


# ---------------------------------------------------------------- Ánimo, hábitos y rutina

FEELINGS = {"muy mal": 1, "fatal": 1, "terrible": 1, "mal": 2, "triste": 2, "cansado": 2, "cansada": 2,
            "estresado": 2, "estresada": 2, "normal": 3, "mas o menos": 3, "bien": 4, "contento": 4,
            "contenta": 4, "feliz": 5, "muy bien": 5, "genial": 5, "excelente": 5}


@command(r"(?:hoy )?me siento (?P<feel>muy mal|fatal|terrible|mal|triste|cansad[oa]|estresad[oa]|normal|mas o menos|bien|content[oa]|feliz|muy bien|genial|excelente)",
         "Mi vida: ánimo", "me siento bien", "hoy me siento cansado")
def mood(c):
    return act("mood", score=FEELINGS[c.plain("feel")], note=c.text("feel"))


@command(r"(?:agrega|crea|nuevo)(?: el| un)? habito(?:\s*:)? (?P<name>.+)", "Mi vida: hábitos", "agrega el hábito leer 20 minutos")
def habit_add(c):
    return act("habit_add", name=c.text("name"))


@command(r"(?:agrega|anade|pon) (?:a|en) mi rutina(?:\s*:)? (?P<text>.+?)(?: a las (?P<time>" + TIME + r"))?",
         "Mi vida: hábitos", "agrega a mi rutina tender la cama a las 7")
def routine_add(c):
    time = hhmm(c.plain("time")) if c.plain("time") else None
    return act("routine_add", text=c.text("text"), time=time)


# ---------------------------------------------------------------- Clases, calendario y feriados

def _class_line(cls) -> str:
    where = ", ".join(x for x in (f"aula {cls['room']}" if cls["room"] else "", cls["place"]) if x)
    return (f"{cls['subject']} de {cls['start']} a {cls['end']}" + (f" en {where}" if where else "") +
            (f", con {cls['teacher']}" if cls["teacher"] else ""))


@command(r"(?:que clase tengo|cual es mi clase|donde es mi clase|a que clase voy)(?: (?P<when>ahora|hoy|manana|el \w+))?|mi proxima clase|que clases tengo(?: (?P<when2>hoy|manana|el \w+))?",
         "Mi vida: clases", "¿qué clase tengo ahora?", "¿qué clases tengo mañana?")
def classes(c):
    when = c.plain("when", "when2") or "ahora"
    summary = life.summary()
    if when == "ahora":
        current, upcoming = summary["classes"]["now"], summary["classes"]["next"]
        if current:
            return said("Ahora tienes " + _class_line(current) + ".")
        if upcoming:
            return said("Tu próxima clase es " + _class_line(upcoming) + ".")
        return said("No tienes más clases hoy.")
    day = parse_day(when.replace("el ", ""))
    if day is None:
        return None
    items = [cls for cls in summary["classes"]["week"] if cls["day"] == day.weekday()]
    if not items:
        return said(f"No tienes clases el {DAYS[day.weekday()]}.")
    return said(f"El {DAYS[day.weekday()]} tienes: " + "; ".join(_class_line(cls) for cls in items) + ".")


@command(r"(?:agrega|anade|tengo)(?: una)? clase de (?P<subject>.+?) (?:el|los) (?P<day>lunes|martes|miercoles|jueves|viernes|sabado|domingo)s? de (?P<start>" + TIME + r") a (?P<end>" + TIME + r")"
         r"(?: en (?:el )?aula (?P<room>\S+))?(?: en (?:el |la )?(?P<place>(?!aula).+?))?(?: con (?:el |la )?(?:ingeniero|ingeniera|ing|docente|profesor|profesora|licenciado|licenciada|lic|doctor|doctora|dr|dra)?\.? ?(?P<teacher>.+))?",
         "Mi vida: clases", "agrega clase de Cálculo el lunes de 8 a 9 y media en el aula A12 con el ingeniero Rojas",
         free_text=True)
def class_add(c):
    start, end = hhmm(c.plain("start")), hhmm(c.plain("end"))
    if not start or not end:
        return None
    return act("class_add", day=c.plain("day"), start=start, end=end, subject=c.text("subject").title(),
               room=(c.text("room") or "").upper(), place=c.text("place") or "", teacher=(c.text("teacher") or "").title())


@command(r"(?:agrega|anade|tengo|pon)(?: un| una| el| la)? (?:evento|cita|reunion|examen|cumpleanos|fiesta|entrega)(?: de| del| con)?(?P<title>.+?) (?P<when>" + DATE + r")(?: a las (?P<time>" + TIME + r"))?(?: en (?P<place>.+))?",
         "Mi vida: calendario", "tengo examen de física el 20 de noviembre a las 10", "agrega cumpleaños de mamá el 3 de marzo",
         free_text=True)
def event_add(c):
    kind = re.search(r"evento|cita|reunion|examen|cumpleanos|fiesta|entrega", c.aligned).group(0)
    day = parse_day(c.plain("when"))
    if day is None:
        return None
    title = c.text("title").strip()
    title = {"cumpleanos": "Cumpleaños", "reunion": "Reunión"}.get(kind, kind.capitalize()) + " " + title \
        if kind != "evento" else title
    time = hhmm(c.plain("time")) if c.plain("time") else None
    return act("event_add", title=title.strip(), day=day.isoformat(), time=time, place=c.text("place") or "")


@command(r"(?:que tengo|mi agenda|que eventos tengo|que hay en mi calendario)(?: (?P<when>hoy|manana|esta semana|este mes))?",
         "Mi vida: calendario", "¿qué tengo esta semana?")
def agenda(c):
    when = c.plain("when") or "esta semana"
    today = date.today()
    end = {"hoy": today, "manana": today + timedelta(days=1), "esta semana": today + timedelta(days=7),
           "este mes": today + timedelta(days=31)}[when]
    start = today + timedelta(days=1) if when == "manana" else today
    summary = life.summary()
    events = [e for e in summary["events"] if start.isoformat() <= e["date"] <= end.isoformat()]
    holidays = [h for h in summary["holidays"] if start.isoformat() <= h["date"] <= end.isoformat()]
    if not events and not holidays:
        return said(f"No tienes nada en tu calendario para {when}.")
    parts = [f"{e['title']} el {datetime.fromisoformat(e['date']).day}" + (f" a las {e['time']}" if e["time"] else "")
             for e in events] + [f"feriado de {h['name']} el {datetime.fromisoformat(h['date']).day}" for h in holidays]
    return said(f"Para {when}: " + "; ".join(parts) + ".")


@command(r"(?:cual es el |cuando es el )?proximo feriado|que feriados hay(?: este mes)?|feriados", "Mi vida: calendario",
         "¿cuál es el próximo feriado?")
def next_holiday(c):
    upcoming = life.summary()["holidays"]
    first = upcoming[0]
    day = datetime.fromisoformat(first["date"]).date()
    left = (day - date.today()).days
    return said(f"El próximo feriado es {first['name']}, el {DAYS[day.weekday()]} {day.day} de {MONTHS[day.month - 1]}"
                + (", es hoy." if left == 0 else f", en {left} días."))


# ---------------------------------------------------------------- Ver el panel

PAGES = {"mi dia": "today", "mi resumen": "today", "mis tareas": "tasks", "mis pendientes": "tasks",
         "mi peso": "body", "mi cuerpo": "body", "mis comidas": "food", "mi alimentacion": "food",
         "mis habitos": "habits", "mi rutina": "habits", "mis gastos": "money", "mi dinero": "money",
         "mis finanzas": "money", "mis clases": "classes", "mi horario": "classes", "mi calendario": "calendar",
         "mi agenda": "calendar", "mis ideas": "ideas", "mis mapas": "ideas", "mis diagramas": "ideas"}


@command(r"(?:muestra(?:me)?|abre|ensename|ver|quiero ver|pon) (?P<page>" + "|".join(PAGES) + ")",
         "Mi vida", "muestra mis clases", "muestra mi día", "abre mis tareas", "muestra mis gastos")
def show_page(c):
    from .commands import do

    do("life_show", page=PAGES[c.plain("page")])
    return said("")


@command(r"(?:como va|como voy con) mi dia|como voy hoy|resumen de mi (?:dia|vida)|mi resumen del dia", "Mi vida",
         "¿cómo va mi día?")
def my_day(c):
    s = life.summary()
    parts = []
    if s["classes"]["now"]:
        parts.append(f"ahora tienes {s['classes']['now']['subject']}")
    elif s["classes"]["next"]:
        parts.append(f"tu próxima clase es {s['classes']['next']['subject']} a las {s['classes']['next']['start']}")
    if s["tasks"]:
        parts.append(f"{len(s['tasks'])} tareas pendientes, la primera: {s['tasks'][0]['text']}")
    food, goals = s["food"], s["food"]["goals"]
    parts.append(f"{food['kcal']} de {goals['kcal']:.0f} calorías y {food['protein']:.0f} de {goals['protein']} gramos de proteína")
    parts.append(f"{s['water']['today']} de {s['water']['goal']} vasos de agua")
    pending = [h["name"] for h in s["habits"] if not h["done"]]
    if pending:
        parts.append("te falta: " + ", ".join(pending[:3]))
    today_events = [e["title"] for e in s["events"] if e["date"] == s["today"]]
    if today_events:
        parts.append("hoy tienes " + ", ".join(today_events))
    return said("Hoy " + "; ".join(parts) + ".")


# ---------------------------------------------------------------- Mapas de ideas y diagramas de flujo

@command(r"crea(?: un| una)? (?P<kind>mapa de ideas|mapa mental|diagrama de flujo|diagrama|lluvia de ideas)(?: llamado| sobre| de| para)? (?P<name>.+)",
         "Mi vida: ideas", "crea un mapa de ideas sobre mi negocio", "crea un diagrama de flujo de mi proyecto")
def map_add(c):
    kind = "flujo" if "diagrama" in c.plain("kind") else "ideas"
    return act("map_add", name=c.text("name"), kind=kind)


@command(r"(?:en el (?:mapa|diagrama) (?P<map>.+?) )?(?:agrega|anade|pon)(?: la idea| el nodo| el paso| la decision)? (?P<text>.+?)"
         r"(?: (?:al|en el) (?:mapa|diagrama) (?P<map2>.+?))?(?: (?:conectad[oa] a|despues de|debajo de|desde|unid[oa] a) (?P<parent>.+))?",
         "Mi vida: ideas", "agrega la idea vender en línea al mapa negocio conectada a ventas")
def node_add(c):
    map_name = c.plain("map", "map2")
    if not map_name:
        return None  # sin decir el mapa, no es para un mapa (Claude o otro comando)
    is_decision = "decision" in c.aligned
    try:
        return act("node_add", map_=map_name, text=c.text("text"), parent=c.plain("parent"),
                   shape="diamond" if is_decision else "box")
    except CommandError:
        return None
