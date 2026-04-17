from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Build engine kwargs based on database type
_is_sqlite = "sqlite" in settings.DATABASE_URL

if _is_sqlite:
    _engine_kwargs = {
        "connect_args": {"check_same_thread": False},
    }
else:
    # Production database: connection pooling for PostgreSQL / MySQL
    _engine_kwargs = {
        "pool_size": 20,
        "max_overflow": 40,
        "pool_pre_ping": True,       # Detect stale connections
        "pool_recycle": 3600,         # Recycle connections every hour
    }

# Create database engine
engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

# SQLite: enforce foreign key constraints (disabled by default)
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
