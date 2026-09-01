"""Single LLM entry point.

The application can run with Claude when ANTHROPIC_API_KEY is configured.  When it
isn't, the fallback is intentionally called *demo mode* and still produces useful,
source-grounded answers from deterministic rules.  User-facing code should never
expose implementation details such as "mock-llm" or environment-variable hints.
"""
import json
import os
import re
from typing import Any


def llm_mode() -> str:
    return "live" if bool(os.environ.get("ANTHROPIC_API_KEY")) else "demo"


def model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


class RealLLM:
    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self.client.messages.create(
            model=model_name(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class MockLLM:
    """Deterministic offline fallback used for the bundled demo dataset.

    It deliberately returns useful, grounded content instead of exposing a
    developer-only placeholder.  It is not presented as equivalent to Claude.
    """

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        if "Extract every distinct contractual obligation" in system:
            return self._mock_extraction(user)
        if "classify the user's question" in system:
            return self._mock_intent(user)
        if "read-only SQLite SELECT" in system:
            return self._mock_sql(user)
        if "answer questions about engineering" in system.lower():
            return self._mock_rag_answer(user)
        if "analytics assistant" in system.lower() or "synthesize" in system.lower() or "construction project risk analyst" in system.lower():
            return self._mock_synthesis(user)
        return "I couldn't produce a grounded answer from the available project evidence."

    def _mock_rag_answer(self, prompt: str) -> str:
        question, _, sources = prompt.partition("\n\nSource chunks:")
        q = question.lower()
        source_text = sources.lower()

        if "penalt" in q and "delay" in q:
            matches = re.findall(
                r".{0,100}(?:penalty|liquidated damages).{0,180}",
                sources,
                flags=re.I | re.S,
            )
            if matches:
                return "\n".join(f"- {m.strip()}" for m in matches[:3])

        if "material" in q and "deliver" in q:
            matches = re.findall(r".{0,80}shall.{0,220}(?:deliver|supply).{0,160}", sources, flags=re.I | re.S)
            if matches:
                return "\n".join(f"- {m.strip()}" for m in matches[:3])

        # Compact grounded fallback: surface the most relevant source text.
        blocks = [b.strip() for b in sources.split("---") if b.strip()]
        if blocks:
            excerpt = re.sub(r"\s+", " ", blocks[0])
            excerpt = re.sub(r"^\[[^\]]+\]\s*\([^\n]+\)\s*", "", excerpt)
            return f"- {excerpt[:420]}"
        return "No relevant project evidence was found for this question."

    def _mock_extraction(self, text: str) -> str:
        """Conservative extraction of actual duties, not every sentence containing 'shall'."""
        results: list[dict[str, Any]] = []
        sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
        for sent in sentences:
            low = sent.lower()
            if not re.search(r"\b(?:shall|must|is required to)\b", low):
                continue
            # Consequence-only sentences are not separate obligations.
            if re.match(r"^(in the event|should the contractor|failure to|delay beyond|any fatal)", low):
                continue
            duty_match = re.search(
                r"(?:The Contractor|Contractor|The Employer|Employer|Authority|Bidder|Bidders)\s+(?:shall|must)\s+(.+)",
                sent,
                re.I,
            )
            if not duty_match:
                continue
            action = duty_match.group(1).strip().rstrip(".")
            deadline = None
            m = re.search(
                r"(?:by|before|no later than|within)\s+([A-Z][a-z]+ \d{1,2}(?:,? \d{4})?|\d+\s+(?:working\s+)?days?(?: of [^.]+)?)",
                sent,
            )
            if m:
                deadline = m.group(1)
            penalty = None
            pm = re.search(
                r"(?:penalty|liquidated damages)[^.;]*(?:₹|INR)\s*[\d,]+(?:\.\d+)?[^.;]*",
                sent,
                re.I,
            )
            if pm:
                penalty = pm.group(0).strip()
            results.append({
                "obligation": action[:300],
                "responsible_party": "Contractor" if "contractor" in low else None,
                "deadline": deadline,
                "penalty": penalty,
                "confidence": 0.86,
            })
        return json.dumps({"obligations": results[:8]})

    def _mock_intent(self, question: str) -> str:
        analytic_markers = [
            "how many", "more than", "count", "which contractors", "overdue",
            "average", "total", "list all", "compare", "highest", "lowest", "sum",
        ]
        is_sql = any(m in question.lower() for m in analytic_markers)
        return json.dumps({"intent": "sql" if is_sql else "rag", "reason": "question shape"})

    def _mock_sql(self, prompt: str) -> str:
        q = prompt.lower()
        project_filter = ""
        if "lakeview" in q:
            project_filter = " AND p.name = 'Lakeview Water Treatment Plant'"
        elif "riverside" in q:
            project_filter = " AND p.name = 'Riverside Bridge Widening'"
        if "overdue" in q and "contractor" in q:
            return (
                "SELECT c.name AS contractor, COUNT(*) AS overdue_count "
                "FROM obligations o JOIN contracts ct ON o.contract_id=ct.contract_id "
                "JOIN projects p ON ct.project_id=p.project_id "
                "JOIN companies c ON o.responsible_company_id=c.company_id "
                "WHERE o.status='overdue'" + project_filter + " GROUP BY c.name ORDER BY overdue_count DESC;"
            )
        if "overdue" in q and "obligation" in q:
            return (
                "SELECT c.name AS contractor, o.description, o.deadline, cl.clause_ref "
                "FROM obligations o JOIN contracts ct ON o.contract_id=ct.contract_id "
                "JOIN projects p ON ct.project_id=p.project_id "
                "LEFT JOIN companies c ON o.responsible_company_id=c.company_id "
                "LEFT JOIN clauses cl ON o.clause_id=cl.clause_id "
                "WHERE o.status='overdue'" + project_filter + " ORDER BY o.deadline;"
            )
        if "how many" in q and "obligation" in q:
            return "SELECT COUNT(*) AS obligation_count FROM obligations;"
        return "SELECT name FROM projects ORDER BY name;"

    def _mock_synthesis(self, prompt: str) -> str:
        # Ground the fallback in actual result rows.
        rows_match = re.search(r"Result rows:\s*(.+)", prompt, re.S)
        rows_text = rows_match.group(1).strip() if rows_match else "[]"
        if rows_text in ("[]", ""):
            return "No matching records were found in the project data."
        import ast
        try:
            rows = ast.literal_eval(rows_text)
        except (ValueError, SyntaxError):
            rows = []
        if rows and isinstance(rows, list) and isinstance(rows[0], dict):
            if "contractor" in rows[0] and "overdue_count" in rows[0]:
                parts = [f"{r['contractor']}: {r['overdue_count']} overdue obligations" for r in rows]
                return " · ".join(parts)
            if "description" in rows[0]:
                return "The matching overdue obligations are listed in the table below."
        return "Matching records were found in the project data."


def get_llm():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    return RealLLM(api_key) if api_key else MockLLM()
