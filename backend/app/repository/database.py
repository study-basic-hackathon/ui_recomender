import logging
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    uri = settings.SQLALCHEMY_DATABASE_URI
    if not uri:
        raise ValueError("SQLALCHEMY_DATABASE_URI is not set")

    engine = create_engine(uri, pool_pre_ping=True)

    if settings.ENVIRONMENT == "development":
        logger.info("Using database at %s", uri)

    return engine


def SessionLocal() -> Session:
    engine = get_engine()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return factory()
