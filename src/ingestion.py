"""Loads raw documents (txt/md now, pdf/docx pluggable) and splits into
clause-aware chunks that we can embed and cite."""
import os
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    clause_ref: str | None
    index: int


def load_document_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        with open(path, encoding="utf-8") as f:
            return f.read()
    if ext == ".pdf":
        import pdfplumber
        text = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)
    raise ValueError(f"Unsupported file type: {ext}")


CLAUSE_PATTERN = re.compile(
    r"(?:^|\n)\s*((?:Section|Clause|Article)\s+\d+(?:\.\d+)*)", re.I
)


def chunk_document(text: str, target_chars: int = 900) -> list[Chunk]:
    """Splits on detected clause headings first; falls back to paragraph
    windows of ~target_chars for documents without numbered clauses
    (meeting minutes, invoices, inspection reports)."""
    matches = list(CLAUSE_PATTERN.finditer(text))
    chunks: list[Chunk] = []

    if len(matches) >= 2:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(Chunk(text=chunk_text, clause_ref=m.group(1).strip(), index=len(chunks)))
        return chunks

    # fallback: paragraph windows
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    buf = ""
    for p in paras:
        if len(buf) + len(p) > target_chars and buf:
            chunks.append(Chunk(text=buf.strip(), clause_ref=None, index=len(chunks)))
            buf = ""
        buf += ("\n\n" if buf else "") + p
    if buf.strip():
        chunks.append(Chunk(text=buf.strip(), clause_ref=None, index=len(chunks)))
    return chunks


DOC_TYPE_HINTS = {
    "contract": ["agreement", "contractor shall", "conditions of contract", "clause"],
    "tender": ["notice inviting", "bid document", "tender", "earnest money"],
    "spec": ["specification", "shall conform to", "is code", "tolerance"],
    "inspection_report": ["inspection", "observed", "non-conformance", "site visit"],
    "schedule": ["milestone", "planned start", "gantt", "baseline"],
    "minutes": ["minutes of meeting", "attendees", "action item"],
    "change_order": ["change order", "variation order", "scope change"],
    "invoice": ["invoice", "amount due", "gst", "bill to"],
    "technical_report": ["analysis", "findings", "recommendation", "test results"],
}


def guess_doc_type(text: str) -> str:
    lowered = text.lower()
    # Prefer distinctive document headers over keyword frequency. This prevents
    # progress minutes containing the word "milestone" from being mislabeled as
    # a schedule document.
    header_rules = [
        ("change_order", r"^\s*change order\b"),
        ("inspection_report", r"^\s*site inspection report\b"),
        ("minutes", r"^\s*minutes of (?:progress|meeting)\b"),
        ("contract", r"^\s*contract agreement\b"),
        ("tender", r"^\s*notice inviting tender\b"),
        ("invoice", r"^\s*invoice\b"),
    ]
    for doc_type, pattern in header_rules:
        if re.search(pattern, text, re.I | re.M):
            return doc_type
    scores = {dt: sum(lowered.count(k) for k in kws) for dt, kws in DOC_TYPE_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "technical_report"
