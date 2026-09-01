"""Build the SQLite intelligence store from documents in data/documents/."""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import init_db
from src.ingestion import load_document_text, chunk_document, guess_doc_type
from src.extraction import (
    extract_obligations_from_chunk,
    classify_clause_type,
    extract_document_metadata,
    extract_change_order_fields,
    extract_schedule_signal,
)
from src.dates import try_parse_date

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "documents")
CONTRACT_DOC_TYPES = {"contract"}
CHANGE_ORDER_DOC_TYPES = {"change_order"}
PROGRESS_DOC_TYPES = {"inspection_report", "minutes", "schedule"}
_STOPWORDS = {"the", "of", "a", "an", "and", "for", "at", "in", "phase", "segment", "project"}


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split()) if name else ""


def _significant_words(name: str) -> set:
    return {w for w in normalize_name(name).replace(",", " ").split() if w not in _STOPWORDS}


def find_matching_project(conn, name: str):
    exact = conn.execute("SELECT project_id FROM projects WHERE lower(name)=?", (normalize_name(name),)).fetchone()
    if exact:
        return exact["project_id"]
    target = _significant_words(name)
    if not target:
        return None
    best_id, best_score = None, 0.0
    for row in conn.execute("SELECT project_id, name FROM projects").fetchall():
        existing = _significant_words(row["name"])
        if not existing:
            continue
        score = len(target & existing) / len(target | existing)
        if score > best_score:
            best_score, best_id = score, row["project_id"]
    return best_id if best_score >= 0.5 else None


def get_or_create_company(conn, name: str, role: str):
    if not name:
        return None
    row = conn.execute("SELECT company_id FROM companies WHERE lower(name)=?", (normalize_name(name),)).fetchone()
    if row:
        return row["company_id"]
    cur = conn.execute("INSERT INTO companies (name, role) VALUES (?, ?)", (name.strip(), role))
    return cur.lastrowid


def get_or_create_project(conn, name: str, location: str | None):
    existing = find_matching_project(conn, name)
    if existing:
        if location:
            conn.execute("UPDATE projects SET location=COALESCE(location, ?) WHERE project_id=?", (location, existing))
        return existing
    cur = conn.execute("INSERT INTO projects (name, location) VALUES (?, ?)", (name.strip(), location))
    return cur.lastrowid


def get_or_create_contract(conn, project_id: int, contractor_company_id, contract_value, signed_date, document_id=None):
    sentinel = -1 if contractor_company_id is None else contractor_company_id
    row = conn.execute(
        "SELECT contract_id FROM contracts WHERE project_id=? AND IFNULL(contractor_company_id, -1)=?",
        (project_id, sentinel),
    ).fetchone()
    if row:
        contract_id = row["contract_id"]
        conn.execute(
            "UPDATE contracts SET document_id=COALESCE(document_id, ?), contract_value=COALESCE(contract_value, ?), signed_date=COALESCE(signed_date, ?) WHERE contract_id=?",
            (document_id, contract_value, signed_date, contract_id),
        )
        return contract_id
    cur = conn.execute(
        "INSERT INTO contracts (project_id, document_id, contractor_company_id, contract_value, signed_date) VALUES (?, ?, ?, ?, ?)",
        (project_id, document_id, contractor_company_id, contract_value, signed_date),
    )
    return cur.lastrowid


def find_contract_for_project(conn, project_id: int, contractor_id=None):
    if contractor_id:
        row = conn.execute(
            "SELECT contract_id FROM contracts WHERE project_id=? AND contractor_company_id=? ORDER BY contract_id LIMIT 1",
            (project_id, contractor_id),
        ).fetchone()
        if row:
            return row["contract_id"]
    row = conn.execute("SELECT contract_id FROM contracts WHERE project_id=? ORDER BY contract_id LIMIT 1", (project_id,)).fetchone()
    return row["contract_id"] if row else None


def _penalty_values(text: str):
    amount = None
    cap = None
    amount_m = re.search(r"(?:penalty|liquidated damages)[^₹\n]*(?:₹|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:per day|/day|per week)?", text, re.I)
    if amount_m:
        amount = float(amount_m.group(1).replace(",", ""))
        if re.search(r"per week", text, re.I):
            amount /= 7.0
    cap_m = re.search(r"capped at\s*(\d+(?:\.\d+)?)%\s*of\s*Contract Value", text, re.I)
    if cap_m:
        cap = float(cap_m.group(1))
    return amount, cap


def main():
    conn = init_db(reset=True)
    ingested = []
    counts = {"documents": 0, "obligations": 0, "change_orders": 0, "schedule_signals": 0}
    project_dates: dict[int, list[str]] = {}

    for fname in sorted(os.listdir(DOCS_DIR)):
        path = os.path.join(DOCS_DIR, fname)
        if not os.path.isfile(path):
            continue
        text = load_document_text(path)
        doc_type = guess_doc_type(text)
        meta = extract_document_metadata(text)

        project_id = None
        contractor_id = None
        contract_id = None
        if meta.get("project_name"):
            project_id = get_or_create_project(conn, meta["project_name"], meta.get("location"))
            owner_id = get_or_create_company(conn, meta.get("owner"), "owner")
            if owner_id:
                conn.execute("UPDATE projects SET owner_company_id=? WHERE project_id=? AND owner_company_id IS NULL", (owner_id, project_id))
            contractor_id = get_or_create_company(conn, meta.get("contractor"), "contractor")

        doc_date = try_parse_date(meta.get("document_date"))
        cur = conn.execute(
            "INSERT INTO documents (project_id, filename, doc_type, document_date) VALUES (?, ?, ?, ?)",
            (project_id, fname, doc_type, doc_date),
        )
        document_id = cur.lastrowid
        counts["documents"] += 1
        if project_id and doc_date:
            project_dates.setdefault(project_id, []).append(doc_date)

        if project_id and doc_type == "contract":
            contract_id = get_or_create_contract(
                conn, project_id, contractor_id, meta.get("contract_value"),
                try_parse_date(meta.get("signed_date")), document_id,
            )
            if meta.get("planned_end_date"):
                parsed_end = try_parse_date(meta["planned_end_date"])
                if parsed_end:
                    conn.execute("UPDATE projects SET planned_end_date=? WHERE project_id=?", (parsed_end, project_id))
        elif project_id:
            contract_id = find_contract_for_project(conn, project_id, contractor_id)

        chunks = chunk_document(text)
        chunk_rows = []
        for ch in chunks:
            c = conn.execute(
                "INSERT INTO chunks (document_id, chunk_index, text, clause_ref) VALUES (?, ?, ?, ?)",
                (document_id, ch.index, ch.text, ch.clause_ref),
            )
            chunk_rows.append((c.lastrowid, ch))
        ingested.append({
            "fname": fname, "text": text, "doc_type": doc_type, "document_id": document_id,
            "project_id": project_id, "contract_id": contract_id, "contractor_id": contractor_id,
            "chunk_rows": chunk_rows,
        })
        conn.commit()

    project_as_of = {pid: max(ds) for pid, ds in project_dates.items() if ds}
    if not project_as_of:
        print("No document dates found; overdue status will use today's date.")

    for doc in ingested:
        project_id = doc["project_id"]
        if not project_id:
            continue
        as_of = project_as_of.get(project_id)

        if doc["doc_type"] == "contract" and doc["contract_id"]:
            for chunk_id, ch in doc["chunk_rows"]:
                if not ch.clause_ref:
                    continue
                clause_type = classify_clause_type(ch.text)
                clause_cur = conn.execute(
                    "INSERT INTO clauses (contract_id, chunk_id, clause_ref, clause_text, clause_type) VALUES (?, ?, ?, ?, ?)",
                    (doc["contract_id"], chunk_id, ch.clause_ref, ch.text, clause_type),
                )
                clause_id = clause_cur.lastrowid
                for ob in extract_obligations_from_chunk(ch.text):
                    description = (ob.get("obligation") or "").strip()
                    if not description:
                        continue
                    # Defensive filter for models that still return a consequence-only sentence.
                    if re.match(r"^(in the event|should the contractor|failure to|delay beyond|any fatal accident)", description, re.I):
                        continue
                    deadline_iso = try_parse_date(ob.get("deadline"))
                    status = "overdue" if deadline_iso and as_of and deadline_iso < as_of else "open"
                    cur = conn.execute(
                        "INSERT INTO obligations (contract_id, clause_id, responsible_company_id, description, deadline, penalty_text, status, confidence, extracted_from_chunk_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (doc["contract_id"], clause_id, doc["contractor_id"], description,
                         deadline_iso, ob.get("penalty"), status, float(ob.get("confidence", 0.5)), chunk_id),
                    )
                    obligation_id = cur.lastrowid
                    amount, cap_pct = _penalty_values(ch.text)
                    if amount is not None:
                        contract_value = conn.execute("SELECT contract_value FROM contracts WHERE contract_id=?", (doc["contract_id"],)).fetchone()["contract_value"]
                        cap_amount = (contract_value * cap_pct / 100.0) if contract_value and cap_pct else None
                        conn.execute(
                            "UPDATE obligations SET penalty_amount_per_day=? WHERE obligation_id=?",
                            (amount, obligation_id),
                        )
                        conn.execute(
                            "INSERT INTO penalties (obligation_id, amount_per_day, cap_amount, clause_id) VALUES (?, ?, ?, ?)",
                            (obligation_id, amount, cap_amount, clause_id),
                        )
                    if deadline_iso:
                        conn.execute(
                            "INSERT INTO deadlines (obligation_id, due_date, is_overdue) VALUES (?, ?, ?)",
                            (obligation_id, deadline_iso, 1 if status == "overdue" else 0),
                        )
                    counts["obligations"] += 1

        elif doc["doc_type"] == "change_order":
            fields = extract_change_order_fields(doc["text"])
            linked_contract = doc["contract_id"] or find_contract_for_project(conn, project_id, doc["contractor_id"])
            conn.execute(
                "INSERT INTO change_orders (project_id, contract_id, document_id, description, cost_impact, schedule_impact_days, date_raised, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, linked_contract, doc["document_id"], fields.get("description"), fields.get("cost_impact"),
                 fields.get("schedule_impact_days"), try_parse_date(fields.get("date_raised")), fields.get("status", "pending")),
            )
            counts["change_orders"] += 1

        elif doc["doc_type"] in PROGRESS_DOC_TYPES:
            signal = extract_schedule_signal(doc["text"])
            if signal.get("behind_schedule_days"):
                planned_end = conn.execute("SELECT planned_end_date FROM projects WHERE project_id=?", (project_id,)).fetchone()["planned_end_date"]
                conn.execute(
                    "INSERT INTO schedule_items (project_id, task_name, planned_end, slippage_days, note, source_document_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, "Overall project completion", planned_end, signal["behind_schedule_days"], signal.get("note"), doc["document_id"]),
                )
                counts["schedule_signals"] += 1

    conn.commit()
    conn.close()
    print(
        f"Built intelligence store: {counts['documents']} documents, {counts['obligations']} obligations, "
        f"{counts['change_orders']} change orders, {counts['schedule_signals']} schedule signals."
    )


if __name__ == "__main__":
    main()
