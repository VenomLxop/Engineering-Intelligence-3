from .router import classify_intent
from .rag_agent import answer_with_rag
from .sql_agent import answer_with_sql


def ask(question: str, project_name: str | None = None) -> dict:
    routing = classify_intent(question)
    intent = routing.get("intent", "rag")
    if intent == "sql":
        result = answer_with_sql(question, project_name=project_name)
        return {"intent": "sql", "routing_reason": routing.get("reason"), **result}
    result = answer_with_rag(question, project_name=project_name)
    return {"intent": "rag", "routing_reason": routing.get("reason"), **result}
