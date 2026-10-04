from collections import Counter


def auditar_datos(registros, asignaciones, ejecuciones) -> list[dict]:
    problemas = []

    def problema(codigo, detalle, **ids):
        problemas.append({"codigo": codigo, "detalle": detalle, **ids})

    estado = {r["id"]: r["estado"] for r in registros}
    ejec = {e["id"]: e for e in ejecuciones}
    por_id = {a["id"]: a for a in asignaciones}
    por_registro = {}
    for a in asignaciones:
        por_registro.setdefault(a["registro_id"], []).append(a)
    reemplazos = Counter(a["reemplaza_a_id"] for a in asignaciones if a["reemplaza_a_id"] is not None)

    for rid, lista in por_registro.items():
        vigentes = [a for a in lista if a["vigente"]]
        if len(vigentes) != 1:
            problema("vigentes_invalidos",
                     f"el registro tiene {len(vigentes)} asignaciones vigentes (debe tener exactamente 1)",
                     registro_id=rid)
        if estado.get(rid) not in ("asignado", "en_gestion"):
            problema("estado_incoherente",
                     f"tiene asignaciones pero su estado es '{estado.get(rid)}'", registro_id=rid)

    for a in asignaciones:
        aid = a["id"]
        e = ejec.get(a["ejecucion_id"])
        if e is None:
            problema("sin_ejecucion", "apunta a una ejecución que no existe", asignacion_id=aid)

        previa_id = a["reemplaza_a_id"]
        if previa_id is not None:
            previa = por_id.get(previa_id)
            if previa is None:
                problema("cadena_rota", f"reemplaza la asignación #{previa_id}, que no existe",
                         asignacion_id=aid)
            else:
                if previa["registro_id"] != a["registro_id"]:
                    problema("cadena_cruzada", f"reemplaza la #{previa_id}, que es de otro registro",
                             asignacion_id=aid)
                if previa["vigente"]:
                    problema("reemplazada_sigue_vigente",
                             f"reemplaza la #{previa_id}, pero esa sigue marcada como vigente",
                             asignacion_id=aid)
                if previa_id >= aid:
                    problema("cadena_desordenada", f"reemplaza la #{previa_id}, que es posterior",
                             asignacion_id=aid)

        if not a["vigente"] and reemplazos.get(aid, 0) != 1:
            problema("retirada_sin_reemplazo",
                     f"no está vigente pero la reemplazan {reemplazos.get(aid, 0)} asignaciones (debe ser 1)",
                     asignacion_id=aid)

        if e is not None:
            expl = a["explicacion"] or {}
            if e["metodo"] == "manual":
                if expl.get("tipo") != "reasignacion_manual" or not (e["parametros"] or {}).get("motivo"):
                    problema("manual_sin_motivo",
                             "reasignación manual sin motivo o sin explicación", asignacion_id=aid)
            elif "ganador" not in expl or "candidatos" not in expl:
                problema("sin_explicacion",
                         "asignación del motor sin explicación (ganador y candidatos)", asignacion_id=aid)
            elif expl["ganador"]["usuario_id"] != a["usuario_id"]:
                problema("explicacion_no_coincide",
                         "la explicación nombra a un ganador distinto del usuario asignado",
                         asignacion_id=aid)

    por_ejecucion = Counter(a["ejecucion_id"] for a in asignaciones)
    for e in ejecuciones:
        if e["metodo"] == "manual" and por_ejecucion.get(e["id"], 0) != 1:
            problema("manual_invalida",
                     f"una reasignación manual debe tener 1 asignación y tiene {por_ejecucion.get(e['id'], 0)}",
                     ejecucion_id=e["id"])

    return problemas