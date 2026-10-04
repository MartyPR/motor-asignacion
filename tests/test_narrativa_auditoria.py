import copy
from datetime import date, datetime

import pytest

from app import carga
from app.auditoria import auditar_datos
from app.motor import Parametros, planificar
from app.narrativa import narrar

HOY = date(2026, 10, 3)
CUANDO = datetime(2026, 10, 3, 9, 30)


@pytest.fixture(scope="module")
def mundo():
    d = carga.cargar_todo()
    ci = carga.carga_desde_actividad(d["registros"], d["actividad"])
    planes = {m: planificar(d["registros"], d["usuarios"], d["ausencias"], ci,
                            Parametros(metodo=m, fecha_referencia=HOY))
              for m in ("scoring", "balanceado", "round_robin")}
    return {"d": d, "planes": planes,
            "reg": {r["id"]: r for r in d["registros"]},
            "nombre": {u["id"]: u["nombre"] for u in d["usuarios"]}}


def data_de_motor(mundo, metodo="scoring", registro_id=None, vigente=True):
    """Arma el diccionario que produciría servicio.explicar() para una asignación del motor."""
    plan = mundo["planes"][metodo]
    a = next(x for x in plan.asignaciones if registro_id in (None, x["registro_id"]))
    reg = mundo["reg"][a["registro_id"]]
    return {
        "registro": reg,
        "dueno_actual": {"usuario_id": a["usuario_id"], "nombre": mundo["nombre"][a["usuario_id"]],
                         "origen": "asignacion"} if vigente else None,
        "historial": [{
            "asignacion_id": 1, "usuario_id": a["usuario_id"], "usuario": mundo["nombre"][a["usuario_id"]],
            "vigente": vigente, "reemplaza_a_id": None, "creado_en": CUANDO, "motivo": None,
            "explicacion": a["explicacion"],
            "ejecucion": {"id": 1, "metodo": metodo, "parametros": Parametros(metodo=metodo, fecha_referencia=HOY).a_dict(),
                          "fecha_referencia": HOY, "ejecutado_por": 1, "ejecutado_por_nombre": "Administrador",
                          "creado_en": CUANDO},
        }],
        "rechazos": [], "actividad_previa": [], "llamadas_ia": [],
    }


def texto(secciones):
    return " ".join(s["texto"] for s in secciones)


# ---------------------------------------------------------------- narrativa

@pytest.mark.parametrize("metodo", ["scoring", "balanceado", "round_robin"])
def test_el_relato_nombra_metodo_ganador_y_estado(mundo, metodo):
    data = data_de_motor(mundo, metodo)
    t = texto(narrar(data))
    assert data["registro"]["razon_social"] in t
    assert f"método «{metodo}»" in t
    assert data["historial"][0]["usuario"] in t
    assert "Es la asignación vigente" in t
    assert "Se descartaron" in t and "Parámetros: zona estricta" in t


def test_el_relato_del_scoring_muestra_puntaje_y_segundo_lugar(mundo):
    t = texto(narrar(data_de_motor(mundo, "scoring")))
    assert "puntos" in t and "Quedó segundo" in t


def test_el_relato_agrupa_los_motivos_de_descarte(mundo):
    t = texto(narrar(data_de_motor(mundo, "scoring")))
    assert "otra zona ×" in t and "usuario inactivo ×1" in t


def test_el_relato_de_una_reasignacion_manual(mundo):
    data = data_de_motor(mundo, "scoring", vigente=False)
    data["historial"].append({
        "asignacion_id": 2, "usuario_id": 14, "usuario": "Ricardo", "vigente": True, "reemplaza_a_id": 1,
        "creado_en": CUANDO, "motivo": "Cuenta técnica",
        "dueno_anterior_nombre": data["historial"][0]["usuario"],
        "explicacion": {"tipo": "reasignacion_manual", "dueno_anterior": {"usuario_id": 3, "origen": "asignacion"},
                        "advertencias": ["otra zona (Occidente, el registro es de Centro)"], "resumen": "x"},
        "ejecucion": {"id": 2, "metodo": "manual", "parametros": {"motivo": "Cuenta técnica"},
                      "fecha_referencia": HOY, "ejecutado_por": 1, "ejecutado_por_nombre": "Administrador",
                      "creado_en": CUANDO},
    })
    t = texto(narrar(data))
    assert "reasignó el registro manualmente a Ricardo" in t
    assert "Motivo: Cuenta técnica" in t and "Reemplaza la asignación #1" in t
    assert "Advertencia registrada" in t and "Fue reemplazada después" in t


def test_el_relato_de_un_registro_con_dueno_historico(mundo):
    duenos = carga.duenos_actuales(mundo["d"]["registros"], mundo["d"]["actividad"])
    rid = next(r for r, u in duenos.items() if u == 4)
    previas = [a for a in mundo["d"]["actividad"] if a["registro_id"] == rid]
    data = {"registro": mundo["reg"][rid],
            "dueno_actual": {"usuario_id": 4, "nombre": mundo["nombre"][4], "origen": "actividad"},
            "historial": [], "rechazos": [], "llamadas_ia": [],
            "actividad_previa": [{**a, "usuario": mundo["nombre"][a["usuario_id"]]} for a in previas]}
    t = texto(narrar(data))
    assert "Antes del motor ya registra" in t and "sin asignación del motor" in t


def test_el_relato_de_un_registro_que_el_motor_no_asigno(mundo):
    data = {"registro": mundo["reg"][165], "dueno_actual": None, "historial": [],
            "rechazos": [{"ejecucion_id": 7, "creado_en": CUANDO, "ejecutado_por_nombre": "Administrador",
                          "motivo": "duplicado del registro #2: no se asigna"}],
            "actividad_previa": [], "llamadas_ia": []}
    t = texto(narrar(data))
    assert "el motor no lo asignó: duplicado del registro #2" in t
    assert "Sigue pendiente de asignar" in t


def test_el_relato_incluye_notas_y_correcciones_de_datos(mundo):
    r = next(x for x in mundo["d"]["registros"] if x["notas"] and x["calidad"])
    data = {"registro": r, "dueno_actual": None, "historial": [], "rechazos": [],
            "actividad_previa": [], "llamadas_ia": []}
    t = texto(narrar(data))
    assert "Nota original" in t and "Al cargar los datos se corrigió" in t


def test_el_relato_no_inventa_nada_fuera_de_la_traza(mundo):
    data = data_de_motor(mundo, "scoring")
    assert narrar(data) == narrar(copy.deepcopy(data))          # mismo input, mismo relato
    assert [s["titulo"] for s in narrar(data)] == ["Cómo entró", "Qué se decidió y por qué", "Dónde está hoy"]


# ---------------------------------------------------------------- auditoría

def traza_sana():
    """a1 (retirada) -> a2 (manual, vigente) sobre el registro 1; a3 vigente sobre el registro 2."""
    registros = [{"id": 1, "estado": "asignado"}, {"id": 2, "estado": "asignado"}]
    ejecuciones = [
        {"id": 1, "metodo": "scoring", "parametros": {}, "no_asignados": []},
        {"id": 2, "metodo": "manual", "parametros": {"motivo": "x"}, "no_asignados": []},
    ]
    motor = {"ganador": {"usuario_id": 3}, "candidatos": [{"usuario_id": 3}]}
    asignaciones = [
        {"id": 1, "registro_id": 1, "usuario_id": 3, "ejecucion_id": 1, "reemplaza_a_id": None,
         "vigente": False, "explicacion": motor},
        {"id": 2, "registro_id": 1, "usuario_id": 8, "ejecucion_id": 2, "reemplaza_a_id": 1,
         "vigente": True, "explicacion": {"tipo": "reasignacion_manual"}},
        {"id": 3, "registro_id": 2, "usuario_id": 3, "ejecucion_id": 1, "reemplaza_a_id": None,
         "vigente": True, "explicacion": motor},
    ]
    return registros, asignaciones, ejecuciones


def test_una_traza_sana_no_tiene_problemas():
    assert auditar_datos(*traza_sana()) == []


def codigos(regs, asigs, ejs):
    return {p["codigo"] for p in auditar_datos(regs, asigs, ejs)}


def test_detecta_registro_sin_dueno_vigente():
    r, a, e = traza_sana()
    a[1]["vigente"] = False
    assert "vigentes_invalidos" in codigos(r, a, e)


def test_detecta_dos_vigentes():
    r, a, e = traza_sana()
    a[0]["vigente"] = True
    assert {"vigentes_invalidos", "reemplazada_sigue_vigente"} <= codigos(r, a, e)


def test_detecta_cadena_rota():
    r, a, e = traza_sana()
    a[1]["reemplaza_a_id"] = 99
    assert "cadena_rota" in codigos(r, a, e)


def test_detecta_cadena_cruzada_entre_registros():
    r, a, e = traza_sana()
    a[1]["reemplaza_a_id"] = 3
    assert "cadena_cruzada" in codigos(r, a, e)


def test_detecta_asignacion_retirada_que_nadie_reemplazo():
    r, a, e = traza_sana()
    a[1]["reemplaza_a_id"] = None
    assert "retirada_sin_reemplazo" in codigos(r, a, e)


def test_detecta_estado_incoherente():
    r, a, e = traza_sana()
    r[1]["estado"] = "nuevo"
    assert "estado_incoherente" in codigos(r, a, e)


def test_detecta_explicacion_ausente_o_que_no_coincide():
    r, a, e = traza_sana()
    a[2]["explicacion"] = {}
    assert "sin_explicacion" in codigos(r, a, e)
    r, a, e = traza_sana()
    a[2]["usuario_id"] = 15
    assert "explicacion_no_coincide" in codigos(r, a, e)


def test_detecta_reasignacion_manual_sin_motivo():
    r, a, e = traza_sana()
    e[1]["parametros"] = {}
    assert "manual_sin_motivo" in codigos(r, a, e)


def test_detecta_asignacion_sin_ejecucion():
    r, a, e = traza_sana()
    a[2]["ejecucion_id"] = 42
    assert "sin_ejecucion" in codigos(r, a, e)