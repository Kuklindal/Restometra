from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"}
)
SessionFactory = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionFactory() as session:
        yield session
