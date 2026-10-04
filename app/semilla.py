from sqlalchemy.orm import Session

from app.models import Actividad, Ausencia, Equipo, Registro, Usuario


def sembrar(s: Session, datos: dict) -> None:
    registros = sorted(datos["registros"], key=lambda r: (r["duplicado_de_id"] is not None, r["id"]))

    s.add_all([Equipo(**e) for e in datos["equipos"]])
    s.add_all([Usuario(**u) for u in datos["usuarios"]])
    s.flush()
    s.add_all([Registro(**r) for r in registros])
    s.flush()
    s.add_all([Ausencia(**a) for a in datos["ausencias"]])
    s.add_all([Actividad(**a) for a in datos["actividad"]])
    s.commit()