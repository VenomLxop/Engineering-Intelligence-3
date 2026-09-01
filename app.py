"""Engineering Intelligence — decision-support interface."""
import contextlib
import io
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

# Streamlit Cloud secrets -> environment, so the same LLM path works locally and in deployment.
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    if "ANTHROPIC_MODEL" in st.secrets:
        os.environ["ANTHROPIC_MODEL"] = st.secrets["ANTHROPIC_MODEL"]
except (FileNotFoundError, KeyError):
    pass

from src.db import DB_PATH, get_connection
from src.llm import llm_mode, model_name
from src.query import ask
from src.analyst_agent import generate_risk_assessment

st.set_page_config(
    page_title="Engineering Intelligence",
    page_icon="▦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Visual system: quiet, information-dense, deliberately not "AI SaaS".
st.markdown(
    """
<style>
    :root { --accent: #ff4b4b; --muted: #9aa0aa; --panel: #17191f; --line: #2a2d35; }
    .block-container { max-width: 1320px; padding-top: 2.2rem; padding-bottom: 4rem; }
    h1, h2, h3 { letter-spacing: -0.025em; }
    h1 { font-size: 2.15rem !important; }
    h2 { font-size: 1.45rem !important; margin-top: 1.8rem !important; }
    h3 { font-size: 1.05rem !important; }
    [data-testid="stSidebar"] { border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] .block-container { padding-top: 1.7rem; }
    .eyebrow { color: #aeb3bd; font-size: .76rem; text-transform: uppercase; letter-spacing: .12em; margin-bottom: .45rem; }
    .hero-copy { color: #aeb3bd; max-width: 820px; font-size: .98rem; line-height: 1.6; }
    .status-line { color: #aeb3bd; font-size: .84rem; padding: .55rem .75rem; border: 1px solid var(--line); border-radius: 8px; }
    .status-live { color: #8ee2ae; }
    .status-demo { color: #d7b36a; }
    .metric-label { color: #9da2ad; font-size: .76rem; text-transform: uppercase; letter-spacing: .08em; }
    .metric-value { font-size: 1.55rem; font-weight: 650; margin-top: .15rem; }
    .metric-sub { color: #8e949f; font-size: .78rem; margin-top: .15rem; }
    .metric-box { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.05rem; min-height: 104px; }
    .finding { background: transparent; border-bottom: 1px solid var(--line); padding: .9rem .15rem 1rem; margin-bottom: .25rem; }
    .finding-title { font-weight: 650; margin-bottom: .3rem; }
    .finding-detail { color: #b0b5be; line-height: 1.55; font-size: .9rem; }
    .severity-high { color: #ff7474; }
    .severity-medium { color: #e0b766; }
    .severity-low { color: #8ec9a1; }
    .source-card { background: #14161b; border-left: 2px solid #4c5059; padding: .8rem 1rem; margin: .55rem 0; border-radius: 0 7px 7px 0; }
    .answer-lead { font-size: 1.02rem; line-height: 1.7; }
    .impact-line { color: #c3c7cf; font-size: .86rem; margin-top: .35rem; }
    .evidence-line { color: #8e949f; font-size: .8rem; margin-top: .2rem; }
    .source-ref { font-weight: 650; }
    .source-doc { color: #9298a3; font-size: .8rem; }
    .small-note { color: #8e949f; font-size: .8rem; }
    .action-list li { margin-bottom: .5rem; }
    .project-chip { color: #b6bbc4; font-size: .82rem; }
    div[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); padding: .85rem 1rem; border-radius: 10px; }
    div[data-testid="stMetricLabel"] { color: #9da2ad; }
    button[kind="primary"] { border-radius: 7px; }
</style>
""",
    unsafe_allow_html=True,
)


def db_exists() -> bool:
    return os.path.exists(DB_PATH)


def run_ingestion(uploaded_files=None) -> tuple[bool, str]:
    """Persist optional uploads and rebuild the local intelligence store."""
    if uploaded_files:
        docs_dir = os.path.join(os.path.dirname(__file__), "data", "documents")
        os.makedirs(docs_dir, exist_ok=True)
        for uploaded in uploaded_files:
            safe_name = os.path.basename(uploaded.name).replace("..", "_")
            with open(os.path.join(docs_dir, safe_name), "wb") as f:
                f.write(uploaded.getbuffer())

    from scripts import seed_db
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            seed_db.main()
        return True, buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def get_projects() -> list[str]:
    if not db_exists():
        return []
    conn = get_connection()
    rows = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def project_snapshot(project: str) -> dict:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT p.project_id, p.name, p.location, p.planned_end_date,
               c.name AS contractor, ct.contract_value,
               MAX(d.document_date) AS as_of_date
        FROM projects p
        LEFT JOIN contracts ct ON ct.project_id=p.project_id
        LEFT JOIN companies c ON c.company_id=ct.contractor_company_id
        LEFT JOIN documents d ON d.project_id=p.project_id
        WHERE p.name=?
        GROUP BY p.project_id
        """, (project,)
    ).fetchone()
    if not row:
        conn.close()
        return {}
    project_id = row["project_id"]
    overdue = conn.execute(
        "SELECT COUNT(*) AS n FROM obligations WHERE contract_id IN (SELECT contract_id FROM contracts WHERE project_id=?) AND status='overdue'",
        (project_id,),
    ).fetchone()["n"]
    open_obligations = conn.execute(
        "SELECT COUNT(*) AS n FROM obligations WHERE contract_id IN (SELECT contract_id FROM contracts WHERE project_id=?) AND status='open'",
        (project_id,),
    ).fetchone()["n"]
    change_cost = conn.execute(
        "SELECT COALESCE(SUM(cost_impact),0) AS v FROM change_orders WHERE project_id=?", (project_id,)
    ).fetchone()["v"]
    schedule = conn.execute(
        "SELECT COALESCE(MAX(slippage_days),0) AS d FROM schedule_items WHERE project_id=?", (project_id,)
    ).fetchone()["d"]
    docs = conn.execute("SELECT COUNT(*) AS n FROM documents WHERE project_id=?", (project_id,)).fetchone()["n"]
    conn.close()
    result = dict(row)
    result.update(overdue_count=overdue, open_obligations=open_obligations, change_cost=change_cost, slippage_days=schedule, document_count=docs)
    return result


def money(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    if abs(value) >= 10_000_000:
        return f"₹{value / 10_000_000:.1f} Cr"
    if abs(value) >= 100_000:
        return f"₹{value / 100_000:.1f} L"
    return f"₹{value:,.0f}"


def human_date(value) -> str:
    if value is None or pd.isna(value):
        return "—"

    try:
        value = str(value)
        return datetime.fromisoformat(value).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(value)

def get_obligations_df(project: str | None) -> pd.DataFrame:
    conn = get_connection()
    query = """
        SELECT p.name AS project, c.name AS contractor, o.description, o.deadline,
               o.penalty_text, o.status, cl.clause_ref
        FROM obligations o
        JOIN contracts ct ON o.contract_id = ct.contract_id
        JOIN projects p ON ct.project_id = p.project_id
        LEFT JOIN companies c ON o.responsible_company_id = c.company_id
        LEFT JOIN clauses cl ON o.clause_id = cl.clause_id
    """
    params = ()
    if project and project != "All projects":
        query += " WHERE p.name=?"
        params = (project,)
    query += " ORDER BY CASE o.status WHEN 'overdue' THEN 0 ELSE 1 END, o.deadline"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    if not df.empty:
        df["deadline"] = df["deadline"].apply(human_date)
        df["penalty_text"] = df["penalty_text"].fillna("—").apply(lambda x: " ".join(str(x).split()) if str(x).strip() else "—")
        df["status"] = df["status"].str.title()
        df = df.rename(columns={
            "project": "Project", "contractor": "Responsible party", "description": "Obligation",
            "deadline": "Due", "penalty_text": "Contractual consequence", "status": "Status",
            "clause_ref": "Clause",
        })
    return df


def get_documents_df(project: str | None) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT d.filename AS document, d.doc_type AS type, p.name AS project, d.document_date AS date FROM documents d LEFT JOIN projects p ON d.project_id=p.project_id"
    params = ()
    if project and project != "All projects":
        query += " WHERE p.name=?"
        params = (project,)
    query += " ORDER BY d.document_date DESC, d.filename"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    if not df.empty:
        df["date"] = df["date"].apply(human_date)
        df["type"] = df["type"].str.replace("_", " ").str.title()
        df = df.rename(columns={"document": "Document", "type": "Type", "project": "Project", "date": "Document date"})
    return df


def recommendations(items: list[dict]) -> list[str]:
    actions = []
    for item in items:
        title = item["title"].lower()
        if "schedule" in title:
            actions.append("Review the recovery schedule and confirm the path back to the approved CPM baseline.")
        elif "structural steel" in title:
            actions.append("Review the extension request against Section 7.2 and require a written recovery plan before the 15 Oct delivery milestone.")
        elif "change order" in title or "commercial" in title:
            actions.append("Validate the approved variation against Section 14.2 and update the cost forecast for the ₹68L exposure.")
        elif "overdue" in title:
            actions.append("Escalate overdue obligations with the responsible contractor and assign recovery dates.")
        elif "concrete testing" in title:
            actions.append("Increase cube-testing frequency to the contractual requirement and record the next verification date.")
        elif "cement" in title:
            actions.append("Replenish cement buffer stock to the contractual 15-day minimum by the agreed recovery date.")
    return list(dict.fromkeys(actions))[:4]


# -----------------------------------------------------------------------------
# First-run setup. Keep it quiet: no logs, no database paths, no developer jargon.
if not db_exists():
    with st.spinner("Preparing the project workspace…"):
        success, _ = run_ingestion()
    if not success:
        st.error("The project workspace could not be prepared. Check the document set and try again.")
        st.stop()

projects = get_projects()

# -----------------------------------------------------------------------------
# Sidebar
with st.sidebar:
    st.markdown("### Engineering Intelligence")
    st.caption("Project evidence → risk → action")
    mode = llm_mode()
    if mode == "live":
        st.markdown('<div class="status-line status-live">● AI analysis ready</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-line status-demo">● Demo analysis mode</div>', unsafe_allow_html=True)
        st.caption("The bundled workspace remains fully usable without an external model.")

    st.markdown("\n")
    selected_project = st.selectbox("Project", ["All projects"] + projects)

    with st.expander("Documents", expanded=False):
        st.caption("Add PDF or TXT project records to rebuild the intelligence store.")
        uploads = st.file_uploader("Upload documents", type=["pdf", "txt", "md"], accept_multiple_files=True, label_visibility="collapsed")
        if st.button("Process documents", disabled=not uploads, use_container_width=True):
            with st.spinner("Processing documents…"):
                ok, _ = run_ingestion(uploads)
            if ok:
                st.success("Workspace updated.")
                st.rerun()
            st.error("The documents could not be processed.")

    with st.expander("Analysis details", expanded=False):
        st.caption(f"Mode: {'Live Claude' if mode == 'live' else 'Bundled deterministic demo'}")
        if mode == "live":
            st.caption(f"Model: {model_name()}")
        st.caption(f"Documents indexed: {sum(1 for _ in get_documents_df(None).itertuples())}")

# -----------------------------------------------------------------------------
# Overview
if selected_project == "All projects":
    st.markdown('<div class="eyebrow">Workspace</div>', unsafe_allow_html=True)
    st.title("Engineering Intelligence")
    st.markdown('<div class="hero-copy">Turn contracts, progress records and change orders into a traceable view of what needs attention.</div>', unsafe_allow_html=True)

    st.markdown("## Projects")
    cols = st.columns(min(3, max(1, len(projects))))
    for idx, project in enumerate(projects):
        snap = project_snapshot(project)
        attention = "High attention" if snap["overdue_count"] > 0 or snap["slippage_days"] >= 21 else "Monitoring"
        with cols[idx % len(cols)]:
            st.markdown(
                f'<div class="metric-box"><div class="metric-label">{attention}</div>'
                f'<div class="metric-value">{project}</div>'
                f'<div class="metric-sub">{snap.get("location") or "Project record"} · {snap["document_count"]} source documents</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Open project", key=f"open_{idx}", use_container_width=True):
                st.session_state["project_jump"] = project
                st.rerun()

    st.markdown("## Workspace summary")
    all_snaps = [project_snapshot(p) for p in projects]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects", len(projects))
    c2.metric("Overdue obligations", sum(x["overdue_count"] for x in all_snaps))
    c3.metric("Change-order exposure", money(sum(x["change_cost"] or 0 for x in all_snaps)))
    c4.metric("Latest project evidence", max((human_date(x["as_of_date"]) for x in all_snaps if x["as_of_date"]), default="—"))

    st.info("Select a project in the sidebar to open its intelligence workspace.")
    st.stop()

# -----------------------------------------------------------------------------
# Project workspace
snap = project_snapshot(selected_project)
st.markdown('<div class="eyebrow">Project workspace</div>', unsafe_allow_html=True)
st.title(selected_project)
st.markdown(f'<div class="project-chip">{snap.get("location") or "Project record"} · Evidence through {human_date(snap.get("as_of_date"))}</div>', unsafe_allow_html=True)

# Snapshot strip
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown('<div class="metric-box"><div class="metric-label">Schedule</div><div class="metric-value">' + (f'{snap["slippage_days"]} days' if snap["slippage_days"] else "On baseline") + '</div><div class="metric-sub">against CPM baseline</div></div>', unsafe_allow_html=True)
with m2:
    st.markdown('<div class="metric-box"><div class="metric-label">Change orders</div><div class="metric-value">' + money(snap["change_cost"]) + '</div><div class="metric-sub">recorded cost impact</div></div>', unsafe_allow_html=True)
with m3:
    label = f'{snap["open_obligations"]} open'
    sub = f'{snap["overdue_count"]} overdue'
    st.markdown('<div class="metric-box"><div class="metric-label">Contract obligations</div><div class="metric-value">' + label + '</div><div class="metric-sub">' + sub + ' at latest evidence date</div></div>', unsafe_allow_html=True)
with m4:
    st.markdown('<div class="metric-box"><div class="metric-label">Contract value</div><div class="metric-value">' + money(snap["contract_value"]) + '</div><div class="metric-sub">' + (snap.get("contractor") or "Contractor not identified") + '</div></div>', unsafe_allow_html=True)

st.markdown("## Project intelligence")
tab_overview, tab_investigate, tab_risk, tab_data = st.tabs(["Overview", "Investigate", "Risk assessment", "Evidence"])

with tab_overview:
    st.markdown("### What needs attention")
    result = generate_risk_assessment(selected_project)
    items = result["items"]
    if not items:
        st.success("No material risk signals were identified in the available project evidence.")
    else:
        sev = result["overall_severity"]
        st.markdown(f'<div class="finding"><div class="finding-title severity-{sev.lower()}">Overall attention: {sev}</div><div class="finding-detail">{result["summary"].replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
        for item in items:
            impact = money(item["impact_amount"]) if item.get("impact_amount") else item.get("impact_detail") or "No quantified impact recorded."
            evidence = ", ".join([str(x) for x in item.get("evidence", []) if x]) or "Project records"
            st.markdown(
                f'<div class="finding"><div class="finding-title"><span class="severity-{item["severity"].lower()}">{item["severity"]}</span> · {item["title"]}</div>'
                f'<div class="finding-detail">{item["detail"]}</div>'
                f'<div class="impact-line"><strong>Impact:</strong> {impact}</div>'
                f'<div class="evidence-line"><strong>Evidence:</strong> {evidence}</div></div>',
                unsafe_allow_html=True,
            )

    actions = recommendations(items)
    if actions:
        st.markdown("### Recommended next actions")
        st.markdown("<ul class='action-list'>" + "".join(f"<li>{a}</li>" for a in actions) + "</ul>", unsafe_allow_html=True)

with tab_investigate:
    st.markdown("### Investigate the project")
    st.caption("Ask about contractual requirements, project records, delays, penalties or cross-record patterns.")
    examples = [
        "What penalties apply if structural steel delivery is delayed?",
        "What are the contractor's obligations related to material delivery?",
        "Which obligations are currently overdue?",
    ]
    cols = st.columns(3)
    for i, ex in enumerate(examples):
        if cols[i].button(ex, key=f"ex_{i}", use_container_width=True):
            st.session_state["question"] = ex
    question = st.text_input("Question", key="question", placeholder="e.g. What contractual exposure is linked to the current schedule delay?")
    if st.button("Investigate", type="primary", disabled=not question, use_container_width=False):
        with st.spinner("Reviewing project evidence…"):
            answer = ask(question, project_name=selected_project)
        st.markdown("### Answer")
        # Render the synthesized answer as Markdown so emphasis such as **Completion delay:** is displayed correctly.
        st.markdown(answer["answer"])
        if answer["intent"] == "sql":
            if answer.get("error"):
                st.error("The structured query could not be completed.")
            elif answer.get("rows"):
                st.dataframe(pd.DataFrame(answer["rows"]), use_container_width=True, hide_index=True)
            else:
                st.caption("No matching records were found.")
        else:
            st.markdown("### Supporting evidence")
            for source in answer["sources"]:
                ref = source["clause_ref"] or "Project record"
                excerpt = source["excerpt"]
                if ref and excerpt.lower().startswith(ref.lower()):
                    excerpt = excerpt[len(ref):].lstrip(" :—-")
                st.markdown(
                    f'<div class="source-card"><div class="source-ref">{ref}</div>'
                    f'<div class="source-doc">{source["document"]} · {human_date(source.get("document_date"))}</div>'
                    f'<div style="margin-top:.45rem;line-height:1.5">{excerpt}</div></div>',
                    unsafe_allow_html=True,
                )
        with st.expander("Analysis details", expanded=False):
            st.caption(f"Path selected: {'Document evidence' if answer['intent']=='rag' else 'Structured project data'}")
            if answer["intent"] == "sql" and answer.get("sql"):
                st.code(answer["sql"], language="sql")

with tab_risk:
    st.markdown("### Risk assessment")
    st.caption("Assessment is based on the latest available schedule, cost, contractual and site evidence.")
    if st.button("Refresh assessment", type="primary"):
        st.rerun()
    result = generate_risk_assessment(selected_project)
    severity = result["overall_severity"]
    st.markdown(f'<div class="finding"><div class="finding-title severity-{severity.lower()}">Overall risk: {severity}</div><div class="finding-detail">Assessment date: {human_date(result.get("as_of_date"))}</div></div>', unsafe_allow_html=True)
    for item in result["items"]:
        impact = money(item["impact_amount"]) if item.get("impact_amount") else item.get("impact_detail") or "No quantified impact recorded."
        st.markdown(
            f'<div class="finding"><div class="finding-title"><span class="severity-{item["severity"].lower()}">{item["severity"]}</span> · {item["title"]} <span class="small-note">· {item["category"]}</span></div>'
            f'<div class="finding-detail">{item["detail"]}</div>'
            f'<div class="impact-line"><strong>Impact:</strong> {impact}</div>'
            f'<div class="evidence-line"><strong>Evidence strength:</strong> {item.get("evidence_strength", "Strong")}</div></div>',
            unsafe_allow_html=True,
        )
    with st.expander("Evidence used", expanded=False):
        ev = result["evidence"]
        if ev["overdue_obligations"]:
            st.markdown("**Overdue obligations**")
            df = pd.DataFrame(ev["overdue_obligations"])
            if not df.empty:
                if "deadline" in df: df["deadline"] = df["deadline"].apply(human_date)
                if "penalty_amount_per_day" in df: df["penalty_amount_per_day"] = df["penalty_amount_per_day"].apply(money)
                st.dataframe(df, use_container_width=True, hide_index=True)
        if ev["schedule_slippage"]:
            st.markdown("**Schedule**")
            df = pd.DataFrame(ev["schedule_slippage"])
            if not df.empty:
                for col in ("planned_end", "actual_end", "document_date"):
                    if col in df.columns:
                        df[col] = df[col].apply(human_date)
                keep = [c for c in ["task_name", "slippage_days", "note", "source_document"] if c in df.columns]
                df = df[keep].rename(columns={"task_name": "Schedule item", "slippage_days": "Slippage", "note": "Observation", "source_document": "Evidence"})
                if "Slippage" in df.columns:
                    df["Slippage"] = df["Slippage"].apply(lambda x: f"{int(x)} days" if pd.notna(x) else "—")
                st.dataframe(df, use_container_width=True, hide_index=True)
        if ev["change_orders"]:
            st.markdown("**Change orders**")
            df = pd.DataFrame(ev["change_orders"])
            if not df.empty:
                if "cost_impact" in df: df["cost_impact"] = df["cost_impact"].apply(money)
                if "date_raised" in df: df["date_raised"] = df["date_raised"].apply(human_date)
                keep = [c for c in ["description", "cost_impact", "schedule_impact_days", "status", "date_raised", "source_document"] if c in df.columns]
                df = df[keep].rename(columns={"description": "Change", "cost_impact": "Cost impact", "schedule_impact_days": "Schedule impact", "status": "Status", "date_raised": "Raised", "source_document": "Evidence"})
                if "Schedule impact" in df.columns:
                    df["Schedule impact"] = df["Schedule impact"].apply(lambda x: f"{int(x)} days" if pd.notna(x) else "—")
                if "Status" in df.columns:
                    df["Status"] = df["Status"].astype(str).str.title()
                st.dataframe(df, use_container_width=True, hide_index=True)
        if ev["relevant_clauses"]:
            st.markdown("**Contract references**")
            for c in ev["relevant_clauses"]:
                st.markdown(f"**{c.get('clause_ref') or 'Source'}** — {c['excerpt']}")
        if ev["project_signals"]:
            st.markdown("**Project observations**")
            for s in ev["project_signals"]:
                st.markdown(f"- **{s['document']}** · {human_date(s.get('document_date'))}: {s['finding']}")

with tab_data:
    st.markdown("### Contract obligations")
    ob_df = get_obligations_df(selected_project)
    if ob_df.empty:
        st.caption("No obligations are currently indexed.")
    else:
        display_cols = [c for c in ["Obligation", "Due", "Contractual consequence", "Status", "Clause"] if c in ob_df.columns]
        display_df = ob_df[display_cols].copy()
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=420)

    st.markdown("### Source documents")
    doc_df = get_documents_df(selected_project)
    st.dataframe(doc_df, use_container_width=True, hide_index=True)
