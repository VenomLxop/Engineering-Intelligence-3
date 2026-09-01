"""Natural-language analytics over the read-only SQLite store."""
from .db import run_readonly_sql, get_schema_description
from .llm import get_llm

SQL_SYSTEM_PROMPT = """You write a single read-only SQLite SELECT query to answer the user's question.

Schema:
{schema}

Rules:
- Output ONLY the SQL statement.
- SELECT only. Never mutate data.
- Prefer explicit columns and clear JOINs.
- If a project context is supplied, restrict the query to that project unless the user explicitly asks for all projects.
- Do not expose internal implementation details in the final answer."""

SYNTHESIS_SYSTEM_PROMPT = """You are an engineering analytics assistant. Answer the user's question using only the SQL result rows. Be short, direct and factual. Use human-readable numbers. If no rows were returned, say that no matching records were found. Do not mention the SQL engine or internal implementation."""


def answer_with_sql(question: str, project_name: str | None = None) -> dict:
    schema = get_schema_description()
    llm = get_llm()
    context = project_name if project_name and project_name != "All projects" else "All projects"
    prompt = SQL_SYSTEM_PROMPT.format(schema=schema) + f"\n\nProject context: {context}\nQuestion: {question}"
    sql = llm.complete(prompt, f"Project context: {context}\nQuestion: {question}", max_tokens=350).strip()
    if sql.startswith("```"):
        sql = sql.strip("`").replace("sql\n", "", 1).strip()

    try:
        rows = run_readonly_sql(sql)
        error = None
    except Exception as e:  # noqa: BLE001
        rows, error = [], str(e)

    synthesis_input = f"Question: {question}\nProject context: {context}\nResult rows: {rows[:50]}"
    if error:
        synthesis_input += f"\nExecution error: {error}"
    answer = llm.complete(SYNTHESIS_SYSTEM_PROMPT, synthesis_input, max_tokens=500)
    return {"answer": answer, "sql": sql, "rows": rows, "error": error}
