import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.query import ask
from src.analyst_agent import generate_risk_assessment


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def demo_query(question):
    result = ask(question)
    print(f"\nQ: {question}")
    print(f"[routed to: {result['intent']} | reason: {result.get('routing_reason')}]")
    if result["intent"] == "sql":
        print(f"SQL: {result['sql']}")
        print(f"Rows: {json.dumps(result['rows'], indent=2)[:800]}")
    else:
        print("Sources:")
        for s in result["sources"]:
            print(f"  - {s['clause_ref']} ({s['document']}, relevance {s['relevance']})")
    print(f"\nAnswer:\n{result['answer']}")


if __name__ == "__main__":
    section("1. RAG query -- clause lookup")
    demo_query("What are the contractor's obligations related to material delivery?")

    section("2. SQL query -- cross-contractor analytics")
    demo_query("Which contractors have more than three overdue obligations?")

    section("3. Analyst Agent -- structured risk assessment")
    result = generate_risk_assessment("Lakeview Water Treatment Plant")
    print(result["summary"])
    print("\n--- Evidence used ---")
    print(json.dumps(result["evidence"], indent=2)[:1500])
