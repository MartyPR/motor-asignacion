import unicodedata
from datetime import date


CIUDAD_ZONA = {
    **dict.fromkeys(["Bogotá", "Bucaramanga", "Chía", "Cúcuta", "Soacha", "Tunja", "Villavicencio"], "Centro"),
    **dict.fromkeys(["Armenia", "Cali", "Manizales", "Palmira", "Pereira"], "Occidente"),
    **dict.fromkeys(["Barranquilla", "Cartagena", "Montería", "Santa Marta", "Sincelejo"], "Costa"),
    **dict.fromkeys(["Medellín", "Envigado", "Itagüí", "Rionegro"], "Antioquia"),
}

ZONA_ALIAS = {
    "centro": "Centro",
    "bogota": "Centro",
    "antioquia": "Antioquia",
    "ant": "Antioquia",
    "occidente": "Occidente",
    "costa": "Costa",
}

ESTADOS = {"nuevo", "asignado", "en_gestion", "descartado"}


UMBRAL_EMPLEADOS_CORPORATIVO = 250
UMBRAL_INGRESOS_CORPORATIVO = 30_000_000_000
SECTORES_INDUSTRIALES = {
    "Manufactura", "Metalmecánica", "Química", "Minería",
    "Agroindustria", "Textil", "Alimentos y bebidas",
}


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def vacio_a_none(valor):
    valor = (valor or "").strip()
    return valor or None


def a_int(valor):
    valor = vacio_a_none(valor)
    return int(valor) if valor is not None else None


def a_fecha(valor):
    valor = vacio_a_none(valor)
    return date.fromisoformat(valor) if valor else None


def a_bool(valor) -> bool:
    return (valor or "").strip().lower() in ("true", "1", "si", "sí")


def normalizar_zona(valor):
    """'ANT' -> 'Antioquia', 'Bogotá' -> 'Centro'. None si viene vacía o no se reconoce."""
    valor = vacio_a_none(valor)
    if valor is None:
        return None
    return ZONA_ALIAS.get(sin_tildes(valor).lower())


def zona_por_ciudad(ciudad):
    return CIUDAD_ZONA.get((ciudad or "").strip())


def derivar_segmento(empleados, ingresos, sector):
    """Corporativo si es grande; si no, industrial por sector; si no, pyme.
    None solo si faltan empleados e ingresos a la vez."""
    if empleados is None and ingresos is None:
        return None
    grande = (empleados is not None and empleados >= UMBRAL_EMPLEADOS_CORPORATIVO) or \
             (ingresos is not None and ingresos >= UMBRAL_INGRESOS_CORPORATIVO)
    if grande:
        return "corporativo"
    if sector in SECTORES_INDUSTRIALES:
        return "industrial"
    return "pyme"