# Engineering Intelligence System

### Evidence-backed project intelligence for engineering & infrastructure projects

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-red?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![RAG](https://img.shields.io/badge/Architecture-RAG-purple)](https://en.wikipedia.org/wiki/Retrieval-augmented_generation)

> **Contracts → Evidence → Risk → Impact → Action**

🔗 **[Live Demo](https://engineering-intelligence-zdjtw88udrrzxcj8gv57ny.streamlit.app/)**

---

## Overview

Engineering and infrastructure projects generate large amounts of information across contracts, progress reports, inspection records, change orders, schedules, procurement records, and tender documents.

The challenge is not simply storing this information.

The challenge is connecting it.

A project manager may need to answer questions such as:

- What contractual penalties apply to a delay?
- Which obligations are currently overdue?
- Which activities are slipping against the baseline?
- What change orders are creating commercial exposure?
- What evidence supports a reported project risk?
- What action should be considered next?

The **Engineering Intelligence System (EIS)** is a decision-support application that combines **structured data analysis, document retrieval, natural-language investigation, and evidence-based risk assessment** to answer these questions.

Rather than treating an LLM as a black-box answer generator, the system is designed around a simple principle:

> **Every important conclusion should be traceable back to project evidence.**

---

## Why This Project?

Traditional engineering dashboards are good at showing **what happened**.

Contract repositories are good at storing **what was agreed**.

But project teams often need to connect the two:

```text
What happened?
      ↓
What does the contract say?
      ↓
What is the impact?
      ↓
What requires attention?
      ↓
What should be investigated or acted upon?

The Engineering Intelligence System explores how AI, data analytics, information retrieval, SQL, and structured reasoning can bridge this gap.

Key Capabilities
1. Project Intelligence Dashboard

The system provides a project-level overview containing:

Schedule performance
Contract value
Change-order exposure
Overdue obligations
Current risk level
Key issues requiring attention
Recommended next actions

The objective is to give a project stakeholder a quick understanding of where attention is required without reading every underlying document.

2. Natural-Language Investigation

Users can ask questions directly about a project.

For example:

What penalties apply for delayed civil work?

The system identifies the relevant contractual provisions and presents:

Applicable clauses
Contractual penalties
Stated penalty caps
Supporting evidence
Relevant contractual context
Interpretation caveats where applicable

Instead of returning a generic AI response, the application exposes the underlying evidence used to construct the answer.

3. Hybrid SQL + RAG Architecture

A key design decision was to avoid using an LLM for every question.

Different questions require different forms of reasoning.

Structured Questions

Questions involving:

Counts
Comparisons
Overdue obligations
Change orders
Schedule metrics
Project-level analysis

are handled through the structured project database and SQL analysis.

Unstructured Questions

Questions involving:

Contract clauses
Penalties
Obligations
Contractual language
Source-document evidence

use document retrieval and RAG-based analysis.

The routing architecture is:

                         User Question
                              │
                              ▼
                       Question Router
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
          Structured Query          Document Query
                 │                         │
                 ▼                         ▼
              SQL Layer              RAG Layer
                 │                         │
                 └────────────┬────────────┘
                              ▼
                    Evidence-backed
                       Intelligence

This separation allows deterministic database operations to handle structured facts while retrieval handles contractual and document-based context.

Risk Assessment

The system converts project evidence into structured risk findings across multiple dimensions.

Schedule

Identifies project slippage against the available baseline.

Delivery / Procurement

Highlights material and procurement milestones that may be at risk.

Commercial

Identifies exposure arising from change orders and project variations.

Quality / Compliance

Surfaces issues such as testing gaps, inspection findings, and site compliance concerns.

Contractual

Connects project events to relevant contractual obligations and potential consequences.

Each finding follows a consistent structure:

Risk
 ↓
Evidence
 ↓
Impact
 ↓
Recommended Action

Example:

High · Structural Steel Delivery at Risk

Structural steel fabrication remains incomplete against the contractual delivery milestone.

Evidence: Progress review records

Potential impact: Delay to project activities and contractual delivery exposure

Recommended action: Confirm recovery schedule and delivery plan.

Evidence Traceability

One of the central design goals of the system is traceability.

Instead of:

AI → Answer

the system follows:

Question
   ↓
Retrieved / Structured Evidence
   ↓
Finding
   ↓
Impact
   ↓
Recommendation

Users can inspect the supporting documents and contractual clauses behind an answer or risk finding.

This is particularly important for engineering and contractual use cases where a user needs to understand:

"Where did this conclusion come from?"

Example Project Analysis

The bundled demonstration workspace contains two engineering projects.

Riverside Bridge Widening

The system identifies issues including:

21-day schedule slippage
Structural steel delivery risk
₹68 lakh change-order exposure
Concrete testing below the contractual requirement
Material buffer concerns
Relevant contractual obligations and penalties
Lakeview Water Treatment Plant

The same analytical workflow can be applied to a second project, demonstrating that the system is designed around a reusable project-intelligence workflow rather than being hard-coded around a single project.

Example Investigation

A user asks:

What penalties apply for delayed civil work?

The system retrieves the relevant contract provisions and distinguishes between different contractual delay mechanisms.

Completion Delay

₹8,00,000 per week of delay

Subject to a maximum of 10% of the contract value.

Structural Steel Delivery Delay

₹50,000 per day of delay

Subject to a maximum of 5% of the contract value.

The system also identifies when the retrieved clauses do not establish whether separate contractual penalties are cumulative.

This distinction is important because the application is designed to surface evidence and reasoning rather than make unsupported contractual interpretations.

System Architecture
┌─────────────────────────────────────────────────────────────┐
│                        Streamlit UI                         │
│                                                             │
│  Overview │ Investigate │ Risk Assessment │ Evidence        │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Intelligence Layer                      │
│                                                             │
│  Question Router                                             │
│  SQL Analysis                                                │
│  Document Retrieval                                          │
│  Risk Assessment                                             │
│  Evidence Synthesis                                          │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────┐     ┌───────────────────────────┐
│      Structured Store     │     │      Document Store       │
│                           │     │                           │
│ SQLite                    │     │ Contracts                 │
│ Projects                  │     │ Progress Reports          │
│ Obligations               │     │ Inspection Reports        │
│ Change Orders             │     │ Change Orders             │
│ Schedule Signals          │     │ Tender Documents          │
└───────────────────────────┘     └───────────────────────────┘
                │                             │
                └──────────────┬──────────────┘
                               ▼
                    Evidence-backed Intelligence
Technology Stack
Layer	Technology
Application	Streamlit
Programming	Python
Structured Database	SQLite
Data Processing	Pandas
Retrieval	TF-IDF + Cosine Similarity
Machine Learning Utilities	scikit-learn
LLM	Anthropic Claude
Document Processing	Python / PDF extraction
Version Control	Git + GitHub
Deployment	Streamlit Community Cloud
Project Structure
Engineering-Intelligence-3/
│
├── app.py
│
├── data/
│   ├── db/
│   │   └── engineering_intel.db
│   │
│   └── documents/
│       ├── change_order_riverside_01.txt
│       ├── contract_lakeview_wtp.txt
│       ├── contract_riverside_bridge.txt
│       ├── inspection_report_lakeview.txt
│       ├── inspection_report_riverside.txt
│       ├── minutes_riverside_progress.txt
│       └── tender_riverside_bridge.txt
│
├── scripts/
│   ├── __init__.py
│   ├── demo.py
│   └── seed_db.py
│
├── src/
│   ├── __init__.py
│   ├── analyst_agent.py
│   ├── dates.py
│   ├── db.py
│   ├── extraction.py
│   ├── ingestion.py
│   ├── llm.py
│   ├── query.py
│   ├── rag_agent.py
│   ├── router.py
│   ├── schema.sql
│   ├── sql_agent.py
│   └── vectorstore.py
│
├── .streamlit/
│   └── secrets.toml.example
│
├── requirements.txt
├── README.md
└── REVISION_NOTES.md
Running Locally
1. Clone the repository
git clone https://github.com/VenomLxop/Engineering-Intelligence-3.git
cd Engineering-Intelligence-3
2. Create a virtual environment
Windows
python -m venv .venv
.venv\Scripts\activate
macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
3. Install dependencies
pip install -r requirements.txt
4. Run the application
streamlit run app.py

The application will be available at:

http://localhost:8501
Optional: Claude Integration

The application can operate using its bundled structured and retrieval-based analysis.

When an Anthropic API key is configured, Claude can be used for natural-language synthesis of retrieved evidence.

Create:

.streamlit/secrets.toml

using:

.streamlit/secrets.toml.example

Never commit the actual secrets.toml file or API keys to GitHub.

For Streamlit Community Cloud, configure the required secrets through the application's Secrets settings.

Data Pipeline

The application includes an ingestion workflow that converts project documents into a structured intelligence store.

The pipeline can be summarized as:

Source Documents
      │
      ▼
Document Ingestion
      │
      ▼
Text Extraction
      │
      ▼
Entity / Obligation Extraction
      │
      ├───────────────┐
      ▼               ▼
Structured Store   Retrieval Store
      │               │
      └───────┬───────┘
              ▼
       Project Intelligence

The bundled demonstration database contains structured information extracted from the included project documents.

The database can also be regenerated using the provided project scripts.

python -m scripts.seed_db
Design Principles
Evidence Before Explanation

The system attempts to identify supporting evidence before generating a narrative explanation.

Structured Data Where Possible

Numerical, comparative, and status-based questions are handled through structured data and SQL rather than relying entirely on an LLM.

Retrieval for Contractual Context

Contractual questions require access to the actual language contained in source documents.

Traceability

Findings should be connected to the evidence that supports them.

Human-Readable Output

The application is designed to present:

Finding → Evidence → Impact → Action

rather than exposing internal implementation details to the end user.

Limitations

This is a portfolio/research prototype rather than a production engineering or contract-management platform.

Current limitations include:

The demonstration dataset is intentionally small.
Document extraction quality depends on the source document structure.
Retrieval currently uses TF-IDF rather than neural embeddings.
Risk classification is rule-driven rather than statistically calibrated.
LLM-generated synthesis can require human verification.
The application should not be treated as a substitute for professional engineering, legal, contractual, or financial judgment.
Future Development

Potential extensions include:

Hybrid BM25 + vector retrieval
Neural embeddings
Improved PDF and table extraction
Temporal reasoning over project events
Predictive schedule-risk modelling
Cost-overrun prediction
Contractor performance analytics
Automated contract comparison
Deadline and obligation alerts
Historical project benchmarking
ERP / project-management system integration
Role-specific dashboards for project managers, contract teams, and commercial teams
What I Learned Building This

This project was built around a practical question:

How can AI be used to help engineering teams find what matters without losing the evidence behind the conclusion?

The main challenge was not simply adding an LLM.

It was designing the system so that:

structured facts remain deterministic,
documents remain searchable,
AI synthesis is grounded in retrieved evidence,
risks can be traced to project records,
and the final interface remains understandable to a non-technical user.

The resulting architecture combines data analytics, information retrieval, natural-language processing, SQL, and AI-assisted reasoning into a single project workflow.

Author
Lankeshwar M

Engineering analytics and AI project focused on:

Data Analytics
SQL
Machine Learning
Natural Language Processing
Retrieval-Augmented Generation
AI-assisted Decision Support
Engineering & Infrastructure Analytics
Project Links

Live Application:
https://engineering-intelligence-zdjtw88udrrzxcj8gv57ny.streamlit.app/

Source Code:
https://github.com/VenomLxop/Engineering-Intelligence-3

Disclaimer

This project is intended for demonstration, portfolio, and research purposes.

The outputs generated by the system are decision-support insights and should be independently verified before being used for engineering, contractual, legal, financial, or operational decisions.
