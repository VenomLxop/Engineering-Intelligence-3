"""Extraction layer for engineering and construction documents."""
import json
import re
from .llm import get_llm, MockLLM

EXTRACTION_SYSTEM_PROMPT = """You are an information-extraction engine for construction/engineering documents. Extract every distinct contractual obligation you find in the given text chunk.

Return ONLY valid JSON, no prose, in this exact shape:
{"obligations": [
  {"obligation": "<short description of what must be done>",
   "responsible_party": "<company/role responsible, or null>",
   "deadline": "<date or duration, or null>",
   "penalty": "<penalty text, or null>",
   "confidence": <float 0-1>}
]}
Do not treat penalty/consequence-only sentences as separate obligations. Do not invent facts."""


def extract_obligations_from_chunk(chunk_text: str) -> list[dict]:
    llm = get_llm()
    raw = llm.complete(EXTRACTION_SYSTEM_PROMPT, chunk_text, max_tokens=1024)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1])
        return parsed.get("obligations", [])
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


CLAUSE_TYPE_SYSTEM_PROMPT = """Classify the following contract clause into exactly one category: payment, delivery, penalty, quality, safety, termination, dispute, general. Return only the category word."""


def classify_clause_type(clause_text: str) -> str:
    llm = get_llm()
    if isinstance(llm, MockLLM):
        lowered = clause_text.lower()
        for kw, cat in [
            ("liquidated damages", "penalty"), ("penalty", "penalty"),
            ("deliver", "delivery"), ("procure", "delivery"), ("payment", "payment"),
            ("safety", "safety"), ("terminate", "termination"),
            ("dispute", "dispute"), ("testing", "quality"), ("quality", "quality"),
        ]:
            if kw in lowered:
                return cat
        return "general"
    return llm.complete(CLAUSE_TYPE_SYSTEM_PROMPT, clause_text, max_tokens=10).strip().lower()


METADATA_SYSTEM_PROMPT = """Extract project/party metadata from an engineering or construction document. Return ONLY JSON:
{"project_name": null, "location": null, "owner": null, "contractor": null, "contract_value": null, "signed_date": null, "planned_end_date": null, "document_date": null}
Use only explicit information. The project name should omit location/segment suffixes when possible."""


def extract_document_metadata(text: str) -> dict:
    llm = get_llm()
    if isinstance(llm, MockLLM):
        return _mock_metadata_extraction(text)
    raw = llm.complete(METADATA_SYSTEM_PROMPT, text[:5000], max_tokens=500)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _mock_metadata_extraction(text: str) -> dict:
    result: dict = {}
    patterns = {
        "project_name": r"(?:Project|Work)\s*:\s*(.+)",
        "owner": r"(?:Employer|Owner)\s*:\s*(.+)",
        "contractor": r"Contractor\s*:\s*(.+)",
        "signed_date": r"Date of Signing\s*:\s*(.+)",
    }
    for field, pattern in patterns.items():
        m = re.search(pattern, text, re.I)
        if m:
            result[field] = m.group(1).strip().splitlines()[0].strip()

    if result.get("project_name") and "," in result["project_name"]:
        name, loc = result["project_name"].split(",", 1)
        result["project_name"] = name.strip()
        result["location"] = loc.strip()

    value_m = re.search(r"Contract Value\s*:\s*(?:INR|₹)?\s*([\d,]+)", text, re.I)
    if value_m:
        result["contract_value"] = float(value_m.group(1).replace(",", ""))

    doc_date_m = re.search(
        r"(?:Date of Inspection|Date Raised|Date of Meeting|^Date)\s*:\s*(\d{4}-\d{2}-\d{2})",
        text, re.I | re.M,
    )
    if doc_date_m:
        result["document_date"] = doc_date_m.group(1)

    # Contract completion language: explicit absolute date wins; otherwise
    # retain the duration as a note for the seed step to resolve if possible.
    completion_m = re.search(
        r"(?:on or before|complete[d]? by)\s+([A-Z][a-z]+\s+\d{1,2},\s*\d{4})",
        text,
    )
    if completion_m:
        result["planned_end_date"] = completion_m.group(1)
    else:
        duration_m = re.search(r"completed\s+within\s+(\d+)\s+months.*?(?:i\.e\.)\s+on\s+or\s+before\s+([A-Z][a-z]+\s+\d{1,2},\s*\d{4})", text, re.I | re.S)
        if duration_m:
            result["planned_end_date"] = duration_m.group(2)
    return result


CHANGE_ORDER_SYSTEM_PROMPT = """Extract a construction Change Order. Return ONLY JSON:
{"description": "<one sentence>", "cost_impact": null, "schedule_impact_days": null, "date_raised": null, "status": "pending"}"""


def extract_change_order_fields(text: str) -> dict:
    llm = get_llm()
    if isinstance(llm, MockLLM):
        return _mock_change_order_extraction(text)
    raw = llm.complete(CHANGE_ORDER_SYSTEM_PROMPT, text[:4000], max_tokens=300)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _mock_change_order_extraction(text: str) -> dict:
    result: dict = {"status": "pending"}
    desc_m = re.search(r"Description\s*:\s*(.+?)(?:\n\s*\n|\nCost Impact)", text, re.I | re.S)
    if desc_m:
        result["description"] = " ".join(desc_m.group(1).split())[:300]
    cost_m = re.search(r"Cost Impact\s*:\s*(?:INR|₹)?\s*\(?\s*([\d,]+)", text, re.I)
    if cost_m:
        result["cost_impact"] = float(cost_m.group(1).replace(",", ""))
    days_m = re.search(r"Schedule Impact\s*:\s*(\d+)\s*days?", text, re.I)
    if days_m:
        result["schedule_impact_days"] = int(days_m.group(1))
    raised_m = re.search(r"Date Raised\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
    if raised_m:
        result["date_raised"] = raised_m.group(1)
    status_m = re.search(r"Status\s*:\s*(\w+)", text, re.I)
    if status_m:
        result["status"] = status_m.group(1).strip().lower()
    return result


SCHEDULE_SIGNAL_SYSTEM_PROMPT = """Read this progress narrative. If it states the project is behind its baseline schedule, return ONLY JSON: {\"behind_schedule_days\": <integer days>, \"note\": \"<short cause phrase>\"}. Convert weeks to days. If no slippage is stated, return nulls."""


def extract_schedule_signal(text: str) -> dict:
    llm = get_llm()
    if isinstance(llm, MockLLM):
        return _mock_schedule_signal(text)
    raw = llm.complete(SCHEDULE_SIGNAL_SYSTEM_PROMPT, text[:4000], max_tokens=150)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"behind_schedule_days": None, "note": None}


def _mock_schedule_signal(text: str) -> dict:
    # Preserve the conservative lower bound when a range is given, while
    # keeping the original wording for the evidence view.
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*(week|day)s?\s+behind", text, re.I)
    if m:
        low, high, unit = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        factor = 7 if unit == "week" else 1
        return {
            "behind_schedule_days": low * factor,
            "upper_bound_days": high * factor,
            "note": f"Approximately {low}–{high} {unit}s behind the CPM baseline",
        }
    m = re.search(r"(\d+)\s*(week|day)s?\s+behind", text, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        return {"behind_schedule_days": n * (7 if unit == "week" else 1), "note": "Behind the CPM baseline"}
    return {"behind_schedule_days": None, "note": None}
