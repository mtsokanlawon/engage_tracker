# services/db_sqlalchemy.py

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./engagement.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

Base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Table: Engagement Metrics
class EngagementMetric(Base):
    __tablename__ = "engagement_metrics"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    participant_id = Column(String, index=True)
    metric_type = Column(String)
    metric_value = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Table: Audio Transcripts
class AudioTranscript(Base):
    __tablename__ = "audio_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(String, index=True)
    participant_id = Column(String, index=True)
    transcript_text = Column(Text)
    start_time = Column(Float)  # optional, in seconds
    end_time = Column(Float)    # optional, in seconds
    timestamp = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# Save engagement metrics
def save_engagement_sqlalchemy(meeting_id: str, participant_id: str, metrics: dict):
    db = SessionLocal()
    try:
        for metric_name, value in metrics.items():
            record = EngagementMetric(
                meeting_id=meeting_id,
                participant_id=participant_id,
                metric_type=metric_name,
                metric_value=float(value)
            )
            db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


# Save audio transcript
def save_transcript_sqlalchemy(meeting_id: str, participant_id: str, transcript_text: str,
                               start_time: float = None, end_time: float = None):
    db = SessionLocal()
    try:
        record = AudioTranscript(
            meeting_id=meeting_id,
            participant_id=participant_id,
            transcript_text=transcript_text,
            start_time=start_time,
            end_time=end_time
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

