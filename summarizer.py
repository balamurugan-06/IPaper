from _future_ import annotations
import json
import re
from typing import Dict, List, Any, Optional, Tuple

# --------- Configuration ---------
DEFAULT_MODEL = "gpt-4o-mini"  # change to your deployed model
TEMPERATURE = 0.1              # keep deterministic & terse
MAX_CHARS_PER_CHUNK = 8000     # tune to your context window

SYSTEM_PROMPT = (
    "You are a careful evidence summarizer. Be accurate, neutral, and concise. "
    "Do not invent data. If something isn’t reported, output “Not reported.” "
    "Use plain language. Extract study essentials (design, population, interventions, comparators, outcomes, results). "
    "Report both relative and absolute effect sizes when available. "
    "Identify major biases, funding, and generalizability. Provide clinician and patient-friendly summaries. "
    "Keep totals about 300–600 words (≤800 for meta-analyses). Units and numbers must match the paper. "
    "Each value must be a single short sentence (≤30 words)."
)

# --------- Public API (call from your route/controller) ---------
def summarize_document(
    client,
    paper_text: str,
    template: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    user_notes: Optional[str] = None,
) -> Dict[str, str]:
    """
    Main entry point.
    Returns: {"json": <minified JSON string>, "text": <pretty plain text>}
    """
    # 1) Chunk long text -> short notes (plain prose), then consolidate to JSON once
    notes = _summarize_in_chunks_to_notes(client, model, paper_text, user_notes)

    # 2) Consolidate notes -> strict JSON using the dynamic template
    raw = _consolidate_notes_to_json(client, model, notes, template, user_notes)

    # 3) Parse/repair/validate JSON
    data = _parse_or_repair_json(raw)

    # 4) Produce plain-text rendering with clean spacing
    pretty = _render_plain(data)

    return {
        "json": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        "text": pretty,
    }

# --------- Chunking & consolidation ---------
def _split_text(text: str, max_len: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    text = text or ""
    if len(text) <= max_len:
        return [text]
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]

def _summarize_in_chunks_to_notes(
    client, model: str, paper_text: str, user_notes: Optional[str]
) -> List[str]:
    """
    For long inputs, create short structured notes per chunk (NOT JSON).
    These notes are later merged into final JSON.
    """
    chunks = _split_text(paper_text, MAX_CHARS_PER_CHUNK)
    notes: List[str] = []
    for idx, ch in enumerate(chunks, 1):
        user_prompt = (
            "Create concise notes (5–9 short sentences) capturing key methods, population, "
            "comparators, outcomes, main results with effect sizes (relative and absolute if available), "
            "bias/limitations, funding/conflicts, and generalizability. "
            "Plain sentences only. No lists, no Markdown, no JSON."
            f"\n\nUser preferences (optional): {user_notes or 'None'}"
            f"\n\nPaper chunk {idx}/{len(chunks)}:\n{ch}"
        )
        txt = _chat(client, model, SYSTEM_PROMPT, user_prompt)
        notes.append(_strip_md(txt))
    return notes

def _consolidate_notes_to_json(
    client, model: str, notes: List[str], template: Dict[str, Any], user_notes: Optional[str]
) -> str:
    instructions = _make_output_instructions(template)
    notes_text = "\n\n".join(f"- {n}" for n in notes)
    user_prompt = (
        f"{instructions}\n\n"
        f"Use the following notes distilled from the paper to fill each value with 1–2 short sentences (≤30 words).\n"
        f"If information is not present, write “Not reported.”\n"
        f"User preferences (optional): {user_notes or 'None'}\n\n"
        f"Paper notes:\n{notes_text}"
    )
    return _chat(client, model, SYSTEM_PROMPT, user_prompt)

# --------- Dynamic instructions from any template ---------
def _make_output_instructions(template: Dict[str, Any]) -> str:
    """
    Template schema input example:
    {
      "sections": [
        {"heading": "Title & Citation 📚", "items": ["Full title", "Authors, journal, year", "DOI/URL"]},
        {"heading": "Study Snapshot 🧠", "items": ["Question (in one line)", "Design", "Setting & dates", "Registration / protocol"]},
        ...
      ]
    }
    """
    if "sections" not in template or not isinstance(template["sections"], list):
        raise ValueError("Template must include 'sections': [ {heading, items[]} ]")

    lines = [
        "Return ONLY one JSON object with this structure:",
        "- top-level key: blocks (array)",
        "- each block: heading (string), items (array of {label: string, value: string})",
        "Use the exact order and labels below.",
        "Each value must be a single short sentence (≤30 words).",
        "If a field is not in the paper, write “Not reported.”",
        "Do not include Markdown, asterisks, bullet lists, code fences, or any text outside the JSON.",
    ]
    for i, sec in enumerate(template["sections"], 1):
        heading = _clean_inline(sec.get("heading", ""))
        items = sec.get("items", [])
        if not heading or not items:
            raise ValueError(f"Invalid section at index {i}")
        lines.append(f"{i}) Heading: {heading}")
        lines.append(f"   Items: " + " | ".join(_clean_inline(x) for x in items))
    return "\n".join(lines)

# --------- Validation, repair, rendering ---------
def _parse_or_repair_json(raw: str) -> Dict[str, Any]:
    txt = (raw or "").strip()
    # strip accidental code fences
    txt = re.sub(r'^(?:json)?\s*', '', txt)
    txt = re.sub(r'\s*$', '', txt)
    # normalize smart quotes
    txt = txt.replace("“", '"').replace("”", '"').replace("’", "'")
    # cheap trailing comma fix
    txt = txt.replace(",]", "]").replace(",}", "}")
    try:
        data = json.loads(txt)
    except Exception as e:
        raise ValueError(f"Model did not return valid JSON. Error: {e}\nRaw (first 800 chars):\n{raw[:800]}")

    if not isinstance(data, dict) or "blocks" not in data or not isinstance(data["blocks"], list):
        raise ValueError("JSON missing required top-level 'blocks' array.")

    # enforce minimal shape and strings
    for b in data["blocks"]:
        if not isinstance(b, dict):
            raise ValueError("Each block must be an object.")
        b.setdefault("heading", "")
        b.setdefault("items", [])
        if not isinstance(b["items"], list):
            raise ValueError("block.items must be an array.")
        for it in b["items"]:
            if not isinstance(it, dict):
                raise ValueError("Each item must be an object.")
            it.setdefault("label", "")
            it.setdefault("value", "")
            # normalize values
            it["label"] = _clean_inline(it["label"])
            it["value"] = _clean_value(it["value"])
    return data

def _render_plain(summary_obj: Dict[str, Any]) -> str:
    """Readable text with clear headings/line breaks for PDFs/emails/logs."""
    out: List[str] = []
    for block in summary_obj.get("blocks", []):
        heading = block.get("heading", "").strip()
        if heading:
            out.append(heading)
            out.append("-" * len(heading))
        for it in block.get("items", []):
            label = it.get("label", "").strip()
            value = (it.get("value", "") or "Not reported.").strip()
            if label:
                out.append(f"{label}: {value}")
            else:
                out.append(value)
        out.append("")  # blank line between sections
    return "\n".join(out).strip()

# --------- Low-level helpers ---------
def _chat(client, model: str, system: str, user: str) -> str:
    """
    Thin wrapper around OpenAI-like clients:
    client.chat.completions.create(model=..., messages=[...])
    Adjust if your SDK differs (e.g., client.responses.create).
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=TEMPERATURE,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    content = resp.choices[0].message.content or ""
    return content.strip()

def _strip_md(s: str) -> str:
    """Remove common Markdown artifacts from chunk notes."""
    s = s.replace("\t", " ")
    s = re.sub(r"{1,3}.*?{1,3}", "", s, flags=re.DOTALL)  # inline/fenced code
    s = re.sub(r"[*_]{1,3}", "", s)                         # bold/italic markers
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)        # headings
    s = re.sub(r"^\s*[-•]\s*", "", s, flags=re.MULTILINE)   # bullets
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _clean_inline(s: str) -> str:
    """Single-line cleanup: drop newlines/asterisks/backticks."""
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("*", "").replace("", "").replace("`", "")
    return re.sub(r"\s{2,}", " ", s).strip()

def _clean_value(v: Any) -> str:
    s = str(v or "").strip()
    s = _strip_md(s)
    # collapse whitespace; ensure sentence ends with period.
    s = re.sub(r"\s{2,}", " ", s)
    if s and s[-1] not in ".!?":
        s += "."
    return s

# --------- Example usage (remove or adapt in your app) ---------
if _name_ == "_main_":
    # Dummy client shim for illustration:
    try:
        from openai import OpenAI
        client = OpenAI()  # expects OPENAI_API_KEY in env
    except Exception:  # fallback placeholder, you should supply a real client
        class _Dummy: pass
        client = _Dummy()  # replace with your actual client instance
        raise SystemExit("Provide a real client before running this module.")

    demo_template = {
        "sections": [
            {"heading": "Title & Citation 📚", "items": ["Full title", "Authors, journal, year", "DOI/URL"]},
            {"heading": "Study Snapshot 🧠", "items": ["Question (in one line)", "Design", "Setting & dates", "Registration / protocol"]},
            {"heading": "Bottom Line (Clinician) ✅", "items": ["Summary"]},
            {"heading": "Bottom Line (Patient-Friendly) 🗣️", "items": ["Summary"]},
        ]
    }

    demo_text = "Paste paper text here or load from PDF extraction…"

    result = summarize_document(client, demo_text, demo_template, model=DEFAULT_MODEL)
    print("\n=== JSON ===\n", result["json"])
    print("\n=== TEXT ===\n", result["text"])
