import asyncio
import websockets
import tempfile
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
import json
import time

model_size = "base"
model = WhisperModel(model_size, device="cpu", compute_type="float32")

async def transcribe_audio(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message)
            if data["type"] == "audioChunk":
                arr = np.array(data["payload"], dtype=np.uint8).tobytes()

                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmpf:
                    tmpf.write(arr)
                    tmp_path = tmpf.name

                audio, sr = sf.read(tmp_path)
                if audio.ndim > 1:
                    audio = np.mean(audio, axis=1)  # mono

                segments, _ = model.transcribe(audio, beam_size=1)
                transcript_text = " ".join([seg.text for seg in segments])

                result = {
                    "type": "transcript",
                    "speakerId": data.get("speakerId"),
                    "speakerName": data.get("speakerName", "Unknown"),
                    "text": transcript_text.strip(),
                    "ts": time.time()
                }
                await websocket.send(json.dumps(result))

        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "error": str(e)}))


async def main():
    async with websockets.serve(transcribe_audio, "0.0.0.0", 8765):
        print("Transcriber server running on ws://0.0.0.0:8765")
        await asyncio.Future()

def test_local_file(filepath):
    audio, sr = sf.read(filepath)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)  # convert to mono

    segments, _ = model.transcribe(audio, beam_size=1)
    transcript_text = " ".join([seg.text for seg in segments])
    print("\n🎙️ Transcript from local file:")
    print(transcript_text.strip())


if __name__ == "__main__":
    # To test locally, uncomment the next two lines and comment out asyncio.run(main())
    test_local_file("test_audio.wav")

    # For WebSocket server, comment the above line and uncomment below:
    # asyncio.run(main())
