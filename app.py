from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pydub import AudioSegment
import asyncio, time, base64, io
import traceback

from detection.video_processor import VideoProcessor
from detection.audio_processor import AudioProcessor
from services.db_sqlalchemy import EngagementMetric, AudioTranscript, get_db
from fpdf import FPDF

from typing import Dict

# =========================
# App Setup
# =========================
app = FastAPI(title="EngageTrack API")

# Enable CORS globally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can restrict later
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# State
video_processors: Dict[str, VideoProcessor] = {}
last_active: Dict[str, float] = {}
processors_lock = asyncio.Lock()
PROCESSOR_IDLE_TIMEOUT = 60
cleanup_task = None

try:
    audio_proc = AudioProcessor()
except Exception as e:
    audio_proc = None
    print(f"Warning: Audio processor not initialized: {e}")

# =========================
# Helper Pydantic for Frame body
# =========================
class FrameBody(BaseModel):
    frame: str

# =========================
# Startup / Shutdown
# =========================
@app.on_event("startup")
async def start_cleanup_task():
    global cleanup_task
    cleanup_task = asyncio.create_task(_cleanup_inactive_processors_loop())
    print("Cleanup task started.")

@app.on_event("shutdown")
async def shutdown_cleanup_task():
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    async with processors_lock:
        for pid, proc in list(video_processors.items()):
            try:
                proc.close()
            except Exception:
                pass
            video_processors.pop(pid, None)
            last_active.pop(pid, None)
    print("Shutdown complete: processors closed.")

async def _cleanup_inactive_processors_loop():
    try:
        while True:
            now = time.time()
            async with processors_lock:
                inactive = [pid for pid, ts in last_active.items()
                            if now - ts > PROCESSOR_IDLE_TIMEOUT]
                for pid in inactive:
                    proc = video_processors.pop(pid, None)
                    last_active.pop(pid, None)
                    if proc:
                        try:
                            proc.close()
                        except Exception:
                            pass
                        print(f"Evicted processor for participant {pid}.")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        return

# =========================
# Endpoints
# =========================
@app.get("/health")
async def health():
    return {"status": "running"}

@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...), 
                        meeting_id: str = Query(...),
                        participant_id: str = Query(...),
                        db: Session = Depends(get_db)):
    contents = await file.read()
    proc = VideoProcessor()
    try:
        result = await asyncio.to_thread(proc.process_frame_bytes, contents)
        metric = EngagementMetric(
            meeting_id=meeting_id,
            participant_id=participant_id,
            attention_instant=result["attention_instant"],
            fatigue_instant=result["fatigue_instant"],
            hand_instant=result["hand_instant"],
            events_logged=result["events_logged"]
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)  # ensure it's written
        print(f"✅ Saved metric: {metric.id}, meeting_id={metric.meeting_id}")
    finally:
        try:
            proc.close()
        except Exception:
            pass
    return JSONResponse(result)

@app.post("/analyze_audio")
async def analyze_audio(
    file: UploadFile = File(...),
    meeting_id: str = Query(...),
    participant_id: str = Query(...),
    db: Session = Depends(get_db)):
    if audio_proc is None:
        raise HTTPException(status_code=503, detail="Audio processor not available")
    # contents = await file.read()
    contents = await file.read()
    result = None
    try:
        # Convert WebM/Opus → WAV in-memory
        audio = AudioSegment.from_file(io.BytesIO(contents))
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_bytes = wav_io.getvalue()
        
        result = await asyncio.to_thread(audio_proc.transcribe_bytes, wav_bytes)
    # try:
        # result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)
        transcript = AudioTranscript(
            meeting_id=meeting_id,
            participant_id=participant_id,
            transcript=" ".join([r["text"] for r in result]),
            raw_events=result
        )
        db.add(transcript)
        db.commit()
        db.refresh(transcript)  # ensure it's written
        print(f"✅ Saved metric: {transcript.id}, meeting_id={transcript.meeting_id}")
    except Exception as e:
        traceback.print_exc()  # logs full stack trace
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"transcriptions": result}

@app.post("/webhook/frames")
async def webhook_frames(
    body: FrameBody,
    meeting_id: str = Query(...),
    participant_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Receives: { "frame": "data:image/jpeg;base64,..." }
    """
    # Decode base64
    try:
        base64_str = body.frame.split(",", 1)[1]
        frame_bytes = base64.b64decode(base64_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid frame data")

    # Create or reuse VideoProcessor
    proc = video_processors.get(participant_id)
    if proc is None:
        proc = VideoProcessor()
        video_processors[participant_id] = proc

    # Process & store engagement metric
    try:
        result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)
        metric = EngagementMetric(
            meeting_id=meeting_id,
            participant_id=participant_id,
            attention_instant=result["attention_instant"],
            fatigue_instant=result["fatigue_instant"],
            hand_instant=result["hand_instant"],
            events_logged=result["events_logged"]
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)  # ensure it's written
        print(f"✅ Saved metric: {metric.id}, meeting_id={metric.meeting_id}")
        
        rows = db.query(EngagementMetric).all()
        print(f"Total EngagementMetric rows in DB: {len(rows)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
        
    finally:
        return {"status": "received", "analysis": result}
    

@app.get("/meetings/{meeting_id}/summary/pdf")
def get_meeting_summary_pdf(meeting_id: str, db: Session = Depends(get_db)):
    metrics = db.query(EngagementMetric).filter_by(meeting_id=meeting_id).all()
    transcripts = db.query(AudioTranscript).filter_by(meeting_id=meeting_id).all()

    # Aggregate engagement data
    total_events = len(metrics)
    focused_count = sum(1 for m in metrics if m.attention_instant == "Focused")
    distracted_count = total_events - focused_count
    fatigue_count = sum(1 for m in metrics if "Fatigue" in m.fatigue_instant)
    hand_raises = sum(1 for m in metrics if m.hand_instant == "Hand Raised")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Meeting Summary - {meeting_id}", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Total frames: {total_events}", ln=True)

    # Avoid division by zero
    if total_events > 0:
        pdf.cell(0, 8, f"Focused: {focused_count} ({focused_count/total_events:.1%})", ln=True)
        pdf.cell(0, 8, f"Distracted: {distracted_count} ({distracted_count/total_events:.1%})", ln=True)
    else:
        pdf.cell(0, 8, f"Focused: {focused_count} (0%)", ln=True)
        pdf.cell(0, 8, f"Distracted: {distracted_count} (0%)", ln=True)

    pdf.cell(0, 8, f"Fatigue events: {fatigue_count}", ln=True)
    pdf.cell(0, 8, f"Hand raises: {hand_raises}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Transcript:", ln=True)
    pdf.set_font("Arial", "", 11)

    for t in transcripts:
        pdf.multi_cell(0, 8, f"[{t.participant_id}] {t.transcript}")

    filename = f"/tmp/{meeting_id}_summary.pdf"
    pdf.output(filename)

    return FileResponse(filename, media_type="application/pdf", filename=f"{meeting_id}_summary.pdf")

@app.get("/debug/metrics/{meeting_id}")
def get_meeting_metrics(meeting_id: str, db: Session = Depends(get_db)):
    metrics = db.query(EngagementMetric).filter_by(meeting_id=meeting_id).all()

    if not metrics:
        return {"meeting_id": meeting_id, "frames": 0, "metrics": []}

    results = []
    for m in metrics:
        results.append({
            "id": str(m.id),
            "participant_id": m.participant_id,
            "attention_instant": m.attention_instant,
            "fatigue_instant": m.fatigue_instant,
            "hand_instant": m.hand_instant,
            "events_logged": m.events_logged,
            "created_at": m.created_at.isoformat() if hasattr(m, "created_at") else None
        })

    return {
        "meeting_id": meeting_id,
        "frames": len(results),
        "metrics": results
    }


