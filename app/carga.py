import csv
from pathlib import Path

from app import limpieza as L

RAW = Path("data/raw")


def leer(nombre: str) -> list[dict]:
    with open(RAW / f"{nombre}.csv", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def limpiar_equipos(filas):
    return [
        {
            "id": int(f["id"]),
            "nombre": f["nombre"].strip(),
            "lider_id": L.a_int(f["lider_id"]),
            "zona": L.normalizar_zona(f["zona"]),
        }
        for f in filas
    ]


def limpiar_usuarios(filas, equipos):
    zona_equipo = {e["id"]: e["zona"] for e in equipos}
    salida = []
    for f in filas:
        calidad = []

        zona_original = L.vacio_a_none(f["zona"])
        zona = L.normalizar_zona(f["zona"])
        if zona_original and zona_original != zona:
            calidad.append(f"zona normalizada: '{zona_original}' -> '{zona}'")

        equipo_id = L.a_int(f["equipo_id"])
        if equipo_id is not None and equipo_id not in zona_equipo:
            calidad.append(f"equipo inexistente: equipo_id {equipo_id}, se deja sin equipo")
            equipo_id = None

        if zona is None and equipo_id is not None:
            zona = zona_equipo[equipo_id]
            calidad.append("zona vacia: se tomo la zona del equipo")
        elif zona is None:
            calidad.append("zona vacia: sin forma de inferirla")

        capacidad = L.a_int(f["capacidad_maxima"])
        if capacidad is None:
            calidad.append("capacidad vacia: capacidad_maxima sin definir")
        elif capacidad == 0:
            calidad.append("capacidad cero: capacidad_maxima = 0")

        fecha_ingreso = L.a_fecha(f["fecha_ingreso"])
        if fecha_ingreso is None:
            calidad.append("fecha_ingreso vacia")

        salida.append({
            "id": int(f["id"]),
            "nombre": f["nombre"].strip(),
            "email": f["email"].strip().lower(),
            "rol": f["rol"].strip().lower(),
            "equipo_id": equipo_id,
            "zona": zona,
            "segmento_experto": (L.vacio_a_none(f["segmento_experto"]) or "").lower() or None,
            "capacidad_maxima": capacidad,
            "fecha_ingreso": fecha_ingreso,
            "activo": L.a_bool(f["activo"]),
            "calidad": calidad,
        })
    return salida


def limpiar_registros(filas):
    salida = []
    for f in filas:
        calidad = []
        ciudad = f["ciudad"].strip()

        zona = L.normalizar_zona(f["zona"])
        zona_ciudad = L.zona_por_ciudad(ciudad)
        if zona is None and zona_ciudad:
            zona = zona_ciudad
            calidad.append(f"zona inferida: de la ciudad {ciudad} -> {zona}")
        elif zona and zona_ciudad and zona != zona_ciudad:
            calidad.append(f"zona incoherente: zona {zona} pero la ciudad {ciudad} es de {zona_ciudad}")
        elif L.vacio_a_none(f["zona"]) and f["zona"] != zona:
            calidad.append(f"zona normalizada: '{f['zona']}' -> '{zona}'")

        estado = f["estado"].strip().lower()
        if f["estado"] != estado:
            calidad.append(f"estado normalizado: '{f['estado']}' -> '{estado}'")
        if estado not in L.ESTADOS:
            calidad.append(f"estado desconocido: '{estado}'")

        sector = L.vacio_a_none(f["sector"])
        empleados = L.a_int(f["empleados"])
        ingresos = L.a_int(f["ingresos_estimados"])
        if sector is None:
            calidad.append("dato faltante: sector")
        if empleados is None:
            calidad.append("dato faltante: empleados")
        if ingresos is None:
            calidad.append("dato faltante: ingresos_estimados")

        salida.append({
            "id": int(f["id"]),
            "razon_social": f["razon_social"].strip(),
            "nit": f["nit"].strip(),
            "sector": sector,
            "empleados": empleados,
            "ingresos_estimados": ingresos,
            "ciudad": ciudad,
            "zona": zona,
            "zona_original": f["zona"] or None,
            "fuente": f["fuente"].strip().lower(),
            "notas": L.vacio_a_none(f["notas"]),
            "estado": estado,
            "fecha_creacion": L.a_fecha(f["fecha_creacion"]),
            "segmento": L.derivar_segmento(empleados, ingresos, sector),
            "duplicado_de_id": None,
            "calidad": calidad,
        })

    marcar_duplicados(salida)
    return salida


def marcar_duplicados(registros):
    """Duplicado = mismo NIT. El original es el más antiguo; los demás apuntan a él.
    La razón social NO sirve de clave: hay empresas distintas con el mismo nombre y NIT diferente."""
    por_nit = {}
    for r in registros:
        por_nit.setdefault(r["nit"], []).append(r)
    for grupo in por_nit.values():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda r: (r["fecha_creacion"], r["id"]))
        original = grupo[0]
        for dup in grupo[1:]:
            dup["duplicado_de_id"] = original["id"]
            dup["calidad"].append(f"duplicado: mismo NIT que el registro #{original['id']}")


def limpiar_ausencias(filas):
    return [
        {
            "id": int(f["id"]),
            "usuario_id": int(f["usuario_id"]),
            "desde": L.a_fecha(f["desde"]),
            "hasta": L.a_fecha(f["hasta"]),  
            "motivo": f["motivo"].strip(),
        }
        for f in filas
    ]


def limpiar_actividad(filas):
    return [
        {
            "id": int(f["id"]),
            "registro_id": int(f["registro_id"]),
            "usuario_id": int(f["usuario_id"]),
            "tipo": f["tipo"].strip().lower(),
            "fecha": L.a_fecha(f["fecha"]),
        }
        for f in filas
    ]


def cargar_todo() -> dict:
    equipos = limpiar_equipos(leer("equipos"))
    return {
        "equipos": equipos,
        "usuarios": limpiar_usuarios(leer("usuarios"), equipos),
        "registros": limpiar_registros(leer("registros")),
        "ausencias": limpiar_ausencias(leer("ausencias")),
        "actividad": limpiar_actividad(leer("actividad")),
    }


def resumen_calidad(datos: dict) -> dict:
    """Cuenta las anotaciones de calidad por tipo (lo que va antes de los dos puntos)."""
    resumen = {}
    for tabla in ("usuarios", "registros"):
        conteo = {}
        for fila in datos[tabla]:
            for nota in fila["calidad"]:
                tipo = nota.split(":")[0]
                conteo[tipo] = conteo.get(tipo, 0) + 1
        resumen[tabla] = dict(sorted(conteo.items()))
    return resumen