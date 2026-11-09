from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from brightwater.config import settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(settings().database_url.get_secret_value(), pool_pre_ping=True)


def session() -> Session:
    return sessionmaker(bind=engine(), expire_on_commit=False)()


def get_db():
    with session() as db:
        with db.begin():
            yield db
