# app.py
import asyncio
import time
from typing import Dict
from datetime import datetime  # ✅ Changed: now we can use datetime.utcnow() safely

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Query,
    File,
    Depends,
    UploadFile,
    HTTPException
)
from fastapi.responses import JSONResponse

from detection.video_processor import VideoProcessor
from detection.audio_processor import AudioProcessor

from services.engagement_service import save_engagement_metrics
from services.db_writer import save_engagement, save_transcript

app = FastAPI(title="EngageTrack API (per-participant WS)")

# Shared state
video_processors: Dict[str, VideoProcessor] = {}
last_active: Dict[str, float] = {}
processors_lock = asyncio.Lock()

PROCESSOR_IDLE_TIMEOUT = 60  # seconds
cleanup_task = None

# Global Audio Processor
try:
    audio_proc = AudioProcessor()
except Exception as e:
    audio_proc = None
    print(f"Warning: Audio processor not initialized: {e}")


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
            except Exception as e:
                print(f"Error closing processor for {pid}: {e}")
            finally:
                video_processors.pop(pid, None)
                last_active.pop(pid, None)
    print("Shutdown complete: processors closed.")


async def _cleanup_inactive_processors_loop():
    try:
        while True:
            now = time.time()
            evict = []
            async with processors_lock:
                for pid, ts in list(last_active.items()):
                    if now - ts > PROCESSOR_IDLE_TIMEOUT:
                        evict.append(pid)

                for pid in evict:
                    proc = video_processors.pop(pid, None)
                    last_active.pop(pid, None)
                    if proc:
                        try:
                            proc.close()
                        except Exception as e:
                            print(f"Error closing processor for {pid}: {e}")
                        print(f"Evicted processor for participant {pid} due to inactivity.")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        return


@app.get("/health")
async def health():
    return {"status": "running"}


@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...)):
    contents = await file.read()
    proc = VideoProcessor()
    try:
        result = await asyncio.to_thread(proc.process_frame_bytes, contents)
    finally:
        try:
            proc.close()
        except Exception as e:
            print(f"Error closing temp VideoProcessor: {e}")
    return JSONResponse(result)


@app.post("/analyze_audio")
async def analyze_audio(
    file: UploadFile = File(...),
    meeting_id: str = Query(...),
    participant_id: str = Query(...)
):
    if audio_proc is None:
        raise HTTPException(status_code=503, detail="Audio processor not available")

    contents = await file.read()
    try:
        result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)

        transcript_text = " ".join(
            seg["text"] if isinstance(seg, dict) and "text" in seg else str(seg)
            for seg in result
        )

        await save_transcript({
            "meeting_id": meeting_id,
            "participant_id": participant_id,
            "transcript_text": transcript_text
        })

        return JSONResponse({"transcriptions": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_db_writer():
    return save_engagement


@app.websocket("/ws/frames")
async def websocket_frames(
    websocket: WebSocket,
    meeting_id: str = Query(...),
    participant_id: str = Query(...),
    db_writer=Depends(get_db_writer)
):
    await websocket.accept()
    proc = None

    try:
        async with processors_lock:
            proc = video_processors.get(participant_id)
            if proc is None:
                proc = VideoProcessor()
                video_processors[participant_id] = proc
            last_active[participant_id] = time.time()

        while True:
            frame_bytes = await websocket.receive_bytes()

            async with processors_lock:
                last_active[participant_id] = time.time()

            try:
                # ✅ Added lock around processing to avoid race conditions on same processor
                async with processors_lock:
                    result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)

                await save_engagement_metrics(db_writer, meeting_id, participant_id, result)
            except Exception as e:
                await websocket.send_json({"error": str(e)})
                continue

            result_with_meta = {"participant_id": participant_id, "analysis": result}
            await websocket.send_json(result_with_meta)

    except WebSocketDisconnect:
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
        print(f"WS disconnected: {participant_id}")
    except Exception as e:
        print(f"WS error for participant {participant_id}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
