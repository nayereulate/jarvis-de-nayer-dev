"""Texto dicho en voz alta: normalizar sin perder posiciones y leer números escritos con palabras."""
import unicodedata


def align(text: str) -> str:
    """Minúsculas, sin tildes y sin signos, con el mismo largo que el original:
    así lo que se captura (lo que hay que escribir, el texto de una nota) sale del original, con tildes."""
    out = []
    for i, char in enumerate(text):
        base = unicodedata.normalize("NFD", char)[0].lower()[:1]
        # El punto de "wikipedia.org" o "1.5" se queda; el de final de frase no.
        inner_dot = char == "." and 0 < i < len(text) - 1 and text[i - 1].isalnum() and text[i + 1].isalnum()
        out.append(" " if (base in '¿?¡!.,;"«»()[]' and not inner_dot) or not base else base)
    return "".join(out)


NUMBERS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "media": 0.5, "medio": 0.5,
}
UNITS = {"segundo": 1, "segundos": 1, "seg": 1, "minuto": 60, "minutos": 60, "min": 60, "hora": 3600, "horas": 3600}


def number(word: str) -> float | None:
    word = word.strip().replace(",", ".").rstrip("%")
    try:
        return float(word)
    except ValueError:
        return NUMBERS.get(word)
