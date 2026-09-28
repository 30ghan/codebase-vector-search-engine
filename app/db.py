import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Absolute path: a relative sqlite:/// URL resolves against the process working
# directory, so starting uvicorn from anywhere but the project root silently
# created a second, empty database.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(PROJECT_ROOT, "codebase_search.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


from app.models import CodeChunk

Base.metadata.create_all(bind=engine)
