# # backend/app/db/database.py

# """
# Database Configuration

# SQLAlchemy engine, session factory, and base class configuration.
# """

# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker, Session
# from typing import Generator

# # from app.core.config import settings
# # from app.core.logger import logger

# # ============================================================================
# # SQLAlchemy Configuration
# # ============================================================================
# from dotenv import load_dotenv
# import os

# load_dotenv()

# sqlalchemy_url = os.getenv("DATABASE_URL")
# # Create engine
# engine = create_engine(
#     sqlalchemy_url,
#     pool_pre_ping=True,  # Verify connections before using
#     pool_size=10,  # Connection pool size
#     max_overflow=20,  # Max connections beyond pool_size
#     pool_recycle=3600,  # Recycle connections after 1 hour
#     echo=False,  # Log SQL queries in debug mode
# )

# # Session factory
# SessionLocal = sessionmaker(
#     autocommit=False,
#     autoflush=False,
#     bind=engine
# )

# # Base class for models
# Base = declarative_base()

# # ============================================================================
# # Dependency Injection
# # ============================================================================

# def get_db() -> Generator[Session, None, None]:
#     """
#     FastAPI dependency for database sessions.
    
#     Usage:
#         @app.get("/items/")
#         def read_items(db: Session = Depends(get_db)):
#             return db.query(Item).all()
#     """
#     db = SessionLocal()
#     try:
#         yield db
#     except Exception as e:
#         logger.error(f"Database session error: {str(e)}")
#         db.rollback()
#         raise
#     finally:
#         db.close()

# # ============================================================================
# # Utility Functions
# # ============================================================================

# def init_db():
#     """
#     Initialize database by creating all tables.
#     Should be called on application startup (development only).
#     """
#     logger.info("Initializing database...")
#     Base.metadata.create_all(bind=engine)
#     logger.info("Database initialized successfully")

# def drop_db():
#     """
#     Drop all database tables.
#     WARNING: This is destructive! Use only in development.
#     """
#     logger.warning("Dropping all database tables...")
#     Base.metadata.drop_all(bind=engine)
#     logger.warning("All tables dropped")
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import uuid
from uuid import UUID
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
        
# ============================================================================
