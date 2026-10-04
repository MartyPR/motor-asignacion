import hashlib
import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import carga as carga_mod
from app.models import Actividad, Asignacion, Ausencia, Ejecucion, Registro, Usuario
from app.motor import Parametros, Plan, ausencia_vigente, motivo_no_elegible, planificar
from app.senales import senales_de_nota


class ErrorNegocio(Exception):
    def __init__(self, mensaje: str, status: int = 422):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


def _fila(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def contexto(s: Session) -> dict:
    registros = [_fila(r) for r in s.scalars(select(Registro).order_by(Registro.id))]
    usuarios = [_fila(u) for u in s.scalars(select(Usuario).order_by(Usuario.id))]
    ausencias = [_fila(a) for a in s.scalars(select(Ausencia))]
    actividad = [_fila(a) for a in s.scalars(select(Actividad))]
    vigentes = {a.registro_id: a.usuario_id
                for a in s.scalars(select(Asignacion).where(Asignacion.vigente.is_(True)))}
    return {
        "registros": registros,
        "usuarios": usuarios,
        "ausencias": ausencias,
        "actividad": actividad,
        "duenos": carga_mod.duenos_actuales(registros, actividad, vigentes),
        "carga_inicial": carga_mod.carga_con_asignaciones(registros, actividad, vigentes),
    }


def _validar_operador(s: Session, operador_id: int) -> Usuario:
    op = s.get(Usuario, operador_id)
    if op is None:
        raise ErrorNegocio(f"El operador {operador_id} no existe", 404)
    if not op.activo or op.rol not in ("admin", "lider"):
        raise ErrorNegocio("Solo un admin o un líder activo puede ejecutar o reasignar", 403)
    return op

def calcular_huella(plan: Plan, params: Parametros) -> str:
    base = {
        "params": params.a_dict(),
        "asignaciones": [[a["registro_id"], a["usuario_id"]] for a in plan.asignaciones],
        "no_asignados": [n["registro_id"] for n in plan.no_asignados],
    }
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:16]


def resumen_plan(plan: Plan, huella: str) -> dict:
    return {
        "huella": huella,
        "asignaciones": [
            {"registro_id": a["registro_id"], "usuario_id": a["usuario_id"],
             "resumen": a["explicacion"]["resumen"]}
            for a in plan.asignaciones
        ],
        "no_asignados": [{"registro_id": n["registro_id"], "motivo": n["motivo"]}
                         for n in plan.no_asignados],
        "carga_inicial": plan.carga_inicial,
        "carga_final": plan.carga_final,
    }


def previsualizar(s: Session, params: Parametros) -> dict:
    ctx = contexto(s)
    plan = planificar(ctx["registros"], ctx["usuarios"], ctx["ausencias"], ctx["carga_inicial"], params)
    return resumen_plan(plan, calcular_huella(plan, params))


def ejecutar(s: Session, params: Parametros, operador_id: int, huella_esperada: str | None = None) -> dict:
    _validar_operador(s, operador_id)
    ctx = contexto(s)
    plan = planificar(ctx["registros"], ctx["usuarios"], ctx["ausencias"], ctx["carga_inicial"], params)
    huella = calcular_huella(plan, params)

    if huella_esperada is not None and huella_esperada != huella:
        raise ErrorNegocio("Los datos cambiaron desde la previsualización. Vuelve a previsualizar.", 409)
    if not plan.asignaciones:
        raise ErrorNegocio("No hay registros asignables con estos parámetros.", 409)

    ejecucion = Ejecucion(
        metodo=params.metodo,
        parametros=params.a_dict(),
        fecha_referencia=params.fecha_referencia,
        ejecutado_por=operador_id,
        no_asignados=plan.no_asignados,
    )
    s.add(ejecucion)
    s.flush()  # para tener ejecucion.id

    ids = [a["registro_id"] for a in plan.asignaciones]
    registros = {r.id: r for r in s.scalars(select(Registro).where(Registro.id.in_(ids)))}
    for a in plan.asignaciones:
        s.add(Asignacion(
            registro_id=a["registro_id"],
            usuario_id=a["usuario_id"],
            ejecucion_id=ejecucion.id,
            explicacion=a["explicacion"],
        ))
        registros[a["registro_id"]].estado = "asignado"

    resultado = {
        "ejecucion_id": ejecucion.id,
        "asignados": len(plan.asignaciones),
        "no_asignados": len(plan.no_asignados),
        "huella": huella,
    }
    s.commit()
    return resultado


# ---------------------------------------------------------------- reasignar

def reasignar(s: Session, registro_id: int, usuario_id: int, operador_id: int,
              motivo: str, fecha: date | None = None) -> dict:
    operador = _validar_operador(s, operador_id)
    if not motivo or not motivo.strip():
        raise ErrorNegocio("El motivo es obligatorio en una reasignación", 422)

    registro = s.get(Registro, registro_id)
    if registro is None:
        raise ErrorNegocio(f"El registro {registro_id} no existe", 404)
    if registro.estado == "descartado":
        raise ErrorNegocio("Un registro descartado no se puede reasignar", 409)

    destino = s.get(Usuario, usuario_id)
    if destino is None:
        raise ErrorNegocio(f"El usuario {usuario_id} no existe", 404)
    if not destino.activo or destino.rol not in ("vendedor", "lider"):
        raise ErrorNegocio("El destino debe ser un vendedor o líder activo", 422)

    fecha = fecha or date.today()
    ctx = contexto(s)
    nombres = {u["id"]: u["nombre"] for u in ctx["usuarios"]}

    anterior = s.scalars(
        select(Asignacion).where(Asignacion.registro_id == registro_id, Asignacion.vigente.is_(True))
    ).first()
    dueno_prev = anterior.usuario_id if anterior else ctx["duenos"].get(registro_id)
    if dueno_prev == usuario_id:
        raise ErrorNegocio("Ese usuario ya es el responsable del registro", 409)

    if anterior is not None:
        origen = "asignacion"
    elif dueno_prev is not None:
        origen = "actividad"     
    else:
        origen = None

    aus_destino = [a for a in ctx["ausencias"] if a["usuario_id"] == usuario_id]
    adv = motivo_no_elegible(_fila(destino), aus_destino, ctx["carga_inicial"].get(usuario_id, 0),
                             _fila(registro), fecha)
    advertencias = [adv] if adv else []

    de = nombres.get(dueno_prev, "sin dueño registrado")
    explicacion = {
        "tipo": "reasignacion_manual",
        "dueno_anterior": {"usuario_id": dueno_prev, "origen": origen},
        "advertencias": advertencias,
        "resumen": f"Reasignación manual por {operador.nombre}: de {de} a {destino.nombre}. "
                   f"Motivo: {motivo.strip()}",
    }

    ejecucion = Ejecucion(
        metodo="manual",
        parametros={"motivo": motivo.strip(), "registro_id": registro_id},
        fecha_referencia=fecha,
        ejecutado_por=operador_id,
        no_asignados=[],
    )
    s.add(ejecucion)
    s.flush()

    if anterior is not None:
        anterior.vigente = False
        s.flush()  

    nueva = Asignacion(
        registro_id=registro_id,
        usuario_id=usuario_id,
        ejecucion_id=ejecucion.id,
        reemplaza_a_id=anterior.id if anterior else None,
        vigente=True,
        explicacion=explicacion,
        motivo=motivo.strip(),
    )
    s.add(nueva)
    registro.estado = "asignado"
    s.flush()

    resultado = {
        "asignacion_id": nueva.id,
        "ejecucion_id": ejecucion.id,
        "reemplaza_a_id": nueva.reemplaza_a_id,
        "advertencias": advertencias,
    }
    s.commit()
    return resultado

def listar_pendientes(s: Session) -> list[dict]:
    filas = s.scalars(select(Registro).where(Registro.estado == "nuevo")
                      .order_by(Registro.fecha_creacion, Registro.id))
    salida = []
    for r in filas:
        d = _fila(r)
        d["senales"] = senales_de_nota(r.notas)
        salida.append(d)
    return salida


def listar_vendedores(s: Session, fecha: date) -> list[dict]:
    ctx = contexto(s)
    aus = {}
    for a in ctx["ausencias"]:
        aus.setdefault(a["usuario_id"], []).append(a)

    salida = []
    for u in ctx["usuarios"]:
        if u["rol"] == "admin":
            continue
        a = ausencia_vigente(aus.get(u["id"], []), fecha)
        cap = u["capacidad_maxima"]
        if not u["activo"]:
            estado = "inactivo"
        elif a:
            estado = "ausente"
        elif cap is None or cap <= 0:
            estado = "sin capacidad"
        else:
            estado = "disponible"
        salida.append({
            "id": u["id"], "nombre": u["nombre"], "rol": u["rol"], "zona": u["zona"],
            "segmento_experto": u["segmento_experto"], "capacidad_maxima": cap,
            "carga": ctx["carga_inicial"].get(u["id"], 0),
            "estado": estado, "detalle_ausencia": a["motivo"] if a else None,
        })
    return salida


def listar_operadores(s: Session) -> list[dict]:
    filas = s.scalars(select(Usuario).where(Usuario.activo.is_(True), Usuario.rol.in_(["admin", "lider"]))
                      .order_by(Usuario.id))
    return [{"id": u.id, "nombre": u.nombre, "rol": u.rol} for u in filas]


def listar_ejecuciones(s: Session, limite: int = 50) -> list[dict]:
    conteo = dict(s.execute(
        select(Asignacion.ejecucion_id, func.count()).group_by(Asignacion.ejecucion_id)
    ).all())
    nombres = {u.id: u.nombre for u in s.scalars(select(Usuario))}
    ejecuciones = s.scalars(select(Ejecucion).order_by(Ejecucion.id.desc()).limit(limite)).all()
    return [{
        "id": e.id, "metodo": e.metodo, "parametros": e.parametros,
        "fecha_referencia": e.fecha_referencia,
        "ejecutado_por": e.ejecutado_por, "ejecutado_por_nombre": nombres.get(e.ejecutado_por),
        "creado_en": e.creado_en,
        "asignados": conteo.get(e.id, 0), "no_asignados": len(e.no_asignados or []),
    } for e in ejecuciones]