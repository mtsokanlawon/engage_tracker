# db_sqlalchemy.py
import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")  # Set in Render env vars

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

class EngagementMetric(Base):
    __tablename__ = "engagement_metrics"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(String, nullable=False)
    participant_id = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    attention_instant = Column(String)
    fatigue_instant = Column(String)
    hand_instant = Column(String)
    events_logged = Column(JSON)

class AudioTranscript(Base):
    __tablename__ = "audio_transcripts"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(String, nullable=False)
    participant_id = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    transcript = Column(String, nullable=False)
    raw_events = Column(JSON, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
