from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date

from app.senales import senales_de_nota

METODOS = ("round_robin", "balanceado", "scoring")




@dataclass
class Parametros:
    metodo: str
    fecha_referencia: date               # "hoy" explícito: define quién está ausente
    incluir_lideres: bool = False        # los líderes no reciben registros salvo que se active
    zona_estricta: bool = True           # solo vendedores de la zona del registro
    segmento_estricto: bool = False      # solo vendedores expertos en el segmento del registro
    respetar_no_insistir: bool = True    # 'pidió que no insistiéramos' -> revisión humana
    # Solo para el método scoring:
    peso_zona: float = 40
    peso_segmento: float = 30
    peso_carga: float = 30
    peso_senior: float = 15
    tolerancia_carga: float = 0.10       # diferencia de carga (en % de capacidad) que ya cuenta como "más cargado"
    meses_senior: int = 12               # antigüedad para considerar a alguien "senior"

    def validar(self):
        if self.metodo not in METODOS:
            raise ValueError(f"metodo debe ser uno de {METODOS}, llegó '{self.metodo}'")
        if self.tolerancia_carga < 0:
            raise ValueError("tolerancia_carga no puede ser negativa")

    def a_dict(self) -> dict:
        d = asdict(self)
        d["fecha_referencia"] = self.fecha_referencia.isoformat()
        return d


@dataclass
class Plan:
    asignaciones: list = field(default_factory=list)   # {registro_id, usuario_id, explicacion}
    no_asignados: list = field(default_factory=list)   # {registro_id, motivo, ...}
    carga_inicial: dict = field(default_factory=dict)
    carga_final: dict = field(default_factory=dict)


# ---------------------------------------------------------------- filtros duros

def _ausencia_vigente(ausencias_usuario, ref: date):
    for a in ausencias_usuario:
        if a["desde"] <= ref and (a["hasta"] is None or ref <= a["hasta"]):
            return a
    return None


def _motivo_descarte(u, ausencias_usuario, carga, p: Parametros, registro):
    """Devuelve por qué este usuario NO puede recibir este registro, o None si puede."""
    if u["rol"] == "admin":
        return "rol admin: no recibe registros"
    if u["rol"] == "lider" and not p.incluir_lideres:
        return "es líder (incluir_lideres desactivado)"
    if u["rol"] not in ("vendedor", "lider"):
        return f"rol '{u['rol']}' no asignable"
    if not u["activo"]:
        return "usuario inactivo"
    aus = _ausencia_vigente(ausencias_usuario, p.fecha_referencia)
    if aus:
        hasta = aus["hasta"].isoformat() if aus["hasta"] else "sin fecha de fin"
        return f"ausente ({aus['motivo']}, hasta {hasta})"
    cap = u["capacidad_maxima"]
    if cap is None:
        return "capacidad_maxima sin definir"
    if cap <= 0:
        return "capacidad_maxima = 0"
    if carga >= cap:
        return f"capacidad llena ({carga}/{cap})"
    if p.zona_estricta and u["zona"] != registro["zona"]:
        return f"otra zona ({u['zona']}, el registro es de {registro['zona']})"
    if p.segmento_estricto and u["segmento_experto"] != registro["segmento"]:
        return f"otro segmento ({u['segmento_experto']}, el registro es {registro['segmento']})"
    return None


# ---------------------------------------------------------------- ranking

def _antiguedad_meses(u, ref: date):
    if u["fecha_ingreso"] is None:
        return None
    return (ref - u["fecha_ingreso"]).days / 30.44


def _evaluar_candidatos(candidatos, carga, asignados_run, registro, senales, p: Parametros):
    """Calcula detalle (y puntaje si es scoring) de cada elegible. Devuelve lista ordenada, mejor primero."""
    ratios = {u["id"]: carga[u["id"]] / u["capacidad_maxima"] for u in candidatos}
    ratio_min = min(ratios.values())

    evaluados = []
    for u in candidatos:
        ratio = ratios[u["id"]]
        det = {
            "usuario_id": u["id"],
            "nombre": u["nombre"],
            "carga": carga[u["id"]],
            "capacidad": u["capacidad_maxima"],
            "ratio_carga": round(ratio, 3),
            "asignados_en_esta_ejecucion": asignados_run[u["id"]],
            "zona_coincide": u["zona"] == registro["zona"],
            "segmento_coincide": u["segmento_experto"] == registro["segmento"],
        }
        if p.metodo == "scoring":
            if p.tolerancia_carga > 0:
                penal = min(1.0, (ratio - ratio_min) / p.tolerancia_carga)
            else:
                penal = 0.0 if ratio == ratio_min else 1.0
            meses = _antiguedad_meses(u, p.fecha_referencia)
            es_senior = meses is not None and meses >= p.meses_senior
            desglose = {
                "zona": p.peso_zona if det["zona_coincide"] else 0,
                "segmento": p.peso_segmento if det["segmento_coincide"] else 0,
                "carga": round(p.peso_carga * (1 - penal), 2),
                "senior": p.peso_senior if ("senior" in senales and es_senior) else 0,
            }
            det["desglose"] = desglose
            det["puntaje"] = round(sum(desglose.values()), 2)
        evaluados.append(det)

    if p.metodo == "round_robin":
        clave = lambda d: (d["asignados_en_esta_ejecucion"], d["usuario_id"])
    elif p.metodo == "balanceado":
        clave = lambda d: (d["ratio_carga"], d["asignados_en_esta_ejecucion"], d["usuario_id"])
    else:  # scoring
        clave = lambda d: (-d["puntaje"], d["ratio_carga"], d["usuario_id"])
    evaluados.sort(key=clave)
    return evaluados


CRITERIOS = {
    "round_robin": "menos registros recibidos en esta ejecución; empate -> menor id",
    "balanceado": "menor carga relativa (carga/capacidad); empate -> menos recibidos en esta ejecución -> menor id",
    "scoring": "mayor puntaje; empate -> menor carga relativa -> menor id",
}


def _resumen(gan, n_cand, n_desc, p: Parametros):
    base = f"{gan['nombre']} (#{gan['usuario_id']}) con método {p.metodo}: "
    if p.metodo == "scoring":
        partes = [f"puntaje {gan['puntaje']}"]
        if gan["zona_coincide"]:
            partes.append("misma zona")
        if gan["segmento_coincide"]:
            partes.append("segmento coincide")
        if gan["desglose"]["senior"]:
            partes.append("perfil senior pedido en la nota")
        partes.append(f"carga {gan['carga']}/{gan['capacidad']}")
    elif p.metodo == "balanceado":
        partes = [f"menor carga relativa entre los elegibles ({gan['carga']}/{gan['capacidad']})"]
    else:
        partes = [f"turno rotativo ({gan['asignados_en_esta_ejecucion']} recibidos antes en esta ejecución)"]
    return base + ", ".join(partes) + f". Elegibles: {n_cand}, descartados: {n_desc}."


# ---------------------------------------------------------------- motor

def planificar(registros, usuarios, ausencias, carga_inicial, p: Parametros) -> Plan:
    p.validar()
    aus_por_usuario = {}
    for a in ausencias:
        aus_por_usuario.setdefault(a["usuario_id"], []).append(a)

    carga = {u["id"]: carga_inicial.get(u["id"], 0) for u in usuarios}
    asignados_run = Counter({u["id"]: 0 for u in usuarios})
    plan = Plan(carga_inicial=dict(carga))

    # Los más antiguos primero: lo que lleva más tiempo esperando se reparte antes.
    pendientes = sorted((r for r in registros if r["estado"] == "nuevo"),
                        key=lambda r: (r["fecha_creacion"], r["id"]))

    for reg in pendientes:
        senales = senales_de_nota(reg["notas"])

        if reg["duplicado_de_id"] is not None:
            plan.no_asignados.append({
                "registro_id": reg["id"],
                "motivo": f"duplicado del registro #{reg['duplicado_de_id']}: no se asigna",
            })
            continue
        if p.respetar_no_insistir and "no_insistir" in senales:
            plan.no_asignados.append({
                "registro_id": reg["id"],
                "motivo": "requiere revisión humana: la nota indica que pidió no ser contactado de nuevo",
            })
            continue

        candidatos, descartados = [], []
        for u in usuarios:
            motivo = _motivo_descarte(u, aus_por_usuario.get(u["id"], []), carga[u["id"]], p, reg)
            if motivo:
                descartados.append({"usuario_id": u["id"], "nombre": u["nombre"], "motivo": motivo})
            else:
                candidatos.append(u)

        if not candidatos:
            plan.no_asignados.append({
                "registro_id": reg["id"],
                "motivo": "sin vendedores elegibles",
                "descartados": descartados,
            })
            continue

        evaluados = _evaluar_candidatos(candidatos, carga, asignados_run, reg, senales, p)
        ganador = evaluados[0]
        carga_antes = carga[ganador["usuario_id"]]

        carga[ganador["usuario_id"]] += 1
        asignados_run[ganador["usuario_id"]] += 1

        plan.asignaciones.append({
            "registro_id": reg["id"],
            "usuario_id": ganador["usuario_id"],
            "explicacion": {
                "metodo": p.metodo,
                "criterio": CRITERIOS[p.metodo],
                "ganador": {**ganador, "carga_antes": carga_antes, "carga_despues": carga_antes + 1},
                "candidatos": evaluados,
                "descartados": descartados,
                "senales_nota": senales,
                "resumen": _resumen(ganador, len(evaluados), len(descartados), p),
            },
        })

    plan.carga_final = dict(carga)
    return plan

ausencia_vigente = _ausencia_vigente

def motivo_no_elegible(u, ausencias_usuario, carga, registro, fecha: date):
    """Por qué un usuario NO sería elegible para este registro (None si lo sería).
    Se usa en reasignaciones manuales para dejar advertencias en la traza."""
    p = Parametros(metodo="balanceado", fecha_referencia=fecha,
                   incluir_lideres=True, zona_estricta=True, segmento_estricto=False)
    return _motivo_descarte(u, ausencias_usuario, carga, p, registro)