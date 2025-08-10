# engagement_service.py
from datetime import datetime  # ✅ Correct import

async def save_engagement_metrics(db_writer, meeting_id, participant_id, result):
    """
    Save engagement metrics after processing a video frame.

    db_writer: async callable for saving to DB
    result: dict from VideoProcessor.process_frame_bytes
    """

    data = {
        "meeting_id": meeting_id,
        "participant_id": participant_id,
        "timestamp": datetime.utcnow(),  # ✅ Now works correctly
        "attention_instant": result.get("attention_instant"),
        "fatigue_instant": result.get("fatigue_instant"),
        "hand_instant": result.get("hand_instant"),
        "events_logged": result.get("events_logged", [])
    }

    try:
        await db_writer(data)
    except Exception as e:
        print(f"Error saving engagement metrics for {participant_id}: {e}")
