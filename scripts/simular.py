"""Compara los tres métodos sobre los datos limpios, sin escribir nada en la base."""
from collections import Counter
from datetime import date

from app import carga
from app.motor import METODOS, Parametros, planificar

HOY = date(2026, 10, 3)


def main():
    d = carga.cargar_todo()
    ci = carga.carga_desde_actividad(d["registros"], d["actividad"])
    regs = {r["id"]: r for r in d["registros"]}
    usrs = {u["id"]: u for u in d["usuarios"]}
    print("carga inicial:", dict(sorted(ci.items())))

    for metodo in METODOS:
        plan = planificar(d["registros"], d["usuarios"], d["ausencias"], ci,
                          Parametros(metodo=metodo, fecha_referencia=HOY))
        nuevos = Counter(a["usuario_id"] for a in plan.asignaciones)
        acierto = sum(usrs[a["usuario_id"]]["segmento_experto"] == regs[a["registro_id"]]["segmento"]
                      for a in plan.asignaciones)
        print(f"\n== {metodo}")
        print(f"asignados: {len(plan.asignaciones)} | sin asignar: {len(plan.no_asignados)}")
        print("nuevos por vendedor:", dict(sorted(nuevos.items())))
        print(f"segmento coincide: {acierto}/{len(plan.asignaciones)}")
        if metodo == "scoring":
            for n in plan.no_asignados:
                print(f"  sin asignar #{n['registro_id']}: {n['motivo']}")
            print("\nEjemplo de explicación:")
            print(" ", plan.asignaciones[0]["explicacion"]["resumen"])


if __name__ == "__main__":
    main()