from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import servicio
from app.db import SessionLocal
from app.motor import Parametros

app = FastAPI(title="Motor de asignación comercial")


def get_db():
    with SessionLocal() as s:
        yield s


@app.exception_handler(servicio.ErrorNegocio)
def manejar_error_negocio(_: Request, e: servicio.ErrorNegocio):
    return JSONResponse(status_code=e.status, content={"detalle": e.mensaje})

class ParametrosIn(BaseModel):
    metodo: Literal["round_robin", "balanceado", "scoring"]
    fecha_referencia: date
    incluir_lideres: bool = False
    zona_estricta: bool = True
    segmento_estricto: bool = False
    respetar_no_insistir: bool = True
    peso_zona: float = Field(40, ge=0)
    peso_segmento: float = Field(30, ge=0)
    peso_carga: float = Field(30, ge=0)
    peso_senior: float = Field(15, ge=0)
    tolerancia_carga: float = Field(0.10, ge=0)
    meses_senior: int = Field(12, ge=0)

    def a_motor(self) -> Parametros:
        return Parametros(**self.model_dump())


class EjecutarIn(BaseModel):
    parametros: ParametrosIn
    operador_id: int
    huella_esperada: str | None = None


class ReasignarIn(BaseModel):
    registro_id: int
    usuario_id: int
    operador_id: int
    motivo: str = Field(min_length=3)
    fecha_referencia: date | None = None


@app.get("/api/salud")
def salud():
    return {"ok": True}


@app.get("/api/pendientes")
def pendientes(s=Depends(get_db)):
    return servicio.listar_pendientes(s)


@app.get("/api/vendedores")
def vendedores(fecha: date, s=Depends(get_db)):
    return servicio.listar_vendedores(s, fecha)


@app.get("/api/operadores")
def operadores(s=Depends(get_db)):
    return servicio.listar_operadores(s)


@app.post("/api/previsualizar")
def previsualizar(body: ParametrosIn, s=Depends(get_db)):
    return servicio.previsualizar(s, body.a_motor())


@app.post("/api/ejecutar")
def ejecutar(body: EjecutarIn, s=Depends(get_db)):
    return servicio.ejecutar(s, body.parametros.a_motor(), body.operador_id, body.huella_esperada)


@app.post("/api/reasignar")
def reasignar(body: ReasignarIn, s=Depends(get_db)):
    return servicio.reasignar(s, body.registro_id, body.usuario_id, body.operador_id,
                              body.motivo, body.fecha_referencia)


@app.get("/api/ejecuciones")
def ejecuciones(s=Depends(get_db)):
    return servicio.listar_ejecuciones(s)