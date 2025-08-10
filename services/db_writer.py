# db_writer.py
import asyncio
from datetime import datetime  # ✅ For timestamp handling
from services.db_sqlalchemy import save_engagement_sqlalchemy, save_transcript_sqlalchemy

async def save_engagement(data):
    """
    Save engagement metrics to the database.

    data: dict with keys:
      - meeting_id (str)
      - participant_id (str)
      - attention_instant (str/float)
      - fatigue_instant (str/float)
      - hand_instant (str/float)
      - events_logged (list)  # currently unused here, but may be handled elsewhere
    """

    # Convert various metric formats into floats
    def convert_metric(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            val = value.lower()
            if val in ("focused", "normal", "hand detected", "hand raised"):
                return 1.0
            elif val in ("distracted", "potential fatigue", "fatigue detected", "no hand detected"):
                return 0.0
        return 0.0

    metrics = {
        "attention_instant": convert_metric(data.get("attention_instant", 0)),
        "fatigue_instant": convert_metric(data.get("fatigue_instant", 0)),
        "hand_instant": convert_metric(data.get("hand_instant", 0)),
    }

    try:
        # Blocking DB call moved to thread pool
        await asyncio.to_thread(
            save_engagement_sqlalchemy,
            data["meeting_id"],
            data["participant_id"],
            metrics,
        )
    except Exception as e:
        print(f"Error saving engagement metrics for {data.get('participant_id')}: {e}")


async def save_transcript(data):
    """
    Save audio transcript to the database.

    data: dict with keys:
      - meeting_id (str)
      - participant_id (str)
      - transcript_text (str)
      - start_time (float, optional)
      - end_time (float, optional)
    """
    try:
        await asyncio.to_thread(
            save_transcript_sqlalchemy,
            meeting_id=data["meeting_id"],
            participant_id=data["participant_id"],
            transcript_text=data.get("transcript_text", ""),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
        )
    except Exception as e:
        print(f"Error saving transcript for {data.get('participant_id')}: {e}")
