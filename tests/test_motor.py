from collections import Counter
from datetime import date

import pytest

from app import carga
from app.motor import METODOS, Parametros, planificar
from app.senales import senales_de_nota

HOY = date(2026, 10, 3)
# Vendedores que SÍ pueden recibir registros el 3-oct-2026:
# excluidos: 1 admin, 2/5/9/12 líderes, 4 inactivo, 6 y 11 ausentes, 7 capacidad 0
ELEGIBLES = {3, 8, 10, 13, 14, 15, 16, 17, 18}


@pytest.fixture(scope="module")
def datos():
    d = carga.cargar_todo()
    d["carga_inicial"] = carga.carga_desde_actividad(d["registros"], d["actividad"])
    return d


def correr(datos, metodo="scoring", fecha=HOY, carga_inicial=None, **kw):
    ci = datos["carga_inicial"] if carga_inicial is None else carga_inicial
    p = Parametros(metodo=metodo, fecha_referencia=fecha, **kw)
    return planificar(datos["registros"], datos["usuarios"], datos["ausencias"], ci, p)


def test_carga_inicial_desde_actividad(datos):
    ci = datos["carga_inicial"]
    assert sum(ci.values()) == 76          # 46 en gestión + 30 asignados
    assert ci[8] == 11 and ci[4] == 8


@pytest.mark.parametrize("metodo", list(METODOS))
def test_solo_asigna_a_elegibles(datos, metodo):
    plan = correr(datos, metodo)
    assert {a["usuario_id"] for a in plan.asignaciones} <= ELEGIBLES


@pytest.mark.parametrize("metodo", list(METODOS))
def test_cada_registro_nuevo_tiene_un_resultado(datos, metodo):
    plan = correr(datos, metodo)
    nuevos = {r["id"] for r in datos["registros"] if r["estado"] == "nuevo"}
    asignados = [a["registro_id"] for a in plan.asignaciones]
    no_asig = [n["registro_id"] for n in plan.no_asignados]
    assert len(asignados) == len(set(asignados))
    assert set(asignados) | set(no_asig) == nuevos
    assert not set(asignados) & set(no_asig)


def test_duplicados_y_no_insistir_no_se_asignan(datos):
    plan = correr(datos)
    motivos = {n["registro_id"]: n["motivo"] for n in plan.no_asignados}
    assert {165, 166, 167} <= set(motivos)
    assert all(motivos[i].startswith("duplicado") for i in (165, 166, 167))
    assert motivos[35].startswith("requiere revisión humana")


def test_no_insistir_se_puede_desactivar(datos):
    plan = correr(datos, respetar_no_insistir=False)
    assert 35 in {a["registro_id"] for a in plan.asignaciones}


def test_zona_estricta(datos):
    regs = {r["id"]: r for r in datos["registros"]}
    usrs = {u["id"]: u for u in datos["usuarios"]}
    plan = correr(datos, "balanceado")
    assert all(usrs[a["usuario_id"]]["zona"] == regs[a["registro_id"]]["zona"]
               for a in plan.asignaciones)


def test_es_deterministico(datos):
    a = correr(datos, "scoring")
    b = correr(datos, "scoring")
    assert a.asignaciones == b.asignaciones and a.no_asignados == b.no_asignados


def test_respeta_capacidad(datos):
    ci = dict(datos["carga_inicial"])
    ci[10] = 40                                   # el único vendedor elegible de Antioquia, lleno
    plan = correr(datos, carga_inicial=ci)
    assert 10 not in {a["usuario_id"] for a in plan.asignaciones}
    sin = [n for n in plan.no_asignados if n["motivo"] == "sin vendedores elegibles"]
    assert sin and all(any("capacidad llena" in d["motivo"] for d in n["descartados"]) for n in sin)


def test_la_fecha_de_referencia_cambia_quien_esta_ausente(datos):
    antes = correr(datos, fecha=date(2026, 10, 1))     # Julián (16) de vacaciones hasta el 2
    despues = correr(datos, fecha=HOY)
    assert 16 not in {a["usuario_id"] for a in antes.asignaciones}
    assert 16 in {a["usuario_id"] for a in despues.asignaciones}


def test_lideres_solo_si_se_activa(datos):
    lideres = {2, 5, 9, 12}
    sin = correr(datos)
    con = correr(datos, incluir_lideres=True)
    assert not lideres & {a["usuario_id"] for a in sin.asignaciones}
    assert lideres & {a["usuario_id"] for a in con.asignaciones}


def test_balanceado_sin_zona_estricta_nivela_la_carga(datos):
    plan = correr(datos, "balanceado", zona_estricta=False)
    finales = [plan.carga_final[i] for i in ELEGIBLES]
    assert max(finales) - min(finales) <= 6


def test_scoring_respeta_mas_el_segmento_que_balanceado(datos):
    regs = {r["id"]: r for r in datos["registros"]}
    usrs = {u["id"]: u for u in datos["usuarios"]}

    def aciertos(plan):
        return sum(usrs[a["usuario_id"]]["segmento_experto"] == regs[a["registro_id"]]["segmento"]
                   for a in plan.asignaciones)

    assert aciertos(correr(datos, "scoring")) > aciertos(correr(datos, "balanceado"))


def test_la_explicacion_permite_reconstruir_la_decision(datos):
    plan = correr(datos)
    for a in plan.asignaciones:
        e = a["explicacion"]
        assert e["candidatos"][0]["usuario_id"] == a["usuario_id"] == e["ganador"]["usuario_id"]
        evaluados = {c["usuario_id"] for c in e["candidatos"]} | {d["usuario_id"] for d in e["descartados"]}
        assert evaluados == {u["id"] for u in datos["usuarios"]}   # nadie queda sin explicar
        assert e["resumen"]


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        Parametros(metodo="magia", fecha_referencia=HOY).validar()


def test_senales_de_nota():
    assert senales_de_nota("Ya lo contactamos en marzo y pidió que no insistiéramos.") == ["no_insistir"]
    assert senales_de_nota("Insistió en hablar con alguien senior.") == ["senior"]
    assert senales_de_nota(None) == []