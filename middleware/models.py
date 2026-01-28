from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
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
    duration_seconds = Column(Float, nullable=True)  # Audio duration in seconds
    status = Column(String(20), nullable=False, default='assigned')  # assigned, completed, skipped
    transcription_length = Column(Integer, nullable=True)  # Length of transcription text
    skip_reason = Column(Text, nullable=True)  # Reason for skipping if applicable

    def __repr__(self):
        return f"<TranscriptionSession(agent_id={self.agent_id}, task_id={self.task_id}, status='{self.status}')>"

class AgentStats(Base):
    """Model for tracking cumulative agent statistics"""
    __tablename__ = 'agent_stats'

    agent_id = Column(Integer, primary_key=True)
    total_duration_seconds = Column(Float, nullable=False, default=0.0)
    total_tasks_completed = Column(Integer, nullable=False, default=0)
    total_tasks_skipped = Column(Integer, nullable=False, default=0)
    total_earnings = Column(Float, nullable=False, default=0.0)  # Can be calculated from duration
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AgentStats(agent_id={self.agent_id}, completed={self.total_tasks_completed}, duration={self.total_duration_seconds})>"

# Database configuration
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER', 'labelstudio')}:{os.getenv('POSTGRES_PASSWORD')}@localhost:5432/{os.getenv('POSTGRES_DB', 'labelstudio')}"

# Create engine and session factory
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")

def test_connection():
    """Test database connection"""
    try:
        engine.connect()
        print("✅ PostgreSQL database connection successful")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL database connection failed: {e}")
        return False

if __name__ == "__main__":
    # Test connection and create tables
    if test_connection():
        create_tables()