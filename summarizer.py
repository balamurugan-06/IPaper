import fitz
import pymupdf as fitz
from tqdm import tqdm
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from textwrap import wrap
import os
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    WEASYPRINT_AVAILABLE = False
from concurrent.futures import ThreadPoolExecutor
load_dotenv()

# ========== CONFIG ==========

OPENAI_API_KEY = os.getenv("GEN_AI_KEY")
MODEL_NAME = "gpt-4o-mini"
CHUNK_SIZE = 6000
# ============================

client = OpenAI(api_key=OPENAI_API_KEY)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

_executor_pdf = ThreadPoolExecutor(max_workers=int(os.getenv("PDF_BG_WORKERS", "2")))

def add_emojis_to_summary(summary_html, prompt):
    """Add contextual and section-based emojis to summary HTML."""
    topic_emojis = {
        "business": "💼",
        "finance": "💰",
        "education": "🎓",
        "medical": "🩺",
        "health": "💪",
        "technology": "💻",
        "research": "🔬",
        "marketing": "📈",
        "environment": "🌱",
        "law": "⚖️",
        "history": "📜",
        "travel": "✈️",
        "science": "🧠",
        "art": "🎨",
        "engineering": "🧰",
    }

    prompt_lower = prompt.lower()
    main_emoji = next((emoji for k, emoji in topic_emojis.items() if k in prompt_lower), "✨")

    section_emojis = {
        "introduction": "📘",
        "key themes": "💡",
        "core arguments": "💡",
        "method": "🧭",
        "approach": "🧭",
        "findings": "📊",
        "insights": "🔍",
        "conclusion": "🎯",
        "summary": "📝"
    }

    def add_section_emoji(heading):
        heading_lower = heading.lower()
        for key, emoji in section_emojis.items():
            if key in heading_lower:
                return f"{emoji} {heading}"
        return f"{main_emoji} {heading}"

    import re
    summary_html = re.sub(
        r"<strong>(.*?)</strong>",
        lambda m: f"<strong>{add_section_emoji(m.group(1))}</strong>",
        summary_html,
        flags=re.IGNORECASE
    )

    return summary_html




def save_summary_to_pdf(summary_html, output_path="summary.pdf"):
    if WEASYPRINT_AVAILABLE:
        html_template = f"""
        <html>
        <head>
        <meta charset="utf-8">
        <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #222;
            padding: 40px;
        }}
        strong {{
            display:block;
            margin-top:18px;
            margin-bottom:6px;
            font-size:16px;
        }}
        </style>
        </head>
        <body>
        {summary_html}
        </body>
        </html>
        """

        HTML(string=html_template).write_pdf(output_path)

    else:
        # Windows fallback using ReportLab
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        import re

        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()

        text = re.sub(r"<[^>]+>", "", summary_html)

        story = [Paragraph(text.replace("\n", "<br/>"), styles["BodyText"])]
        doc.build(story)

    return output_path

def save_summary_to_pdf_async(summary_html, output_path="summary.pdf"):
    return _executor_pdf.submit(save_summary_to_pdf, summary_html, output_path)


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
You will combine partial summaries into a single final summary and return ONLY valid HTML (no markdown, no extra commentary).

IMPORTANT (FOLLOW STRICTLY):
- FOLLOW THE USER'S TEMPLATE INSTRUCTIONS EXACTLY as provided below.
- DO NOT force any predefined structure like Introduction, Key Themes, Method, Findings, Conclusion.
- Only create headings, paragraphs, or lists IF the user's template requires them.
- Use <strong> ONLY for headings that the template includes.
- Use <ul> and <li> ONLY if the template format asks for bullet points.
- Add visual spacing between section titles by inserting <br><br> BEFORE each <strong> heading.
- No additional sections or formatting should be added beyond what the template specifies.
- NO <script> tags or inline JS.
- Output must be PURE HTML only.
PROFESSIONAL FORMATTING RULES:
- Do not use emojis or emoticons.
- Do not use decorative symbols.
- Use clear, professional business language.
- Use meaningful headings and bullet points only when required by the selected template.

USER TEMPLATE INSTRUCTIONS:
\"\"\"
{promptFromFE}
\"\"\"

Document length guidance: {summary_instruction}

Below are the merged chunk summaries. Combine, rewrite, remove duplicates, and shape the content EXACTLY according to the USER TEMPLATE ABOVE:
{combined_summary_text}
"""


    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.2
    )

    # The model output should be HTML. Return it verbatim.
    return response.choices[0].message.content.strip()

def summarizer(pdfPath, promptFromFE, docId):

    # ---------------------------------------------------------
    # 1. Determine the uploaded document path
    # ---------------------------------------------------------

    pdf_path = pdfPath.strip()

    # If a relative path was supplied, convert it to the
    # application's configured upload directory.

    if not os.path.isabs(pdf_path):

        pdf_path = os.path.join(
            os.getenv(
                "UPLOAD_FOLDER",
                os.path.join(
                    os.path.dirname(
                        os.path.abspath(__file__)
                    ),
                    "uploads"
                )
            ),
            os.path.basename(pdf_path)
        )


    print(
        f"\n📄 Processing document: {pdf_path}"
    )


    # ---------------------------------------------------------
    # 2. Verify document exists
    # ---------------------------------------------------------

    if not os.path.exists(pdf_path):

        raise FileNotFoundError(
            f"Document not found: {pdf_path}"
        )


    # ---------------------------------------------------------
    # 3. Extract text
    # ---------------------------------------------------------

    print(
        "\nExtracting text from PDF..."
    )


    text, num_pages = extract_text_from_pdf(
        pdf_path
    )


    print(
        f"\n✅ Extracted "
        f"{len(text)} characters "
        f"from {num_pages} pages."
    )


    # ---------------------------------------------------------
    # 4. Generate AI summary
    # ---------------------------------------------------------

    print(
        "\nSummarizing document... "
        "(this may take several minutes "
        "for long PDFs)"
    )


    summary = summarize_document(
        text,
        num_pages,
        promptFromFE
    )


    # ---------------------------------------------------------
# 5. Professional summary formatting
# ---------------------------------------------------------

# Emojis are intentionally disabled.
# The AI-generated HTML is returned without automatic emoji insertion.


    # ---------------------------------------------------------
    # 6. Determine summary PDF location
    # ---------------------------------------------------------

    upload_folder = os.getenv(
        "UPLOAD_FOLDER",
        os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            "uploads"
        )
    )


    os.makedirs(
        upload_folder,
        exist_ok=True
    )


    output_pdf = os.path.join(
        upload_folder,
        f"summary_{docId}.pdf"
    )


    print(
        f"\n📄 Creating summary PDF: "
        f"{output_pdf}"
    )


    # ---------------------------------------------------------
    # 7. Create summary PDF
    # ---------------------------------------------------------

    save_summary_to_pdf_async(
        summary,
        output_pdf
    )


    print(
        "\n✅ Summary generation completed."
    )


    # ---------------------------------------------------------
    # 8. Return summary HTML
    # ---------------------------------------------------------

    return summary