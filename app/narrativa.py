from collections import Counter

from app.senales import senales_de_nota


def _dia(valor) -> str:
    return str(valor)[:10] if valor else "fecha desconocida"


def _plata(valor) -> str:
    if valor is None:
        return "no informados"
    millones = f"{valor / 1_000_000:,.0f}".replace(",", ".")
    return f"${millones} millones"


def _categoria(motivo: str) -> str:
    """'otra zona (Centro, el registro es de Costa)' -> 'otra zona'."""
    return motivo.split(" (")[0].split(":")[0]


def _descartados(descartados) -> str:
    if not descartados:
        return "No se descartó a nadie."
    conteo = Counter(_categoria(d["motivo"]) for d in descartados)
    detalle = ", ".join(f"{motivo} ×{n}" for motivo, n in conteo.most_common())
    return f"Se descartaron {len(descartados)} usuarios: {detalle}."


def _estado_cadena(h) -> str:
    return "Es la asignación vigente." if h["vigente"] else "Fue reemplazada después."



def _entrada(data) -> str:
    r = data["registro"]
    partes = [f"{r['razon_social']} (NIT {r['nit']}) entró el {_dia(r['fecha_creacion'])} "
              f"por la fuente «{r['fuente']}»."]
    detalles = []
    if r["sector"]:
        detalles.append(f"sector {r['sector']}")
    detalles.append(f"{r['empleados']} empleados" if r["empleados"] is not None else "empleados no informados")
    detalles.append(f"ingresos estimados {_plata(r['ingresos_estimados'])}")
    partes.append("Datos: " + ", ".join(detalles) + ".")
    partes.append(f"Ciudad {r['ciudad']}, zona {r['zona']}. "
                  f"Segmento {r['segmento'] or 'no determinado'} (derivado al cargar los datos, no venía en el original).")
    if r["calidad"]:
        partes.append("Al cargar los datos se corrigió o anotó: " + "; ".join(r["calidad"]) + ".")
    if r["notas"]:
        partes.append(f"Nota original: «{r['notas']}».")
        senales = senales_de_nota(r["notas"])
        if senales:
            partes.append("Señales detectadas en la nota: " + ", ".join(senales) + ".")
    return " ".join(partes)


def _por_el_motor(h) -> str:
    e, ej = h["explicacion"], h["ejecucion"]
    p, g = ej["parametros"] or {}, e["ganador"]
    t = [f"El {_dia(ej['creado_en'])}, {ej['ejecutado_por_nombre']} ejecutó el método «{ej['metodo']}» "
         f"(ejecución #{ej['id']}, fecha de referencia {_dia(ej['fecha_referencia'])}) "
         f"y el registro quedó con {h['usuario']}."]
    t.append(f"Criterio del método: {e['criterio']}.")

    if ej["metodo"] == "scoring":
        d = g["desglose"]
        t.append(f"{h['usuario']} sumó {g['puntaje']} puntos (zona {d['zona']}, segmento {d['segmento']}, "
                 f"carga {d['carga']}, senior {d['senior']}).")
    elif ej["metodo"] == "balanceado":
        t.append(f"{h['usuario']} tenía la menor carga relativa entre los elegibles: "
                 f"{g['carga_antes']} de {g['capacidad']} registros.")
    else:
        t.append(f"Le tocaba el turno: {h['usuario']} había recibido {g['asignados_en_esta_ejecucion']} "
                 f"registros en esa ejecución.")

    cands = e["candidatos"]
    if len(cands) > 1:
        s = cands[1]
        if ej["metodo"] == "scoring":
            t.append(f"Quedó segundo {s['nombre']} con {s['puntaje']} puntos.")
        else:
            t.append(f"Le seguía {s['nombre']} (carga {s['carga']} de {s['capacidad']}).")
    else:
        t.append("Era el único candidato elegible.")
    t.append(_descartados(e["descartados"]))

    t.append("Parámetros: zona " + ("estricta" if p.get("zona_estricta") else "flexible")
             + ", segmento " + ("estricto" if p.get("segmento_estricto") else "como preferencia")
             + ", líderes " + ("incluidos" if p.get("incluir_lideres") else "excluidos") + ".")
    if e.get("senales_nota"):
        t.append("Señales de la nota consideradas: " + ", ".join(e["senales_nota"]) + ".")
    t.append(_estado_cadena(h))
    return " ".join(t)


def _manual(h) -> str:
    e, ej = h["explicacion"], h["ejecucion"]
    origen = {"asignacion": "una asignación del motor", "actividad": "el histórico de actividad",
              None: "sin dueño registrado"}.get(e["dueno_anterior"]["origen"], "origen desconocido")
    antes = h.get("dueno_anterior_nombre") or "nadie"
    t = [f"El {_dia(ej['creado_en'])}, {ej['ejecutado_por_nombre']} reasignó el registro manualmente "
         f"a {h['usuario']} (antes: {antes}, según {origen}). Motivo: {h['motivo']}."]
    if h["reemplaza_a_id"]:
        t.append(f"Reemplaza la asignación #{h['reemplaza_a_id']}.")
    for adv in e.get("advertencias", []):
        t.append(f"Advertencia registrada en ese momento: {adv}.")
    t.append(_estado_cadena(h))
    return " ".join(t)


def _decisiones(data) -> str:
    partes = []
    for h in data["historial"]:
        es_manual = h["explicacion"].get("tipo") == "reasignacion_manual"
        partes.append(_manual(h) if es_manual else _por_el_motor(h))
    for rc in data["rechazos"]:
        partes.append(f"En la ejecución #{rc['ejecucion_id']} ({_dia(rc['creado_en'])}, "
                      f"{rc['ejecutado_por_nombre']}) el motor no lo asignó: {rc['motivo']}.")
    previa = data["actividad_previa"]
    if previa:
        ultima = previa[-1]
        usuarios = sorted({a["usuario"] for a in previa})
        partes.append(f"Antes del motor ya registra {len(previa)} acciones de {', '.join(usuarios)}; "
                      f"la última fue «{ultima['tipo']}» el {_dia(ultima['fecha'])} ({ultima['usuario']}).")
    llamadas = data["llamadas_ia"]
    if llamadas:
        partes.append(f"Se consultó al modelo de IA {len(llamadas)} vez/veces para este registro.")
    return " ".join(partes)


def _situacion_actual(data) -> str:
    estado = data["registro"]["estado"]
    dueno = data["dueno_actual"]
    if dueno:
        origen = ("según la asignación vigente" if dueno["origen"] == "asignacion"
                  else "según el histórico de actividad, sin asignación del motor")
        return f"Hoy el responsable es {dueno['nombre']} ({origen}). Estado del registro: {estado}."
    if estado == "nuevo":
        return "Sigue pendiente de asignar: nadie lo tiene."
    return f"No hay un responsable registrado. Estado del registro: {estado}."


def narrar(data: dict) -> list[dict]:
    secciones = [{"titulo": "Cómo entró", "texto": _entrada(data)}]
    decisiones = _decisiones(data)
    if decisiones:
        secciones.append({"titulo": "Qué se decidió y por qué", "texto": decisiones})
    secciones.append({"titulo": "Dónde está hoy", "texto": _situacion_actual(data)})
    return secciones