import io
import os
import numpy as np
import soundfile as sf
import librosa
from datetime import timedelta
from faster_whisper import WhisperModel

class AudioProcessor:
    def __init__(self, model_name="base", device="cpu"):
        self.model_name = model_name
        self.device = device
        self.model = None  # Lazy load

    def _load_model(self):
        if self.model is None:
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type="int8"  # Lighter for Render
            )

    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS.mmm format."""
        td = timedelta(seconds=seconds)
        return str(td)

    def transcribe_bytes(self, audio_bytes: bytes):
        self._load_model()

        # Read from memory buffer
        audio_data, sample_rate = sf.read(io.BytesIO(audio_bytes))

        # Convert stereo to mono
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1)

        # Resample to 16kHz
        if sample_rate != 16000:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000

        # Transcribe
        segments, _ = self.model.transcribe(audio_data, sample_rate=sample_rate)

        # Build results with proper segment timestamps
        results = []
        for seg in segments:
            results.append({
                "start": self._format_timestamp(seg.start),
                "end": self._format_timestamp(seg.end),
                "text": seg.text.strip()
            })

        return results
