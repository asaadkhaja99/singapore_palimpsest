from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from backend.config import get_settings


settings = get_settings()
db_path = Path(settings.palimpsest_db_path)
if db_path.parent and str(db_path.parent) != ".":
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
