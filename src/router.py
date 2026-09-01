"""Routes a user question to the semantic-retrieval (RAG) path or the
structured-analytics (SQL) path. This is what separates this system
from a plain 'chat with your documents' RAG demo: aggregate/comparative
questions ('which contractors have more than 3 overdue obligations')
have no single answering passage -- they need the SQL layer."""
import json
from .llm import get_llm

ROUTER_SYSTEM_PROMPT = """You are a query router for an engineering-documents intelligence system. \
Given the user's question, classify the user's question as either:
- "rag": answerable by finding and reading specific clauses/passages in documents
- "sql": needs aggregation, counting, filtering, or comparison across structured records
  (obligations, deadlines, penalties, change orders, risks, contractors, projects)

Return ONLY JSON: {"intent": "rag" or "sql", "reason": "<one short sentence>"}"""


def classify_intent(question: str) -> dict:
    llm = get_llm()
    raw = llm.complete(ROUTER_SYSTEM_PROMPT, question, max_tokens=100)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {"intent": "rag", "reason": "fallback: could not parse router output"}
