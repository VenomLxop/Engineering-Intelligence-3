# Engineering Intelligence & Decision Support System

Converts unstructured engineering/project documents (contracts, tenders, specs, inspection
reports, meeting minutes, change orders, invoices, technical reports) into structured, queryable
business intelligence — and lets an "Analyst Agent" chain retrieval + analytics into a
traceable, evidence-backed risk assessment.

Not "chat with your documents." Two distinct query paths, routed automatically:

- **RAG path** — "What are the contractor's obligations related to material delivery?"
  → retrieves the relevant clause(s), extracts the specific answer, cites the clause.
- **SQL path** — "Which contractors have more than three overdue obligations?"
  → no single passage answers this. The system writes and runs a constrained, read-only SQL
  query against the structured store that the extraction pipeline populated.

## Architecture

```
Document (pdf/txt) → chunk (clause-aware) → embed (TF-IDF index)
                                          → LLM extraction → structured rows in SQLite
                                             (obligations, deadlines, penalties, clauses,
                                              change orders, schedule, risks)

User question → intent router → RAG (retrieve + extract answer + cite)
                              → SQL (NL→SQL, read-only, execute, synthesize)

Analyst Agent (pinned multi-step pipeline, not a free tool loop — reproducible & auditable):
  query overdue obligations → query schedule slippage → query change orders
  → retrieve relevant clauses → LLM synthesizes a structured, evidence-cited risk summary
```

Every extracted fact carries a `confidence` score and a foreign key back to the exact chunk/
clause it came from — nothing in an answer is untraceable to a source document.

## Project layout

```
src/
  schema.sql       structured store: projects, contracts, companies, clauses, obligations,
                   deadlines, penalties, change_orders, schedule_items, risks
  db.py            SQLite access + a hard SELECT-only guard for the SQL agent
  llm.py           single choke point for all model calls (see "Running without an API key")
  ingestion.py     pdf/txt loading + clause-aware chunking + doc-type guessing
  extraction.py    unstructured chunk -> structured obligation JSON (with confidence)
  vectorstore.py   TF-IDF retrieval (swap for a real embedding model via the same interface)
  router.py        RAG-vs-SQL intent classification
  rag_agent.py     retrieval + extraction-style answer + citations
  sql_agent.py     NL -> read-only SQL -> execution -> grounded synthesis
  analyst_agent.py the multi-step risk assessment pipeline
  query.py         top-level ask() entrypoint (router + both paths)
scripts/
  seed_db.py       ingest data/documents/, extract obligations, seed schedule/status data
  demo.py          runs one RAG query, one SQL query, one risk assessment
data/documents/     sample contracts/tenders/inspection reports/minutes/change orders
```

## Running it

```bash
pip install -r requirements.txt
python -m scripts.seed_db      # ingest + extract + build the SQLite DB
python -m scripts.demo         # runs all three query types in the terminal
streamlit run app.py           # interactive UI: ask questions, run risk assessments, browse data
```

The Streamlit app (`app.py`) has three tabs — **Ask a question** (routed to RAG or SQL, with
sources/SQL shown), **Risk Assessment** (runs the Analyst Agent for a chosen project, with
evidence tables), and **Browse data** (the extracted obligations/documents as sortable tables).
Its sidebar shows whether you're in mock mode or connected to the real API, and has a button to
re-run ingestion after you drop new documents into `data/documents/` — no terminal needed once
it's running.

Interactive (no UI):
```python
from src.query import ask
ask("What penalties apply if the contractor delays structural steel delivery?")
```

## Running without an API key (offline mode)

`src/llm.py` is the only place that talks to a model. If `ANTHROPIC_API_KEY` is unset, it falls
back to `MockLLM` — a regex/heuristic stand-in that answers the *same prompts* the real model
gets, just with pattern matching instead of reasoning. This means the full pipeline — ingestion,
chunking, extraction, routing, SQL generation, retrieval — runs and is inspectable end-to-end
with zero credentials. Extraction/answer *quality* with the mock is intentionally weak; it exists
to prove the architecture, not to replace the real model. Set the key for real results:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m scripts.seed_db
```

## Sample data — and how to use real documents instead

The documents in `data/documents/` are synthetic, but their clause structure and terminology
(performance guarantees, EMD, liquidated damages, IS-code references, NIT format) are modeled
on real Indian public-works tender/contract conventions. Ingestion is **zero-config**: drop new
`.txt` or `.pdf` files into `data/documents/` and rerun `python -m scripts.seed_db` — no manual
project/party mapping needed. Each document is read for its own project/party/contract metadata
(`extract_document_metadata` in `extraction.py`), projects and companies are created on first
mention and matched by name (with fuzzy word-overlap matching so "Riverside Bridge Widening" and
"Widening of Riverside Bridge" resolve to the same project rather than duplicating it), and
obligation `overdue` status is computed generically by comparing each extracted deadline against
the latest document date seen across the corpus — not by hardcoded per-project keyword rules.

Known mock-mode limitation: `MockLLM`'s metadata extractor is a label:value regex (`Project:`,
`Contractor:`, etc.) and won't parse a document that describes its project in a full sentence
instead of a header field, or a deadline given as a duration ("18 months from award") rather than
an absolute date. The real model handles both without any code changes — this is exactly the
kind of judgment call mock mode can't make.

Real, publicly downloadable Indian government contract/tender documents you can use directly
(not fetchable from this sandbox's network allowlist, but downloadable by you):
- NHAI standard bid documents: `https://nhai.gov.in/nhai/sites/default/files/2020/RFP_10_1.pdf`
- NHAI EPC agreement: `https://www.mea.gov.in/Portal/Tender/3025_1/4_4._DCA_RFP_Vol-II-1.pdf`
- CPWD General Conditions of Contract 2019: `https://www.cpwd.gov.in/Publication/GCC_Construction_2019.pdf`

Your own Unilever/Jain Housing/CERN materials (redacted as needed) would work just as well and
make for a much stronger demo story than synthetic docs.

## What to build next (if you want to push this further for FischerJordan-level polish)

- Swap `TfidfRetriever` for a real embedding model once you have API/model access.
- Turn `analyst_agent.py` from a pinned pipeline into a constrained tool-calling loop once you
  want the agent to decide *which* evidence to gather rather than always gathering all of it.
- The mock-mode metadata extractor is a regex over `Field: value` headers — a real document set
  with varied phrasing will need the real model (already wired in, just needs the API key).
