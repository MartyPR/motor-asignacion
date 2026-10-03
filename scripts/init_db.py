from sqlalchemy import inspect

from app.db import DB_PATH, engine
from app.models import Base


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    for tabla in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns(tabla)]
        print(f"{tabla}: {', '.join(cols)}")


if __name__ == "__main__":
    main()