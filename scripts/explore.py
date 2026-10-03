import pandas as pd
from pathlib import Path

RAW = Path("data/raw")
nombres = ["usuarios", "equipos", "registros", "ausencias", "actividad"]
# dtype=str: así pandas no convierte nada y ves los datos tal como vienen
tablas = {n: pd.read_csv(RAW / f"{n}.csv", dtype=str) for n in nombres}

for nombre, df in tablas.items():
    print(f"\n===== {nombre} ({len(df)} filas) =====")
    print(df.head(3).to_string())
    print("\nNulos por columna:")
    print(df.isna().sum()[lambda s: s > 0].to_string())

r = tablas["registros"]
for col in ["zona", "estado", "fuente"]:
    print(f"\n--- valores de {col} ---")
    print(r[col].value_counts(dropna=False).to_string())

print("\n--- NIT repetidos ---")
cols = ["id", "razon_social", "nit", "estado"]
print(r[r.nit.duplicated(keep=False)].sort_values("nit")[cols].to_string())

print("\n--- notas ---")
print(r.notas.value_counts().to_string())