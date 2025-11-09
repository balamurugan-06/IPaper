import fitz
from tqdm import tqdm
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from textwrap import wrap
import os

# ========== CONFIG ==========

OPENAI_API_KEY = os.getenv("GEN_AI_KEY")
MODEL_NAME = "gpt-4o-mini"
CHUNK_SIZE = 6000
# ============================

client = OpenAI(api_key=OPENAI_API_KEY)
def save_summary_to_pdf(summary_text, output_path="summary.pdf"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin
    c.setFont("Helvetica", 11)

    for line in summary_text.split("\n"):
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - margin
        c.drawString(margin, y, line)
        y -= 14

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
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]

def determine_summary_length(num_pages, word_count):
    if num_pages <= 20 or word_count <= 5000:
        return "Write a summary of about 300–500 words."
    elif num_pages <= 60 or word_count <= 20000:
        return "Write a summary of about 600–900 words."
    elif num_pages <= 240 or word_count <= 80000:
        return "Write a summary of about 900–1,200 words."
    else:
        return "Write a summary of about 1,200–1,800 words."

def summarize_chunk(chunk,fePrompt):
    final = f"""
{fePrompt}

Summarize the following text clearly and concisely.

### Chunk Summary Format:
**Key Ideas:**
- Explain main concepts
- Avoid unnecessary detail
- No repetition

Text:
{chunk}
"""
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
    fePrompt = promptFromFE + " " + summary_instruction

    for i, chunk in enumerate(tqdm(chunks, desc="Summarizing chunks")):
        try:
            summary = summarize_chunk(chunk, fePrompt)
            summaries.append(summary)
        except Exception as e:
            print(f"⚠️ Error summarizing chunk {i+1}: {e}")

    combined_summary_text = "\n\n".join(summaries)
    print("\nGenerating final summary...")

    final_prompt = f"""
You are to create a final structured summary using the format below. Do not repeat or duplicate sentences from the partial summaries.

**Introduction**
Write 2–4 sentences describing the purpose and context of the document.

**Key Themes / Core Arguments**
Summarize the major ideas using bullet points:
- Keep each point short
- Avoid repetition
- Focus on meaning, not wording from the text

**Method / Approach (If Applicable)**
Use bullet points to describe any methodology or approach:
- If there is no methodology, simply omit this section

**Findings / Insights**
Summarize the main findings using bullet points:
- Prioritize clarity and accuracy

**Conclusion**
Write 2–4 sentences summarizing the significance and final takeaway.

**Style Rules:**
- Headings must be **bold**
- Sub-points must be in bullet points
- Keep sentences clear, short, and organized
- Avoid long paragraphs

### Target Length:
{summary_instruction}

---
Below are the partial chunk summaries to merge and rewrite cohesively:
{combined_summary_text}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()


def summarizer(pdfPath, promptFromFE,docId):
    pdf_path = pdfPath.strip()
    print("\nExtracting text from PDF...")
    text, num_pages = extract_text_from_pdf(pdf_path)
    print(f"\n✅ Extracted {len(text)} characters from {num_pages} pages.")

    print("\nSummarizing document... (this may take several minutes for long PDFs)")
    summary = summarize_document(text, num_pages, promptFromFE)

    output_pdf = f"uploads/summary_{docId}.pdf"
    save_summary_to_pdf(summary, output_pdf)
    return summary
