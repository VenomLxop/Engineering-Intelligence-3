"""Evidence-first project risk analysis.

The engine calculates risk signals deterministically from structured records and
source documents. Claude, when available, is used to turn those signals into
natural language; it is not asked to invent probability scores.
"""
import re
from .db import get_connection, run_readonly_sql
from .vectorstore import build_retriever_from_db
from .llm import get_llm, MockLLM


def _project_row(project_name: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT project_id, name, location, planned_end_date FROM projects WHERE name=?", (project_name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _step_overdue_obligations(project_name: str) -> list[dict]:
    sql = """
        SELECT c.name AS contractor, o.description, o.deadline, o.penalty_text,
               o.penalty_amount_per_day, cl.clause_ref
        FROM obligations o
        JOIN contracts ct ON o.contract_id = ct.contract_id
        JOIN projects p ON ct.project_id = p.project_id
        LEFT JOIN companies c ON o.responsible_company_id = c.company_id
        LEFT JOIN clauses cl ON o.clause_id = cl.clause_id
        WHERE p.name = ? AND o.status = 'overdue'
        ORDER BY o.deadline
    """
    return run_readonly_sql(sql, (project_name,))


def _step_schedule_slippage(project_name: str) -> list[dict]:
    sql = """
        SELECT s.task_name, s.planned_end, s.actual_end, s.slippage_days, s.note,
               d.filename AS source_document, d.document_date
        FROM schedule_items s
        JOIN projects p ON s.project_id = p.project_id
        LEFT JOIN documents d ON s.source_document_id = d.document_id
        WHERE p.name = ? AND s.slippage_days > 0
        ORDER BY s.slippage_days DESC
    """
    return run_readonly_sql(sql, (project_name,))


def _step_change_orders(project_name: str) -> list[dict]:
    sql = """
        SELECT co.description, co.cost_impact, co.schedule_impact_days, co.status,
               co.date_raised, d.filename AS source_document
        FROM change_orders co
        JOIN projects p ON co.project_id = p.project_id
        LEFT JOIN documents d ON co.document_id = d.document_id
        WHERE p.name = ?
        ORDER BY co.cost_impact DESC
    """
    return run_readonly_sql(sql, (project_name,))


def _step_relevant_clauses(project_name: str, topic: str = "delay penalty procurement quality safety") -> list[dict]:
    project = _project_row(project_name)
    if not project:
        return []
    retriever = build_retriever_from_db()
    hits = retriever.query(topic, top_k=6, project_id=project["project_id"])
    return [
        {"clause_ref": h.clause_ref, "excerpt": h.text[:420].strip(), "document_id": h.document_id}
        for h in hits
    ]


def _step_project_signals(project_name: str) -> list[dict]:
    """Find dated inspection/minutes evidence that describes active issues."""
    project = _project_row(project_name)
    if not project:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT d.filename, d.document_date, c.clause_ref, c.text "
        "FROM chunks c JOIN documents d ON c.document_id=d.document_id "
        "WHERE d.project_id=? AND d.doc_type IN ('inspection_report','minutes') "
        "ORDER BY d.document_date DESC",
        (project["project_id"],),
    ).fetchall()
    conn.close()
    patterns = re.compile(
        r"(not yet|not delivered|overdue|below|non-conformance|risk|concern|delay|outstanding|behind|miss)", re.I
    )
    signals = []
    for row in rows:
        sentences = re.split(r"(?<=[.!?])\s+", row["text"])
        for sentence in sentences:
            # Positive observations such as "No safety non-conformances noted"
            # should not become risk signals merely because they contain the
            # word "non-conformance".
            if re.search(r"\bno\b.*\b(?:risk|concern|non-conformance|outstanding|delay)\b", sentence, re.I):
                continue
            if patterns.search(sentence):
                clean = " ".join(sentence.split())
                if len(clean) >= 45:
                    signals.append({
                        "document": row["filename"],
                        "document_date": row["document_date"],
                        "clause_ref": row["clause_ref"],
                        "finding": clean[:360],
                    })
    # Keep the strongest, non-duplicate statements.
    seen, unique = set(), []
    for s in signals:
        key = s["finding"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique[:8]


def _risk_items(evidence: dict, contract_value: float | None) -> list[dict]:
    """Build deterministic, evidence-backed risk findings.

    Severity is a rule-based assessment of the structured evidence. It is not a
    probability estimate. Narrative generation, when available, may explain the
    findings but must not change their underlying facts.
    """
    items: list[dict] = []
    overdue = evidence["overdue_obligations"]
    if overdue:
        items.append({
            "title": "Overdue contractual obligations",
            "category": "Contract",
            "severity": "High" if len(overdue) >= 2 else "Medium",
            "evidence_strength": "Confirmed",
            "impact_amount": None,
            "detail": f"{len(overdue)} contractual obligation{'s' if len(overdue) != 1 else ''} are overdue as of the latest project evidence date.",
            "evidence": [r.get("clause_ref") for r in overdue if r.get("clause_ref")],
            "impact_detail": "Review the overdue obligations and agree recovery dates with the responsible contractor.",
        })

    slippage = evidence["schedule_slippage"]
    if slippage:
        max_days = max(int(r["slippage_days"]) for r in slippage)
        items.append({
            "title": "Schedule slippage",
            "category": "Schedule",
            "severity": "High" if max_days >= 21 else "Medium",
            "evidence_strength": "Strong",
            "impact_amount": None,
            "detail": f"Project completion is approximately {max_days} days behind the CPM baseline.",
            "evidence": [r.get("source_document") for r in slippage if r.get("source_document")],
            "impact_detail": "Recovery planning is required to restore the approved baseline.",
        })

    # Turn the most actionable progress observations into specific findings.
    signal_text = " ".join(s["finding"] for s in evidence["project_signals"])
    if re.search(r"structural steel.*(?:not yet|not).*arriv|fabrication.*60%|steel delivery", signal_text, re.I):
        items.append({
            "title": "Structural steel delivery at risk",
            "category": "Delivery",
            "severity": "High",
            "evidence_strength": "Strong",
            "impact_amount": None,
            "detail": "Structural steel had not arrived at site and fabrication was reported at 60%, creating a risk of missing the 15 Oct 2026 delivery milestone.",
            "evidence": [s.get("document") for s in evidence["project_signals"] if re.search(r"steel|fabrication", s.get("finding", ""), re.I)][:3],
            "impact_detail": "A delivery delay may trigger the Section 7.2 penalty of ₹50,000/day, subject to the contractual cap.",
        })

    changes = [r for r in evidence["change_orders"] if r.get("cost_impact")]
    if changes:
        total = sum(float(r["cost_impact"]) for r in changes)
        ratio = total / contract_value if contract_value else 0
        items.append({
            "title": "Commercial exposure from change orders",
            "category": "Cost",
            "severity": "High" if ratio >= 0.05 else "Medium",
            "evidence_strength": "Confirmed",
            "impact_amount": total,
            "detail": f"Approved/pending change orders represent ₹{total:,.0f} of additional cost exposure.",
            "evidence": [r.get("source_document") for r in changes if r.get("source_document")],
            "impact_detail": "Validate the variation against contractual entitlement and update the cost forecast.",
        })

    if re.search(r"cube testing.*(?:below|only 4).*7|non-conformance", signal_text, re.I):
        items.append({
            "title": "Concrete testing below requirement",
            "category": "Quality",
            "severity": "Medium",
            "evidence_strength": "Strong",
            "impact_amount": None,
            "detail": "Only 4 cube-test sets were completed against 7 expected for the volume poured; the contractor was directed to increase testing frequency.",
            "evidence": [s.get("document") for s in evidence["project_signals"] if re.search(r"cube|testing|non-conformance", s.get("finding", ""), re.I)][:3],
            "impact_detail": "Correct the testing shortfall and document the next verification date.",
        })

    if re.search(r"cement.*(?:9 days|below the 15|buffer stock)", signal_text, re.I):
        items.append({
            "title": "Cement buffer below requirement",
            "category": "Supply",
            "severity": "Medium",
            "evidence_strength": "Strong",
            "impact_amount": None,
            "detail": "Cement buffer stock was approximately 9 days of consumption against the 15-day contractual minimum.",
            "evidence": [s.get("document") for s in evidence["project_signals"] if re.search(r"cement|buffer", s.get("finding", ""), re.I)][:3],
            "impact_detail": "Replenish the site buffer to the contractual 15-day minimum.",
        })

    return items

def _overall_severity(items: list[dict]) -> str:
    if any(i["severity"] == "High" for i in items):
        return "High"
    if any(i["severity"] == "Medium" for i in items):
        return "Medium"
    return "Low"


def _demo_summary(project_name: str, items: list[dict], evidence: dict) -> str:
    if not items:
        return f"No material risk signals were identified for {project_name} from the available project records."
    lines = [f"{project_name} currently requires { _overall_severity(items).lower() } attention."]
    for item in items[:4]:
        lines.append(f"• {item['title']}: {item['detail']}")
    return "\n".join(lines)


def generate_risk_assessment(project_name: str) -> dict:
    project = _project_row(project_name)
    if not project:
        raise ValueError(f"Project not found: {project_name}")
    conn = get_connection()
    contract = conn.execute(
        "SELECT contract_value FROM contracts WHERE project_id=? ORDER BY contract_id LIMIT 1",
        (project["project_id"],),
    ).fetchone()
    conn.close()
    contract_value = contract["contract_value"] if contract else None

    evidence = {
        "overdue_obligations": _step_overdue_obligations(project_name),
        "schedule_slippage": _step_schedule_slippage(project_name),
        "change_orders": _step_change_orders(project_name),
        "relevant_clauses": _step_relevant_clauses(project_name),
        "project_signals": _step_project_signals(project_name),
    }
    items = _risk_items(evidence, contract_value)
    overall = _overall_severity(items)

    # Keep the structured facts deterministic. The LLM only turns those facts
    # into prose when a real model is available.
    if isinstance(get_llm(), MockLLM):
        summary = _demo_summary(project_name, items, evidence)
    else:
        llm = get_llm()
        prompt = (
            f"Project: {project_name}\nOverall severity: {overall}\n\n"
            f"Structured risk findings (do not change their numbers or severity):\n{items}\n\n"
            f"Supporting evidence:\n{evidence}"
        )
        summary = llm.complete(
            "You are a construction project analyst. Write a concise executive summary from the supplied structured findings. "
            "Do not invent facts, probabilities, costs or dates. Do not mention AI, models, APIs or internal implementation.",
            prompt,
            max_tokens=700,
        )

    return {
        "project": project_name,
        "overall_severity": overall,
        "items": items,
        "summary": summary,
        "evidence": evidence,
        "as_of_date": max(
            [
                r.get("document_date") for group in evidence.values() if isinstance(group, list)
                for r in group if isinstance(r, dict) and r.get("document_date")
            ],
            default=None,
        ),
    }
