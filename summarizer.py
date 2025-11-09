import fitz
from tqdm import tqdm
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from textwrap import wrap
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4



# ========== CONFIG ==========

OPENAI_API_KEY = os.getenv("GEN_AI_KEY")
MODEL_NAME = "gpt-4o-mini"
CHUNK_SIZE = 6000
# ============================

client = OpenAI(api_key=OPENAI_API_KEY)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

def save_summary_to_pdf(summary_html, output_path="summary.pdf"):
    # Create the PDF document
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    bold = ParagraphStyle(
        "BoldHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        spaceBefore=14,
        spaceAfter=6
    )

    story = []
    lines = summary_html.split("\n")
    bullet_buffer = []

    for line in lines:
        line = line.strip()

        # Heading: <strong>Heading</strong>
        if line.startswith("<strong>") and line.endswith("</strong>"):
            heading_text = line.replace("<strong>", "").replace("</strong>", "")
            story.append(Paragraph(heading_text, bold))
            continue

        # Bullet Item: <li>• text</li>
        if line.startswith("<li>"):
            bullet_text = line.replace("<li>", "").replace("</li>", "")
            bullet_buffer.append(Paragraph(bullet_text, normal))
            continue

        # End of bullet section
        if line == "</ul>" and bullet_buffer:
            story.append(ListFlowable(
                [ListItem(item) for item in bullet_buffer],
                bulletType="bullet",
                bulletChar="•"
            ))
            bullet_buffer = []
            continue

        # Normal paragraph lines
        if line and not line.startswith("<ul>") and not line.startswith("</ul>"):
            story.append(Paragraph(line, normal))
            story.append(Spacer(1, 8))

    doc.build(story)
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

    # Ask the model to return HTML. Headings in <strong>, sub-points in <ul><li> with '• ' prefix.
    final_prompt = f"""
You will combine partial summaries into a single, well-structured final summary and return the output AS VALID HTML ONLY (no extra commentary, no markdown).

Requirements (IMPORTANT):
- Use <strong> tags for headings (e.g. <strong>Introduction</strong>).
- For sub-points, produce an unordered list using <ul> and <li>.
  Each <li> text should begin with the bullet symbol "• " (U+2022) followed by the short point.
  Example: <ul><li> First sub-point</li><li> Second sub-point</li></ul>
- Keep paragraphs short. Prefer lists for Key Themes / Findings.
- Do NOT include any <script> tags or inline event handlers.
- Output only HTML markup (no surrounding backticks or text).

Structure to produce (as HTML, with headings wrapped in <strong>):
<strong>Introduction</strong>
<p>Short sentence(s) about purpose/context.</p>

<strong>Key Themes / Core Arguments</strong>
<ul>
<li> Theme 1 summary (very short)</li>
<li> Theme 2 summary</li>
</ul>

<strong>Method / Approach</strong>
<ul>
<li> Method point 1</li>
<li> Method point 2</li>
</ul>

<strong>Findings / Insights</strong>
<ul>
<li> Finding 1</li>
<li> Finding 2</li>
</ul>

<strong>Conclusion</strong>
<p>One short concluding paragraph.</p>

Target length guidance (human-readable): {summary_instruction}

-- BELOW are the partial chunk summaries to merge. Combine them, remove duplicates, and produce concise bullets & short paragraphs as described. --
{combined_summary_text}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.2
    )

    # The model output should be HTML. Return it verbatim.
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
