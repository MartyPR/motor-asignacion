from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DB_PATH = Path("data/motor.db")


def crear_engine(url):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _activar_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = crear_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(engine, expire_on_commit=False)