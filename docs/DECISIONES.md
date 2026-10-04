
Update version 4
¿Los líderes reciben registros?
No, salvo incluir_lideres=True. El admin nunca
¿Cómo se deriva el segmento de un registro?
¿Qué pasa con un vendedor sin capacidad o con capacidad 0?
¿Qué hacemos con los duplicados y con la nota "no insistir"?
¿Cómo se infiere la zona cuando falta?

# Decisiones de limpieza de datos

| Tema | Decisión | Por qué |
|---|---|---|
| Zona | Se normaliza con un diccionario (ANT→Antioquia, Bogotá→Centro, etc.) | Son variantes de las mismas 4 zonas |
| Zona vacía en registros | Se infiere de la ciudad | Revisé los datos: ninguna ciudad aparece en dos zonas, así que la inferencia es segura |
| Zona vacía en un usuario | Se toma la zona de su equipo | El usuario 18 es del equipo 1, que es Centro |
| Equipo 99 (usuario 17) | `equipo_id` queda en `None` y se anota | No inventamos un equipo; la zona Costa sí se conserva |
| Estado "Nuevo" | Se pasa a minúscula | Son 4 filas con error de tipeo |
| Duplicados | Mismo NIT = duplicado; el más antiguo es el original | El NIT es la clave legal |
| Razón social repetida con NIT distinto | No es duplicado | Hay 19 nombres repetidos con NIT diferente; tratarlos como duplicados borraría clientes reales |
| Segmento del registro | Corporativo si tiene ≥250 empleados o ≥30.000 millones de ingresos; si no, industrial si el sector es industrial; si no, pyme | Es un supuesto mío, no viene en los datos. Las constantes están arriba del archivo para que lo cambies |
| Datos faltantes | Se dejan en `None` y se anotan | Nunca dejan a un registro sin segmento: ninguno trae empleados e ingresos vacíos a la vez |



#Decisiones de etapa motor

|Pregunta |	Decisión |
|---|---|
|Capacidad vacía o 0  |	No elegible, con motivo explícito. No inventamos una capacidad |
|"Hoy" |  fecha_referencia es un parámetro obligatorio. Define quién está ausente y queda en la traza |
|Nota |"pidió que no insistiéramos"	No se asigna solo: va a "revisión humana" (configurable) |
|Orden de reparto |	Los registros más antiguos primero, para atacar el "entró el viernes y nadie lo toca hasta el martes" |
|Zona |	Estricta por defecto (configurable) |
|Segmento |	Preferencia, no obligación (configurable) |
|Carga actual |	Se deduce de actividad |


# 1. ¿Quién está disponible hoy?
curl -s "localhost:8000/api/vendedores?fecha=2026-10-03"

# 2. Previsualizar (no escribe nada). Guarda la "huella" de la respuesta
curl -s -X POST localhost:8000/api/previsualizar \
  -H "Content-Type: application/json" \
  -d '{"metodo":"scoring","fecha_referencia":"2026-10-03"}'

# 3. Ejecutar, pasando la huella de la previsualización
curl -s -X POST localhost:8000/api/ejecutar \
  -H "Content-Type: application/json" \
  -d '{"parametros":{"metodo":"scoring","fecha_referencia":"2026-10-03"},"operador_id":1,"huella_esperada":"PEGA_AQUI_LA_HUELLA"}'

# 4. Reasignar un registro de Nicolás (el usuario inactivo) a Catalina
curl -s -X POST localhost:8000/api/reasignar \
  -H "Content-Type: application/json" \
  -d '{"registro_id":79,"usuario_id":13,"operador_id":1,"motivo":"Nicolás está inactivo","fecha_referencia":"2026-10-03"}'

# 5. Historial de ejecuciones
curl -s localhost:8000/api/ejecuciones


