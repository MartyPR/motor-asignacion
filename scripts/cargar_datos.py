from app import carga
from app.db import SessionLocal

from scripts.init_db import main as reiniciar_bd
from app.semilla import sembrar

def main():
    reiniciar_bd()
    datos = carga.cargar_todo()

    with SessionLocal() as s:
        sembrar(s, datos)

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