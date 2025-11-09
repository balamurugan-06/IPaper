import fitz
from tqdm import tqdm
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
import os
import re

# ========== CONFIG ==========

OPENAI_API_KEY = os.getenv("GEN_AI_KEY")
MODEL_NAME = "gpt-4o-mini"
CHUNK_SIZE = 6000
# ============================

client = OpenAI(api_key=OPENAI_API_KEY)

def save_summary_to_pdf(summary_text, output_path="summary.pdf"):
    """Convert markdown-formatted text to a properly styled PDF"""
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           topMargin=0.75*inch, bottomMargin=0.75*inch,
                           leftMargin=0.75*inch, rightMargin=0.75*inch)
    
    styles = getSampleStyleSheet()
    
    # Create custom styles
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=12,
        textColor='#1a1a1a',
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading2'],
        fontSize=13,
        spaceAfter=8,
        spaceBefore=12,
        textColor='#2c3e50',
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=6
    ))
    
    styles.add(ParagraphStyle(
        name='BulletPoint',
        parent=styles['BodyText'],
        fontSize=10,
        leading=14,
        leftIndent=20,
        bulletIndent=10,
        spaceAfter=4
    ))
    
    story = []
    lines = summary_text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            story.append(Spacer(1, 0.1*inch))
            i += 1
            continue
        
        # Horizontal rule
        if line.startswith('---') or line == '---':
            story.append(Spacer(1, 0.1*inch))
            story.append(HRFlowable(width="100%", thickness=1, color='#cccccc'))
            story.append(Spacer(1, 0.1*inch))
            i += 1
            continue
        
        # Main title (##)
        if line.startswith('## '):
            title_text = clean_markdown(line[3:])
            story.append(Paragraph(title_text, styles['CustomTitle']))
            i += 1
            continue
        
        # Section headers (###)
        if line.startswith('### '):
            header_text = clean_markdown(line[4:])
            story.append(Paragraph(header_text, styles['CustomHeading']))
            i += 1
            continue
        
        # Emoji headers (🔸, 📊, etc.)
        if re.match(r'^[🔸📊✅⚠️🔬📈📝🎯💡⚡🌟]+\s*\*\*', line):
            header_text = clean_markdown(line)
            story.append(Paragraph(header_text, styles['CustomHeading']))
            i += 1
            continue
        
        # Bullet points (• or -)
        if line.startswith('• ') or line.startswith('- '):
            bullet_text = clean_markdown(line[2:])
            story.append(Paragraph(f"• {bullet_text}", styles['BulletPoint']))
            i += 1
            continue
        
        # Numbered lists
        if re.match(r'^\d+\.\s', line):
            list_text = clean_markdown(line)
            story.append(Paragraph(list_text, styles['BulletPoint']))
            i += 1
            continue
        
        # Regular paragraph
        paragraph_lines = [line]
        i += 1
        
        # Collect continuation lines
        while i < len(lines) and lines[i].strip() and \
              not lines[i].startswith(('##', '###', '• ', '- ', '---')) and \
              not re.match(r'^[🔸📊✅⚠️🔬📈📝🎯💡⚡🌟]+\s*\*\*', lines[i]) and \
              not re.match(r'^\d+\.\s', lines[i]):
            paragraph_lines.append(lines[i].strip())
            i += 1
        
        full_paragraph = ' '.join(paragraph_lines)
        cleaned_text = clean_markdown(full_paragraph)
        story.append(Paragraph(cleaned_text, styles['CustomBody']))
    
    doc.build(story)
    return output_path

def clean_markdown(text):
    """Convert markdown to reportlab HTML-like formatting"""
    # Bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # Italic (*text* or _text_)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    
    # Escape special XML characters
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    # Restore our formatting tags
    text = text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    text = text.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    
    return text

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

def summarize_chunk(chunk, fePrompt):
    final = f"{fePrompt}\n\n{chunk}"
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
    fePrompt = promptFromFE + summary_instruction

    for i, chunk in enumerate(tqdm(chunks, desc="Summarizing chunks")):
        try:
            summary = summarize_chunk(chunk, fePrompt)
            summaries.append(summary)
        except Exception as e:
            print(f"⚠️ Error summarizing chunk {i+1}: {e}")

    # Preserve newlines when combining summaries
    combined_summary_text = "\n\n".join(summaries)
    print("\nGenerating final summary...")

    final_prompt = (
        f"{fePrompt}\n\n"
        f"Here are multiple partial summaries of a document. Combine them into a single, well-structured summary "
        f"using markdown formatting (headers with ##, bullet points with •, bold with **, etc.):\n\n"
        f"{combined_summary_text}"
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
