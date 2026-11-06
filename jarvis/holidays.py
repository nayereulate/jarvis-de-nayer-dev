"""Feriados de Bolivia y de Cochabamba. Los que dependen de la Pascua se calculan para cada año."""
from datetime import date, timedelta


def easter(year: int) -> date:
    """Domingo de Pascua (algoritmo de Butcher para el calendario gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(year: int, cochabamba: bool = True) -> list[dict]:
    sunday = easter(year)
    found = [
        (date(year, 1, 1), "Año Nuevo"),
        (date(year, 1, 22), "Día del Estado Plurinacional"),
        (sunday - timedelta(days=48), "Carnaval (lunes)"),
        (sunday - timedelta(days=47), "Carnaval (martes)"),
        (sunday - timedelta(days=2), "Viernes Santo"),
        (date(year, 5, 1), "Día del Trabajo"),
        (sunday + timedelta(days=60), "Corpus Christi"),
        (date(year, 6, 21), "Año Nuevo Andino Amazónico"),
        (date(year, 8, 6), "Día de la Independencia"),
        (date(year, 11, 2), "Todos Santos"),
        (date(year, 12, 25), "Navidad"),
    ]
    if cochabamba:
        found.append((date(year, 9, 14), "Aniversario de Cochabamba"))
    return [{"date": day.isoformat(), "name": name} for day, name in sorted(found)]


def upcoming(today: date, count: int = 5) -> list[dict]:
    items = holidays(today.year) + holidays(today.year + 1)
    return [item for item in items if item["date"] >= today.isoformat()][:count]
