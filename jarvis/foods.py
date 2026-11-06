"""Tabla local de alimentos: calorías y proteínas por porción habitual. Sin internet y sin Claude.

Valores aproximados de una porción típica (lo que la gente suele comer de una vez).
"""
import re

from .textutil import align, number

# nombre (sin tildes): (porción, kcal, proteína en gramos)
FOODS = {
    # Comida boliviana
    "salteña": ("1 salteña", 350, 12), "saltena": ("1 salteña", 350, 12),
    "tucumana": ("1 tucumana", 300, 9), "empanada": ("1 empanada", 280, 8),
    "empanada de queso": ("1 empanada", 300, 9), "cuñape": ("1 cuñapé", 130, 4), "cunape": ("1 cuñapé", 130, 4),
    "silpancho": ("1 plato", 900, 40), "pique macho": ("1 plato", 1200, 55), "pique": ("1 plato", 1200, 55),
    "majadito": ("1 plato", 700, 25), "chicharron": ("1 plato", 900, 45), "sajta": ("1 plato", 650, 35),
    "sajta de pollo": ("1 plato", 650, 35), "anticucho": ("1 porción", 400, 30), "anticuchos": ("1 porción", 400, 30),
    "sopa de mani": ("1 plato", 350, 12), "sopa": ("1 plato", 200, 8), "chairo": ("1 plato", 350, 15),
    "fricase": ("1 plato", 650, 35), "fricasé": ("1 plato", 650, 35), "falso conejo": ("1 plato", 750, 35),
    "lapping": ("1 plato", 1000, 55), "charque": ("1 plato", 800, 45), "keperi": ("1 plato", 900, 55),
    "pollo broaster": ("1 presa", 400, 25), "pollo frito": ("1 presa", 400, 25), "broaster": ("1 presa", 400, 25),
    "api": ("1 vaso", 220, 3), "api con pastel": ("1 vaso con pastel", 450, 8), "pastel": ("1 pastel", 230, 5),
    "sonso": ("1 porción", 300, 9), "masaco": ("1 porción", 400, 8), "humintas": ("1 huminta", 250, 7),
    "huminta": ("1 huminta", 250, 7), "llajua": ("1 porción", 20, 1), "mocochinchi": ("1 vaso", 100, 0),
    "chicha": ("1 vaso", 150, 1), "linaza": ("1 vaso", 90, 1), "tojori": ("1 vaso", 180, 3),
    # Básicos
    "arroz": ("1 taza", 205, 4), "fideo": ("1 plato", 400, 14), "fideos": ("1 plato", 400, 14),
    "pasta": ("1 plato", 400, 14), "papa": ("1 papa", 130, 3),
    "papas fritas": ("1 porción", 365, 4), "pure": ("1 porción", 210, 4), "yuca": ("1 porción", 190, 2),
    "choclo": ("1 choclo", 120, 4), "quinua": ("1 taza", 222, 8), "avena": ("1 taza", 150, 5),
    "pan": ("1 pan", 150, 5), "marraqueta": ("1 marraqueta", 150, 5), "tostada": ("1 tostada", 70, 2),
    "galletas": ("1 porción", 150, 2), "cereal": ("1 taza", 150, 3),
    "frijoles": ("1 taza", 225, 15), "lentejas": ("1 taza", 230, 18), "garbanzos": ("1 taza", 270, 15),
    "ensalada": ("1 plato", 100, 2), "verduras": ("1 porción", 60, 3),
    # Proteínas
    "pollo": ("1 presa", 250, 27), "pechuga": ("1 pechuga", 280, 50), "pechuga de pollo": ("1 pechuga", 280, 50),
    "carne": ("1 porción", 250, 26), "carne de res": ("1 porción", 250, 26), "bistec": ("1 bistec", 300, 30),
    "carne molida": ("1 porción", 280, 24), "cerdo": ("1 porción", 300, 25), "chuleta": ("1 chuleta", 300, 25),
    "pescado": ("1 filete", 200, 30), "trucha": ("1 trucha", 300, 40), "atun": ("1 lata", 190, 40),
    "huevo": ("1 huevo", 78, 6), "salchicha": ("1 salchicha", 150, 6),
    "jamon": ("2 rebanadas", 90, 10), "queso": ("1 porción", 110, 7),
    "proteina": ("1 scoop", 120, 24), "whey": ("1 scoop", 120, 24), "batido de proteina": ("1 batido", 250, 30),
    "yogur": ("1 vaso", 150, 8), "yogurt": ("1 vaso", 150, 8), "leche": ("1 vaso", 150, 8),
    "mantequilla de mani": ("1 cucharada", 95, 4), "mani": ("1 puñado", 170, 7), "almendras": ("1 puñado", 170, 6),
    # Rápida
    "hamburguesa": ("1 hamburguesa", 550, 25), "pizza": ("1 porción", 285, 12), "hot dog": ("1 hot dog", 300, 11),
    "sandwich": ("1 sándwich", 350, 15), "lomito": ("1 lomito", 650, 35), "tacos": ("2 tacos", 400, 18),
    # Frutas
    "banana": ("1 banana", 105, 1), "platano": ("1 plátano", 105, 1), "manzana": ("1 manzana", 95, 0),
    "naranja": ("1 naranja", 62, 1), "mandarina": ("1 mandarina", 45, 1), "papaya": ("1 taza", 60, 1),
    "frutilla": ("1 taza", 50, 1), "frutillas": ("1 taza", 50, 1), "uvas": ("1 taza", 105, 1),
    "sandia": ("1 tajada", 85, 2), "pina": ("1 taza", 80, 1), "palta": ("media palta", 160, 2),
    "aguacate": ("media palta", 160, 2), "ensalada de frutas": ("1 taza", 120, 2),
    # Bebidas y dulces
    "coca": ("1 vaso", 140, 0), "coca cola": ("1 vaso", 140, 0), "gaseosa": ("1 vaso", 140, 0),
    "refresco": ("1 vaso", 100, 0), "jugo": ("1 vaso", 120, 1), "jugo de naranja": ("1 vaso", 110, 2),
    "cafe": ("1 taza", 5, 0), "cafe con leche": ("1 taza", 90, 4), "te": ("1 taza", 2, 0), "mate": ("1 taza", 2, 0),
    "cerveza": ("1 botella", 270, 2), "vino": ("1 copa", 125, 0), "chocolate": ("1 barra", 230, 3),
    "helado": ("1 porción", 210, 4), "torta": ("1 tajada", 350, 4), "galleta": ("1 galleta", 50, 1),
    "energizante": ("1 lata", 110, 0),
}
UNIT_WORDS = r"(?:plato|platos|vaso|vasos|taza|tazas|porcion|porciones|presa|presas|rebanada|rebanadas|lata|latas|botella|botellas|copa|copas|scoop|scoops|cucharada|cucharadas|pedazo|pedazos|tajada|tajadas|unidad|unidades|filete|filetes|pieza|piezas)"
SEPARATORS = re.compile(r",|\s+y\s+|\s+con\s+|\s+mas\s+|\+|\s+tambien\s+")
NAMES = sorted(FOODS, key=len, reverse=True)  # el nombre más largo primero: "pechuga de pollo" antes que "pollo"


def parse_meal(text: str) -> list[dict]:
    """'dos salteñas y una coca' -> [{name, qty, kcal, protein}, ...]. Lo desconocido va con kcal None."""
    items = []
    text = align(text.replace(",", " y "))
    for name in NAMES:  # "café con leche" y "api con pastel" no se parten por el "con"
        if " con " in name or " y " in name:
            text = text.replace(name, name.replace(" ", "_"))
    for chunk in SEPARATORS.split(text.strip()):
        chunk = chunk.replace("_", " ")
        chunk = re.sub(r"^\s*(?:un poco de|algo de|de)\s+", "", chunk).strip()
        if not chunk:
            continue
        qty = 1.0
        match = re.match(r"(\S+)\s+(?:" + UNIT_WORDS + r"\s+(?:de\s+)?)?(.*)", chunk)
        if match and number(match.group(1)) is not None:
            qty, chunk = number(match.group(1)), match.group(2)
        chunk = re.sub(r"^" + UNIT_WORDS + r"\s+(?:de\s+)?", "", chunk).strip()
        # Acepta el plural: "salteñas", "huevos", "panes".
        name = next((n for n in NAMES if re.search(r"\b" + re.escape(n) + r"(?:s|es)?\b", chunk)), None)
        if name is None:
            items.append({"name": chunk, "qty": qty, "kcal": None, "protein": None})
            continue
        portion, kcal, protein = FOODS[name]
        items.append({"name": name, "portion": portion, "qty": qty,
                      "kcal": round(kcal * qty), "protein": round(protein * qty, 1)})
    return items
