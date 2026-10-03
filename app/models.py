from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, ForeignKey, Index, JSON, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def ahora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------- Datos de la operación (vienen de los CSV) ----------

class Equipo(Base):
    __tablename__ = "equipos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    lider_id: Mapped[int | None]  # sin FK a propósito: haría un ciclo con usuarios
    zona: Mapped[str]


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    email: Mapped[str]
    rol: Mapped[str]
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id"))
    zona: Mapped[str | None]
    segmento_experto: Mapped[str | None]
    capacidad_maxima: Mapped[int | None]
    fecha_ingreso: Mapped[date | None]
    activo: Mapped[bool]
    calidad: Mapped[list] = mapped_column(JSON, default=list)


class Registro(Base):
    __tablename__ = "registros"
    id: Mapped[int] = mapped_column(primary_key=True)
    razon_social: Mapped[str]
    nit: Mapped[str]
    sector: Mapped[str | None]
    empleados: Mapped[int | None]
    ingresos_estimados: Mapped[int | None] = mapped_column(BigInteger)
    ciudad: Mapped[str]
    zona: Mapped[str | None]            # normalizada
    zona_original: Mapped[str | None]   # como venía en el CSV
    fuente: Mapped[str]
    notas: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str]
    fecha_creacion: Mapped[date]
    segmento: Mapped[str | None]        # derivado (Paso 3)
    duplicado_de_id: Mapped[int | None] = mapped_column(ForeignKey("registros.id"))
    calidad: Mapped[list] = mapped_column(JSON, default=list)


class Ausencia(Base):
    __tablename__ = "ausencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    desde: Mapped[date]
    hasta: Mapped[date | None]  # None = indefinida
    motivo: Mapped[str]


class Actividad(Base):
    __tablename__ = "actividad"
    id: Mapped[int] = mapped_column(primary_key=True)
    registro_id: Mapped[int] = mapped_column(ForeignKey("registros.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str]
    fecha: Mapped[date]

class Ejecucion(Base):
    """Un clic en 'Ejecutar' (o una reasignación manual)."""
    __tablename__ = "ejecuciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    metodo: Mapped[str]
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)
    fecha_referencia: Mapped[date]
    ejecutado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(default=ahora)
    no_asignados: Mapped[list] = mapped_column(JSON, default=list)


class Asignacion(Base):
    __tablename__ = "asignaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    registro_id: Mapped[int] = mapped_column(ForeignKey("registros.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecuciones.id"))
    reemplaza_a_id: Mapped[int | None] = mapped_column(ForeignKey("asignaciones.id"))
    vigente: Mapped[bool] = mapped_column(default=True)
    explicacion: Mapped[dict] = mapped_column(JSON, default=dict)
    motivo: Mapped[str | None] = mapped_column(Text) 
    creado_en: Mapped[datetime] = mapped_column(default=ahora)

    __table_args__ = (
        Index("ix_asignaciones_registro", "registro_id"),
        # Un solo dueño vigente por registro, garantizado por la base:
        Index("uq_asignacion_vigente", "registro_id", unique=True,
              sqlite_where=text("vigente = 1")),
    )


class LlamadaIA(Base):
    """Auditoría de cada llamada al modelo: prompt completo, respuesta, costo."""
    __tablename__ = "llamadas_ia"
    id: Mapped[int] = mapped_column(primary_key=True)
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecuciones.id"))
    registro_id: Mapped[int | None] = mapped_column(ForeignKey("registros.id"))
    modelo: Mapped[str]
    prompt_sistema: Mapped[str] = mapped_column(Text)
    prompt_usuario: Mapped[str] = mapped_column(Text)  # incluye los datos del registro
    respuesta_cruda: Mapped[str | None] = mapped_column(Text)
    respuesta_valida: Mapped[bool | None]
    error: Mapped[str | None] = mapped_column(Text)
    tokens_entrada: Mapped[int | None]
    tokens_salida: Mapped[int | None]
    latencia_ms: Mapped[int | None]
    costo_usd: Mapped[float | None]
    creado_en: Mapped[datetime] = mapped_column(default=ahora)