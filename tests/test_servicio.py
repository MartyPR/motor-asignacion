"""Pruebas de integración: motor + base de datos (SQLite en memoria, con los CSV reales)."""
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import carga, servicio
from app.db import crear_engine
from app.models import Asignacion, Base, Ejecucion, Registro
from app.motor import Parametros
from app.semilla import sembrar

HOY = date(2026, 10, 3)


@pytest.fixture
def s():
    engine = crear_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sesion:
        sembrar(sesion, carga.cargar_todo())
        yield sesion


def params(metodo="scoring", **kw):
    return Parametros(metodo=metodo, fecha_referencia=HOY, **kw)


def contar(s, modelo):
    return s.scalar(select(func.count()).select_from(modelo))


def nuevos(s):
    return s.scalar(select(func.count()).select_from(Registro).where(Registro.estado == "nuevo"))


def registro_de(s, usuario_id):
    """Un registro en gestión cuyo dueño histórico es este usuario."""
    return next(r for r, u in servicio.contexto(s)["duenos"].items() if u == usuario_id)

def test_previsualizar_no_escribe(s):
    r = servicio.previsualizar(s, params())
    assert len(r["asignaciones"]) == 67 and len(r["no_asignados"]) == 4
    assert contar(s, Asignacion) == 0 and contar(s, Ejecucion) == 0
    assert nuevos(s) == 71


def test_ejecutar_guarda_la_traza_completa(s):
    r = servicio.ejecutar(s, params(), operador_id=1)
    assert r["asignados"] == 67 and r["no_asignados"] == 4
    assert contar(s, Asignacion) == 67 and contar(s, Ejecucion) == 1
    assert nuevos(s) == 4                      

    ej = s.scalars(select(Ejecucion)).one()
    assert ej.metodo == "scoring" and ej.ejecutado_por == 1
    assert ej.parametros["fecha_referencia"] == "2026-10-03"
    assert len(ej.no_asignados) == 4

    a = s.scalars(select(Asignacion)).first()
    assert a.vigente and a.ejecucion_id == ej.id and a.explicacion["resumen"]


def test_ejecutar_dos_veces_no_duplica(s):
    servicio.ejecutar(s, params(), 1)
    with pytest.raises(servicio.ErrorNegocio) as e:
        servicio.ejecutar(s, params(), 1)
    assert e.value.status == 409
    assert contar(s, Asignacion) == 67 and contar(s, Ejecucion) == 1


def test_la_huella_detecta_que_los_datos_cambiaron(s):
    huella = servicio.previsualizar(s, params())["huella"]
    with pytest.raises(servicio.ErrorNegocio) as e:
        servicio.ejecutar(s, params(), 1, huella_esperada="otra")
    assert e.value.status == 409 and contar(s, Ejecucion) == 0
    assert servicio.ejecutar(s, params(), 1, huella_esperada=huella)["huella"] == huella


def test_la_carga_incluye_lo_asignado_por_el_motor(s):
    servicio.ejecutar(s, params(), 1)
    assert servicio.contexto(s)["carga_inicial"][10] == 21     


@pytest.mark.parametrize("operador,status", [(3, 403), (4, 403), (999, 404)])
def test_solo_admin_o_lider_ejecuta(s, operador, status):
    with pytest.raises(servicio.ErrorNegocio) as e:
        servicio.ejecutar(s, params(), operador)
    assert e.value.status == status
    assert contar(s, Ejecucion) == 0


def test_un_lider_puede_ejecutar(s):
    assert servicio.ejecutar(s, params(), operador_id=2)["asignados"] == 67


def test_reasignar_deja_cadena_y_un_solo_vigente(s):
    servicio.ejecutar(s, params(), 1)
    a1 = s.scalars(select(Asignacion).where(Asignacion.usuario_id == 10)).first()

    r = servicio.reasignar(s, a1.registro_id, 14, 1, "Cuenta técnica para un industrial", HOY)

    s.refresh(a1)
    assert a1.vigente is False
    assert r["reemplaza_a_id"] == a1.id
    vigentes = s.scalars(select(Asignacion).where(
        Asignacion.registro_id == a1.registro_id, Asignacion.vigente.is_(True))).all()
    assert len(vigentes) == 1 and vigentes[0].usuario_id == 14
    assert contar(s, Asignacion) == 68
    assert s.get(Ejecucion, r["ejecucion_id"]).metodo == "manual"


def test_reasignar_registro_con_dueno_historico(s):
    rid = registro_de(s, 4)                    
    carga0 = servicio.contexto(s)["carga_inicial"]

    r = servicio.reasignar(s, rid, 8, 1, "Nicolás está inactivo", HOY)

    assert r["reemplaza_a_id"] is None         
    a = s.get(Asignacion, r["asignacion_id"])
    assert a.explicacion["dueno_anterior"] == {"usuario_id": 4, "origen": "actividad"}
    carga1 = servicio.contexto(s)["carga_inicial"]
    assert carga1[4] == carga0[4] - 1 and carga1[8] == carga0[8] + 1
    assert s.get(Registro, rid).estado == "asignado"


def test_reasignar_validaciones(s):
    rid = registro_de(s, 8)
    casos = [
        (dict(registro_id=rid, usuario_id=8, motivo="prueba"), 409),     
        (dict(registro_id=rid, usuario_id=3, motivo="   "), 422),        
        (dict(registro_id=rid, usuario_id=4, motivo="prueba"), 422),     
        (dict(registro_id=rid, usuario_id=999, motivo="prueba"), 404),   
        (dict(registro_id=99999, usuario_id=3, motivo="prueba"), 404),   
    ]
    for kw, status in casos:
        with pytest.raises(servicio.ErrorNegocio) as e:
            servicio.reasignar(s, operador_id=1, fecha=HOY, **kw)
        assert e.value.status == status

    descartado = s.scalars(select(Registro).where(Registro.estado == "descartado")).first()
    with pytest.raises(servicio.ErrorNegocio) as e:
        servicio.reasignar(s, descartado.id, 3, 1, "prueba", HOY)
    assert e.value.status == 409
    assert contar(s, Asignacion) == 0           


def test_reasignar_a_un_ausente_se_permite_con_advertencia(s):
    rid = registro_de(s, 8)
    r = servicio.reasignar(s, rid, 6, 1, "Cubrir una cuenta de Andrés", HOY)   
    assert any("ausente" in adv for adv in r["advertencias"])
    a = s.get(Asignacion, r["asignacion_id"])
    assert a.explicacion["advertencias"] == r["advertencias"]


# ---------------------------------------------------------------- listados

def test_listados_para_la_consola(s):
    assert len(servicio.listar_pendientes(s)) == 71
    v = {x["id"]: x for x in servicio.listar_vendedores(s, HOY)}
    assert 1 not in v                                             
    assert v[4]["estado"] == "inactivo" and v[6]["estado"] == "ausente"
    assert v[7]["estado"] == "sin capacidad" and v[8]["estado"] == "disponible"
    assert [o["id"] for o in servicio.listar_operadores(s)] == [1, 2, 5, 9, 12]

    servicio.ejecutar(s, params(), 1)
    e = servicio.listar_ejecuciones(s)[0]
    assert e["asignados"] == 67 and e["no_asignados"] == 4 and e["ejecutado_por_nombre"]