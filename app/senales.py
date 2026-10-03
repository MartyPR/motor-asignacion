
import re

from app.limpieza import sin_tildes

PATRONES = {
    "no_insistir": r"no insistieramos",
    "senior": r"alguien senior",
}


def senales_de_nota(nota) -> list[str]:
    texto = sin_tildes(nota or "").lower()
    return sorted(nombre for nombre, patron in PATRONES.items() if re.search(patron, texto))