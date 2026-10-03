import pytest

from app import carga
from app import limpieza as L


@pytest.mark.parametrize("entrada,esperado", [
    ("ANT", "Antioquia"), ("Bogotá", "Centro"), ("Occidente ", "Occidente"),
    ("COSTA", "Costa"), ("centro", "Centro"), ("", None), (None, None), ("Narnia", None),
])
def test_normalizar_zona(entrada, esperado):
    assert L.normalizar_zona(entrada) == esperado


@pytest.mark.parametrize("emp,ing,sector,esperado", [
    (300, 1_000_000, "Retail", "corporativo"),
    (10, 40_000_000_000, "Retail", "corporativo"),
    (40, 2_000_000_000, "Textil", "industrial"),
    (40, 2_000_000_000, "Retail", "pyme"),
    (None, 5_000_000_000, None, "pyme"),
    (None, None, "Textil", None),
])
def test_derivar_segmento(emp, ing, sector, esperado):
    assert L.derivar_segmento(emp, ing, sector) == esperado


@pytest.fixture(scope="module")
def datos():
    return carga.cargar_todo()


def test_conteos(datos):
    assert len(datos["registros"]) == 167
    assert len(datos["usuarios"]) == 18
    assert len(datos["equipos"]) == 5


def test_registros_quedan_limpios(datos):
    regs = datos["registros"]
    assert all(r["zona"] in {"Centro", "Antioquia", "Occidente", "Costa"} for r in regs)
    assert all(r["estado"] in L.ESTADOS for r in regs)
    assert all(r["segmento"] is not None for r in regs)
    assert sum(r["estado"] == "nuevo" for r in regs) == 71


def test_zona_coherente_con_ciudad(datos):
    incoherentes = [r["id"] for r in datos["registros"]
                    if any(c.startswith("zona incoherente") for c in r["calidad"])]
    assert incoherentes == []


def test_duplicados_por_nit(datos):
    dups = {r["id"]: r["duplicado_de_id"] for r in datos["registros"] if r["duplicado_de_id"]}
    assert dups == {166: 31, 165: 2, 167: 74}


def test_usuarios_problematicos(datos):
    u = {x["id"]: x for x in datos["usuarios"]}
    assert u[17]["equipo_id"] is None and u[17]["zona"] == "Costa"
    assert u[18]["zona"] == "Centro"
    assert u[6]["capacidad_maxima"] is None
    assert u[7]["capacidad_maxima"] == 0
    assert u[14]["fecha_ingreso"] is None
    assert u[4]["activo"] is False
    assert u[4]["zona"] == "Centro"