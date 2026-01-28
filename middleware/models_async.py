from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, text
from sqlalchemy.orm import declarative_base
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

Base = declarative_base()

class TranscriptionSession(Base):
    """Model for tracking individual transcription sessions"""
    __tablename__ = 'transcription_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default='assigned')
    transcription_length = Column(Integer, nullable=True)
    skip_reason = Column(Text, nullable=True)

    def __repr__(self):
        return f"<TranscriptionSession(agent_id={self.agent_id}, task_id={self.task_id}, status='{self.status}')>"

class AgentStats(Base):
    """Model for tracking cumulative agent statistics"""
    __tablename__ = 'agent_stats'

    agent_id = Column(Integer, primary_key=True)
    total_duration_seconds = Column(Float, nullable=False, default=0.0)
    total_tasks_completed = Column(Integer, nullable=False, default=0)
    total_tasks_skipped = Column(Integer, nullable=False, default=0)
    total_earnings = Column(Float, nullable=False, default=0.0)
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AgentStats(agent_id={self.agent_id}, completed={self.total_tasks_completed}, duration={self.total_duration_seconds})>"

# Async database configuration
DATABASE_URL = f"postgresql+asyncpg://{os.getenv('POSTGRES_USER', 'labelstudio')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:5432/{os.getenv('POSTGRES_DB', 'labelstudio')}"

# Create async engine and session factory
async_engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Dependency for FastAPI
async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Create tables (call this on startup)
async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def test_connection():
    """Test database connection"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False