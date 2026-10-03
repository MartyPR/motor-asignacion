from app import carga
from app.db import SessionLocal
from app.models import Actividad, Ausencia, Equipo, Registro, Usuario
from scripts.init_db import main as reiniciar_bd


def main():
    reiniciar_bd()
    datos = carga.cargar_todo()

    datos["registros"].sort(key=lambda r: (r["duplicado_de_id"] is not None, r["id"]))

    with SessionLocal() as s:
        s.add_all([Equipo(**e) for e in datos["equipos"]])
        s.add_all([Usuario(**u) for u in datos["usuarios"]])
        s.flush()
        s.add_all([Registro(**r) for r in datos["registros"]])
        s.flush()
        s.add_all([Ausencia(**a) for a in datos["ausencias"]])
        s.add_all([Actividad(**a) for a in datos["actividad"]])
        s.commit()

    print("\n== Cargado ==")
    for tabla, filas in datos.items():
        print(f"{tabla}: {len(filas)}")

    print("\n== Arreglos de calidad ==")
    for tabla, conteo in carga.resumen_calidad(datos).items():
        print(f"{tabla}:")
        for tipo, n in conteo.items():
            print(f"  {tipo}: {n}")

    nuevos = [r for r in datos["registros"] if r["estado"] == "nuevo"]
    dups = [r for r in nuevos if r["duplicado_de_id"]]
    print(f"\nRegistros nuevos: {len(nuevos)} (duplicados entre ellos: {len(dups)})")


if __name__ == "__main__":
    main()