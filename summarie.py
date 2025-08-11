import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.tokenize import RegexpTokenizer
from transformers import pipeline
import soundfile as sf
from faster_whisper import WhisperModel

# --- Helper functions ---
tokenizer = RegexpTokenizer(r"\w+")

def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text.strip())

def fit_vectorizer(cleaned_text):
    vectorizer = TfidfVectorizer()
    vectorizer.fit(cleaned_text)
    return vectorizer

def is_valid_sentence(sent):
    return (
        4 < len(sent.split()) < 40 and
        not re.search(r"@|/Enron|Corp/Enron|Enron@|[A-Za-z]+/[A-Za-z]+", sent)
    )

def summarize_email(text, vectorizer, top_n=3):
    if not text or not isinstance(text, str):
        return ""

    vocab = vectorizer.vocabulary_
    sentences = split_sentences(text)
    sentences = [s for s in sentences if is_valid_sentence(s)]

    if not sentences:
        return ""

    sentence_scores = []
    for sentence in sentences:
        words = tokenizer.tokenize(sentence.lower())
        words = [w for w in words if w in vocab]
        score = np.mean([vectorizer.idf_[vocab[w]] for w in words]) if words else 0
        sentence_scores.append(score)

    ranked_sentences = [s for _, s in sorted(zip(sentence_scores, sentences), reverse=True)]
    return " ".join(ranked_sentences[:top_n])

summarizer = pipeline("summarization", model="Falconsai/text_summarization")

def summarize_abstractive(text):
    if not isinstance(text, str) or len(text.strip()) < 30:
        return ""
    
    input_len = len(text.strip().split())
    # Dynamic max length between 50 and 200 tokens, ~65% of input length
    adjusted_max = int(input_len * 0.65)
    adjusted_max = max(50, min(adjusted_max, 200))

    try:
        return summarizer(text, max_length=adjusted_max, min_length=15, do_sample=False)[0]["summary_text"]
    except Exception as e:
        return f"[ERROR: {e}]"



# --- Load and transcribe audio ---
def transcribe_audio_file(file_path):
    model_size = "base"
    model = WhisperModel(model_size, device="cpu", compute_type="float32")

    audio, sr = sf.read(file_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # convert to mono if stereo

    segments, _ = model.transcribe(audio, beam_size=1)
    return " ".join([seg.text for seg in segments])

# --- Main flow ---
if __name__ == "__main__":
    audio_file = "test_audio.wav"  # Your test audio wav file

    print("Transcribing audio...")
    transcript = transcribe_audio_file(audio_file)
    print("Transcript:")
    print(transcript)

    print("\nFitting vectorizer and generating extractive summary...")
    vectorizer = fit_vectorizer(split_sentences(transcript))
    extractive_summary = summarize_email(transcript, vectorizer, top_n=3)
    print("Extractive Summary:")
    print(extractive_summary)

    print("\nGenerating abstractive summary...")
    abstractive_summary = summarize_abstractive(transcript)
    print("Abstractive Summary:")
    print(abstractive_summary)

