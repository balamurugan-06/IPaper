import fitz
from tqdm import tqdm
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from textwrap import wrap
import os
import re

# ========== CONFIG ==========
OPENAI_API_KEY = os.getenv("GEN_AI_KEY")
MODEL_NAME = "gpt-4o-mini"
CHUNK_SIZE = 6000
# ============================

client = OpenAI(api_key=OPENAI_API_KEY)

def save_summary_to_pdf(summary_text, output_path="summary.pdf"):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    margin = 40
    y_position = height - margin
    c.setFont("Helvetica", 11)
    
    # Preserve line breaks from the original text
    lines = []
    for paragraph in summary_text.split('\n\n'):
        if paragraph.strip():
            wrapped_lines = wrap(paragraph, 90)
            lines.extend(wrapped_lines)
            lines.append('')  # Add empty line between paragraphs
    
    for line in lines:
        if line == '':  # Empty line for paragraph spacing
            y_position -= 8
            continue
            
        if y_position < margin:
            c.showPage()
            c.setFont("Helvetica", 11)
            y_position = height - margin

        c.drawString(margin, y_position, line)
        y_position -= 14

    c.save()
    return output_path

def extract_text_from_pdf(pdf_path):
    text = ""
    with fitz.open(pdf_path) as pdf:
        num_pages = len(pdf)
        for i, page in enumerate(pdf, start=1):
            text += page.get_text()
    return text, num_pages

def split_text_into_chunks(text, max_length=4000):
    # Split at paragraph boundaries when possible
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 <= max_length:
            current_chunk += paragraph + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def determine_summary_length(num_pages, word_count):
    if num_pages <= 20 or word_count <= 5000:
        return "Write a summary of about 300–500 words. PRESERVE the original formatting, line breaks, and paragraph structure."
    elif num_pages <= 60 or word_count <= 20000:
        return "Write a summary of about 600–900 words. PRESERVE the original formatting, line breaks, and paragraph structure."
    elif num_pages <= 240 or word_count <= 80000:
        return "Write a summary of about 900–1,200 words. PRESERVE the original formatting, line breaks, and paragraph structure."
    else:
        return "Write a summary of about 1,200–1,800 words. PRESERVE the original formatting, line breaks, and paragraph structure."

def summarize_chunk(chunk, fePrompt):
    # Enhanced prompt to preserve formatting
    formatting_instruction = """
CRITICAL FORMATTING INSTRUCTIONS:
- PRESERVE all line breaks and paragraph breaks
- Use **bold** for section headers and important terms
- Use bullet points with • for lists
- Use --- for section dividers
- Maintain proper spacing between sections
- Keep emojis and labels properly spaced
- DO NOT collapse everything into one paragraph
- Structure the summary with clear sections and subsections
"""
    
    final = f"{fePrompt}\n\n{formatting_instruction}\n\nText to summarize:\n{chunk}"
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": final}],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def summarize_document(text, num_pages, promptFromFE):
    chunks = split_text_into_chunks(text, CHUNK_SIZE)
    summaries = []
    word_count = len(text.split())
    summary_instruction = determine_summary_length(num_pages, word_count)
    
    # Enhanced prompt with formatting instructions
    fePrompt = promptFromFE + summary_instruction + """
    
FORMATTING REQUIREMENTS:
- Keep all original line breaks and paragraph structure
- Use markdown-style formatting: **bold** for headers, • for bullets, --- for dividers
- Maintain proper spacing between sections
- Do not collapse multiple paragraphs into one
- Preserve list structures with proper bullet points
- Ensure emojis and labels have proper spacing
"""

    for i, chunk in enumerate(tqdm(chunks, desc="Summarizing chunks")):
        try:
            summary = summarize_chunk(chunk, fePrompt)
            summaries.append(summary)
        except Exception as e:
            print(f"⚠️ Error summarizing chunk {i+1}: {e}")

    combined_summary_text = "\n\n".join(summaries)  # Use double newline to preserve structure
    print("\nGenerating final summary...")

    final_prompt = (
        f"{fePrompt}\n\n"
        f"Here are multiple partial summaries of a document. Combine them into a single, well-structured summary:\n\n"
        f"IMPORTANT: PRESERVE ALL FORMATTING, LINE BREAKS, AND STRUCTURE from the partial summaries below.\n"
        f"Keep sections, bullet points, bold headers, and dividers exactly as they appear.\n"
        f"Do not collapse paragraphs or remove line breaks.\n\n"
        f"Partial summaries:\n{combined_summary_text}"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()

def summarizer(pdfPath, promptFromFE, docId):
    pdf_path = pdfPath.strip()
    print("\nExtracting text from PDF...")
    text, num_pages = extract_text_from_pdf(pdf_path)
    print(f"\n✅ Extracted {len(text)} characters from {num_pages} pages.")

    print("\nSummarizing document... (this may take several minutes for long PDFs)")
    summary = summarize_document(text, num_pages, promptFromFE)

    output_pdf = f"uploads/summary_{docId}.pdf"
    save_summary_to_pdf(summary, output_pdf)
    return summary
