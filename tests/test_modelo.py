from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import crear_engine
from app.models import Asignacion, Base, Ejecucion, Registro, Usuario


@pytest.fixture
def sesion():
    engine = crear_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([
            Usuario(id=1, nombre="Admin", email="a@x.co", rol="admin", activo=True),
            Usuario(id=3, nombre="Vend", email="v@x.co", rol="vendedor", activo=True),
            Registro(id=1, razon_social="ACME", nit="900000000-1", ciudad="Cali",
                     fuente="web", estado="nuevo", fecha_creacion=date(2026, 9, 1)),
        ])
        s.flush()
        s.add(Ejecucion(id=1, metodo="manual", fecha_referencia=date(2026, 10, 3),
                        ejecutado_por=1))
        s.commit()
        yield s


def test_no_permite_dos_asignaciones_vigentes(sesion):
    sesion.add(Asignacion(registro_id=1, usuario_id=3, ejecucion_id=1))
    sesion.commit()
    sesion.add(Asignacion(registro_id=1, usuario_id=3, ejecucion_id=1))
    with pytest.raises(IntegrityError):
        sesion.commit()


def test_reasignar_deja_cadena(sesion):
    a1 = Asignacion(registro_id=1, usuario_id=3, ejecucion_id=1)
    sesion.add(a1)
    sesion.commit()
    a1.vigente = False
    sesion.add(Asignacion(registro_id=1, usuario_id=1, ejecucion_id=1,
                          reemplaza_a_id=a1.id))
    sesion.commit()
    assert sesion.query(Asignacion).filter_by(registro_id=1).count() == 2


def test_fk_activadas(sesion):
    sesion.add(Asignacion(registro_id=999, usuario_id=3, ejecucion_id=1))
    with pytest.raises(IntegrityError):
        sesion.commit()