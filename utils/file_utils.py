import csv
import os
from fpdf import FPDF
from config import OUTPUT_DIR

def save_csv(filename, rows, headers):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def generate_pdf_transcript(transcriptions, out_path=None):
    if out_path is None:
        out_path = os.path.join(OUTPUT_DIR, "transcription_summary.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10, "Lecture Transcriptions\n\n")
    for ts, text in transcriptions:
        pdf.multi_cell(0, 12, f"[{ts}] {text or '(No speech detected)'}")
        pdf.ln(5)
    pdf.output(out_path)

def generate_pdf_logs(events, out_path=None):
    if out_path is None:
        out_path = os.path.join(OUTPUT_DIR, "engagement_log_summary.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 10, "Engagement Log Summary\n\n")
    for ts, etype, desc, speech in events:
        log_entry = f"[{ts}] {etype}: {desc}"
        if speech:
            log_entry += f"\n    Speech Context: \"{speech}\""
        pdf.multi_cell(0, 12, log_entry)
        pdf.ln(5)
    pdf.output(out_path)
