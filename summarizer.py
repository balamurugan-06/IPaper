from _future_ import annotations
import json
import re
import time
from typing import Dict, List, Any, Optional, Tuple

# --------- Configuration ---------
DEFAULT_MODEL = "gpt-4o-mini"   # change to your deployed model
TEMPERATURE = 0.1               # keep deterministic & terse
MAX_CHARS_PER_CHUNK = 8000      # tune to your context window
CHUNK_OVERLAP = 600             # keep context continuity across chunks
MAX_RETRIES = 2                 # retry on invalid JSON or transient API errors
SENTENCE_MAX_WORDS = 30

SYSTEM_PROMPT = (
    "You are a careful evidence summarizer. Be accurate, neutral, and concise. "
    "Do not invent data. If something isn’t reported, output \"Not reported.\" "
    "Use plain language. Extract study essentials (design, population, interventions, comparators, outcomes, results). "
    "Report both relative and absolute effect sizes when available. "
    "Identify major biases, funding, and generalizability. Provide clinician and patient-friendly summaries. "
    "Keep totals about 300–600 words (≤800 for meta-analyses). Units and numbers must match the paper. "
    f"Each value must be a single short sentence (≤{SENTENCE_MAX_WORDS} words)."
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
    raw = _consolidate_notes_to_json_with_retries(client, model, notes, template, user_notes)

    # 3) Parse/repair/validate JSON to strict schema
    data = _parse_repair_and_lock_schema(raw, template)

    # 4) Produce plain-text rendering with clean spacing
    pretty = _render_plain(data)

    return {
        "json": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        "text": pretty,
    }

# --------- Chunking & consolidation ---------

_DEF_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")


def _smart_split(text: str, max_len: int, overlap: int) -> List[str]:
    text = text or ""
    if len(text) <= max_len:
        return [text]

    # Prefer paragraph splits first
    paras = re.split(r"\n{2,}", text)
    chunks: List[str] = []
    buf = []
    cur = 0

    def flush_buf():
        s = "\n\n".join(buf).strip()
        if s:
            chunks.append(s)

    for p in paras:
        if cur + len(p) + 2 <= max_len:
            buf.append(p)
            cur += len(p) + 2
        else:
            # try sentence-level packing for the paragraph
            sents = _DEF_SENT_SPLIT.split(p)
            for s in sents:
                if cur + len(s) + 1 <= max_len:
                    buf.append(s)
                    cur += len(s) + 1
                else:
                    flush_buf()
                    # start new chunk with overlap from previous
                    if overlap and chunks:
                        tail = chunks[-1][-overlap:]
                        chunks[-1] = chunks[-1]  # keep as is
                        buf[:] = [tail + s]
                        cur = len(tail) + len(s)
                    else:
                        buf[:] = [s]
                        cur = len(s)
    flush_buf()

    # Final safety: if anything still exceeds max_len, hard-slice with overlap
    final: List[str] = []
    for ch in chunks:
        if len(ch) <= max_len:
            final.append(ch)
        else:
            i = 0
            while i < len(ch):
                final.append(ch[i:i+max_len])
                i += max_len - overlap if overlap < max_len else max_len
    return final


def _summarize_in_chunks_to_notes(
    client, model: str, paper_text: str, user_notes: Optional[str]
) -> List[str]:
    """
    For long inputs, create short structured notes per chunk (NOT JSON).
    These notes are later merged into final JSON.
    """
    chunks = _smart_split(paper_text, MAX_CHARS_PER_CHUNK, CHUNK_OVERLAP)
    notes: List[str] = []

    for idx, ch in enumerate(chunks, 1):
        user_prompt = (
            "Create concise notes (5–9 short sentences) capturing: methods, population, "
            "comparators, outcomes, main results with effect sizes (relative and absolute if available), "
            "bias/limitations, funding/conflicts, and generalizability. "
            "Plain sentences only. No lists, no Markdown, no JSON."
            f"\n\nUser preferences (optional): {user_notes or 'None'}"
            f"\n\nPaper chunk {idx}/{len(chunks)}:\n{ch}"
        )
        txt = _chat(client, model, SYSTEM_PROMPT, user_prompt)
        notes.append(_strip_md(txt))
    return notes


def _consolidate_notes_to_json_with_retries(
    client, model: str, notes: List[str], template: Dict[str, Any], user_notes: Optional[str]
) -> str:
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _consolidate_notes_to_json_once(client, model, notes, template, user_notes)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(0.6 * (attempt + 1))
            else:
                raise
    # unreachable
    raise last_err  # type: ignore


def _consolidate_notes_to_json_once(
    client, model: str, notes: List[str], template: Dict[str, Any], user_notes: Optional[str]
) -> str:
    instructions, labels = _make_output_instructions(template)
    notes_text = "\n\n".join(f"- {n}" for n in notes)

    user_prompt = (
        f"{instructions}\n\n"
        f"Use the notes distilled from the paper to fill each value with 1–2 short sentences (≤{SENTENCE_MAX_WORDS} words).\n"
        f"If information is not present, write \"Not reported.\" Do not add new labels.\n"
        f"User preferences (optional): {user_notes or 'None'}\n\n"
        f"Paper notes:\n{notes_text}"
    )

    raw = _chat(client, model, SYSTEM_PROMPT, user_prompt)
    return raw

# --------- Dynamic instructions & schema locking ---------

def _make_output_instructions(template: Dict[str, Any]) -> Tuple[str, List[Tuple[str, List[str]]]]:
    """
    Template schema input example:
    {
      "sections": [
        {"heading": "Title & Citation 📚", "items": ["Full title", "Authors, journal, year", "DOI/URL"]},
        {"heading": "Study Snapshot 🧠", "items": ["Question (in one line)", "Design", "Setting & dates", "Registration / protocol"]},
        ...
      ]
    }
    Returns: (instruction_text, list_of_(heading, [item_labels]))
    """
    if "sections" not in template or not isinstance(template["sections"], list):
        raise ValueError("Template must include 'sections': [ {heading, items[]} ]")

    shape: List[Tuple[str, List[str]]] = []

    lines = [
        "Return ONLY a single JSON object with EXACTLY this structure:",
        "{\n  \"blocks\": [\n    { \"heading\": string, \"items\": [ { \"label\": string, \"value\": string }, ... ] },\n    ...\n  ]\n}",
        "Rules:",
        "- No Markdown, no bullet signs, no code fences, no extra keys.",
        "- Use the EXACT order and labels below; do not add, remove, or rename items.",
        f"- Each value must be one short sentence (≤{SENTENCE_MAX_WORDS} words).",
        "- If a field is not in the paper, write 'Not reported.'",
    ]

    for i, sec in enumerate(template["sections"], 1):
        heading = _clean_inline(sec.get("heading", "").strip())
        items = [ _clean_inline(x) for x in sec.get("items", []) ]
        if not heading or not items:
            raise ValueError(f"Invalid section at index {i}")
        shape.append((heading, items))
        lines.append(f"{i}) Heading: {heading}")
        lines.append("   Items: " + " | ".join(items))

    return "\n".join(lines), shape


# --------- Validation, repair, rendering ---------

_CODE_FENCE_START = re.compile(r"^(?:json)?\s*", re.MULTILINE)
_CODE_FENCE_END = re.compile(r"\s*$", re.MULTILINE)
_LARGEST_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def _parse_repair_and_lock_schema(raw: str, template: Dict[str, Any]) -> Dict[str, Any]:
    txt = (raw or "").strip()

    # 1) Strip code fences & obvious markdown
    txt = _CODE_FENCE_START.sub("", txt)
    txt = _CODE_FENCE_END.sub("", txt)

    # 2) Normalise quotes & stray commas
    txt = txt.replace("“", '"').replace("”", '"').replace("’", "'")
    txt = txt.replace(",]", "]").replace(",}", "}")

    # 3) Try to auto-extract the largest JSON-looking block if the model added chatter
    if not txt.strip().startswith("{"):
        m = _LARGEST_JSON_BLOCK.search(txt)
        if m:
            txt = m.group(0)

    # 4) Parse JSON
    try:
        data = json.loads(txt)
    except Exception as e:
        raise ValueError(f"Model did not return valid JSON. Error: {e}\nRaw (first 800 chars):\n{raw[:800]}")

    if not isinstance(data, dict) or "blocks" not in data or not isinstance(data["blocks"], list):
        raise ValueError("JSON missing required top-level 'blocks' array.")

    # 5) Lock to template schema: exact headings + item labels in order
    expected = [( _clean_inline(sec.get("heading", "")), [ _clean_inline(x) for x in sec.get("items", []) ]) for sec in template.get("sections", [])]

    # Build new object to ensure order + labels enforced
    locked_blocks: List[Dict[str, Any]] = []
    source_blocks: Dict[str, Dict[str, str]] = {}

    # Map incoming data for flexible matching by normalized labels
    for b in data.get("blocks", []):
        heading = _clean_inline(b.get("heading", ""))
        items = b.get("items", []) if isinstance(b.get("items", []), list) else []
        label_map = {}
        for it in items:
            if isinstance(it, dict):
                label = _clean_inline(it.get("label", ""))
                value = _clean_value(it.get("value", ""))
                if label:
                    label_map[label] = value
        if heading:
            source_blocks[heading] = label_map

    for heading, item_labels in expected:
        src = source_blocks.get(heading, {})
        out_items = []
        for lab in item_labels:
            val = _clean_value(src.get(lab, "Not reported."))
            out_items.append({"label": lab, "value": _enforce_sentence_length(val)})
        locked_blocks.append({"heading": heading, "items": out_items})

    return {"blocks": locked_blocks}


def _render_plain(summary_obj: Dict[str, Any]) -> str:
    """Readable text with clear headings/line breaks for PDFs/emails/logs."""
    out: List[str] = []
    for block in summary_obj.get("blocks", []):
        heading = (block.get("heading", "") or "").strip()
        if heading:
            out.append(heading)
            out.append("-" * len(heading))
        for it in block.get("items", []):
            label = (it.get("label", "") or "").strip()
            value = (it.get("value", "") or "Not reported.").strip()
            if label:
                out.append(f"{label}: {value}")
            else:
                out.append(value)
        out.append("")  # blank line between sections
    return "\n".join(out).strip()

# --------- Low-level helpers ---------

class _APIError(Exception):
    pass


def _chat(client, model: str, system: str, user: str) -> str:
    """
    Thin wrapper around OpenAI-like clients.
    Tries Chat Completions first, then Responses API as a fallback.
    """
    # Primary: Chat Completions
    try:
        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            resp = client.chat.completions.create(
                model=model,
                temperature=TEMPERATURE,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            content = getattr(resp.choices[0].message, "content", "") or ""
            return content.strip()
    except Exception as e:
        last = e
    else:
        # If we got here without error, we already returned
        pass

    # Fallback: Responses API
    try:
        if hasattr(client, "responses"):
            resp = client.responses.create(
                model=model,
                temperature=TEMPERATURE,
                input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            # unify content extraction
            txt = ""
            if hasattr(resp, "output_text"):
                txt = resp.output_text or ""
            elif hasattr(resp, "content") and resp.content:
                # some SDKs return a list of content parts
                parts = [getattr(p, "text", "") for p in resp.content]
                txt = "".join(parts)
            return (txt or "").strip()
    except Exception as e:
        raise _APIError(str(e))

    # If neither path worked
    raise _APIError(str(last))  # type: ignore


def _strip_md(s: str) -> str:
    """Remove common Markdown / junk artifacts from chunk notes."""
    s = s.replace("\t", " ")
    s = re.sub(r"{1,3}[\s\S]*?{1,3}", "", s)       # inline/fenced code
    s = re.sub(r"[*_]{1,3}", "", s)                    # bold/italic markers
    s = re.sub(r"^[#>]+\s*", "", flags=re.MULTILINE, string=s)  # headings/quotes
    s = re.sub(r"^\s*[-•]\s*", "", flags=re.MULTILINE, string=s) # bullets
    s = re.sub(r"\|{2,}", " ", s)                    # stray pipes
    s = re.sub(r"\s*--\s*", " ", s)                 # double dashes used as bullets
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _clean_inline(s: str) -> str:
    """Single-line cleanup: drop newlines/asterisks/backticks."""
    s = (s or "").replace("\n", " ").replace("\r", " ")
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


def _enforce_sentence_length(s: str) -> str:
    words = s.split()
    if len(words) <= SENTENCE_MAX_WORDS:
        return s
    # truncate gracefully, keep terminal punctuation
    trimmed = " ".join(words[:SENTENCE_MAX_WORDS]).rstrip(",;:")
    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "."
    return trimmed

# --------- Example usage (remove or adapt in your app) ---------
if _name_ == "_main_":
    # Dummy client shim for illustration:
    try:
        from openai import OpenAI
        client = OpenAI()  # expects OPENAI_API_KEY in env
    except Exception:  # fallback placeholder, you should supply a real client
        class _Dummy: ...
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
