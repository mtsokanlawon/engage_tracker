# app.py
import asyncio
import time
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, File, Depends, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from detection.video_processor import VideoProcessor
from detection.audio_processor import AudioProcessor

from services.engagement_service import save_engagement_metrics
from services.db_writer import save_engagement, save_transcript


app = FastAPI(title="EngageTrack API (per-participant WS)")

# Map participant_id -> VideoProcessor
video_processors: Dict[str, VideoProcessor] = {}
# Map participant_id -> last active timestamp (epoch seconds)
last_active: Dict[str, float] = {}
# Lock to protect shared maps
processors_lock = asyncio.Lock()

# Idle timeout (seconds) after which a participant processor will be evicted
PROCESSOR_IDLE_TIMEOUT = 60  # adjust as needed (60s default)

# Background cleanup task handle
cleanup_task = None

# Create a global audio processor if desired
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
    # Close all remaining processors
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
    """
    Periodically evict idle participants to free resources.
    """
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
                        except Exception:
                            pass
                        print(f"Evicted processor for participant {pid} due to inactivity.")
            await asyncio.sleep(10)  # check every 10 seconds
    except asyncio.CancelledError:
        # task cancelled on shutdown
        return


@app.get("/health")
async def health():
    return {"status": "running"}


@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...)):
    """
    Simple HTTP endpoint for single-frame analysis (keeps backward compatibility).
    """
    contents = await file.read()
    # Use a transient processor or a shared one (stateless). We'll use a temp VideoProcessor instance here.
    proc = VideoProcessor()
    try:
        result = await asyncio.to_thread(proc.process_frame_bytes, contents)
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

        # Save transcript asynchronously using your async writer
        await save_transcript({
            "meeting_id": meeting_id,
            "participant_id": participant_id,
            "transcript_text": transcript_text
        })

        return JSONResponse({"transcriptions": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_db_writer():
    """
    Dependency to provide the DB writer function.
    Replace with actual DB writer in production.
    """
    return save_engagement  # Use your real async DB writer


@app.websocket("/ws/frames")
async def websocket_frames(websocket: WebSocket, 
                           meeting_id: str = Query(...),
                           participant_id: str = Query(...), 
                           db_writer = Depends(get_db_writer)):
    """
    WebSocket endpoint for per-participant real-time frame analysis.

    Client should connect using:
      wss://your-service/ws/frames?participant_id=abc123

    Then send binary frames (JPEG/PNG bytes). Server returns JSON results for each frame.
    """
    await websocket.accept()
    proc = None

    try:
        # create or fetch participant processor
        async with processors_lock:
            proc = video_processors.get(participant_id)
            if proc is None:
                proc = VideoProcessor()
                video_processors[participant_id] = proc
            last_active[participant_id] = time.time()

        while True:
            # Receive binary frame bytes. If client sends text, this will raise.
            frame_bytes = await websocket.receive_bytes()

            # update last active timestamp
            async with processors_lock:
                last_active[participant_id] = time.time()

            # Offload heavy processing to thread
            try:
                result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)
                await save_engagement_metrics(db_writer, meeting_id, participant_id, result)
            except Exception as e:
                # return error object but keep the connection open
                await websocket.send_json({"error": str(e)})
                continue

            # Attach participant id (optional) and send back
            result_with_meta = {"participant_id": participant_id, "analysis": result}
            await websocket.send_json(result_with_meta)

    except WebSocketDisconnect:
        # client disconnected; mark last_active to let cleanup evict quickly
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
        print(f"WS disconnected: {participant_id}")
    except Exception as e:
        # unexpected error
        print("WS error for participant", participant_id, ":", e)
        try:
            await websocket.close()
        except Exception:
            pass
        # mark for eviction
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
