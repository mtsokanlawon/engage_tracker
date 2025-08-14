

import tempfile
import os
import gc
from faster_whisper import WhisperModel
from datetime import datetime

class AudioProcessor:
    def __init__(self, model_name="models/tiny", device="cpu"):
        self.model_name = model_name
        self.device = device

    def transcribe_bytes(self, audio_bytes):
        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = tmp.name
            tmp.write(audio_bytes)

        try:
            # Load model only for this transcription
            model = WhisperModel(self.model_name, device=self.device, compute_type="int8")
            segments, _ = model.transcribe(tmp_path)

            # Format results
            results = []
            for seg in segments:
                ts = datetime.now().strftime("%H:%M:%S")
                results.append((ts, seg.text.strip()))

            return results

        finally:
            # Cleanup
            try:
                os.remove(tmp_path)
            except:
                pass
            # Free model memory
            del model
            gc.collect()
