-- Engineering Intelligence & Decision Support System
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    role TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    project_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    location TEXT,
    owner_company_id INTEGER REFERENCES companies(company_id),
    start_date TEXT,
    planned_end_date TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(project_id),
    filename TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    document_date TEXT,
    ingested_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(document_id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    clause_ref TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
    contract_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(project_id),
    document_id INTEGER REFERENCES documents(document_id),
    contractor_company_id INTEGER REFERENCES companies(company_id),
    contract_value REAL,
    currency TEXT DEFAULT 'INR',
    signed_date TEXT
);

CREATE TABLE IF NOT EXISTS clauses (
    clause_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER REFERENCES contracts(contract_id),
    chunk_id INTEGER REFERENCES chunks(chunk_id),
    clause_ref TEXT,
    clause_text TEXT,
    clause_type TEXT
);

CREATE TABLE IF NOT EXISTS obligations (
    obligation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER REFERENCES contracts(contract_id),
    clause_id INTEGER REFERENCES clauses(clause_id),
    responsible_company_id INTEGER REFERENCES companies(company_id),
    description TEXT NOT NULL,
    deadline TEXT,
    penalty_text TEXT,
    penalty_amount_per_day REAL,
    status TEXT DEFAULT 'open',
    confidence REAL,
    extracted_from_chunk_id INTEGER REFERENCES chunks(chunk_id)
);

CREATE TABLE IF NOT EXISTS deadlines (
    deadline_id INTEGER PRIMARY KEY AUTOINCREMENT,
    obligation_id INTEGER REFERENCES obligations(obligation_id),
    due_date TEXT,
    actual_date TEXT,
    is_overdue INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS penalties (
    penalty_id INTEGER PRIMARY KEY AUTOINCREMENT,
    obligation_id INTEGER REFERENCES obligations(obligation_id),
    amount_per_day REAL,
    cap_amount REAL,
    currency TEXT DEFAULT 'INR',
    clause_id INTEGER REFERENCES clauses(clause_id)
);

CREATE TABLE IF NOT EXISTS change_orders (
    change_order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(project_id),
    contract_id INTEGER REFERENCES contracts(contract_id),
    document_id INTEGER REFERENCES documents(document_id),
    description TEXT,
    cost_impact REAL,
    schedule_impact_days INTEGER,
    date_raised TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS schedule_items (
    schedule_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(project_id),
    task_name TEXT,
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    slippage_days INTEGER DEFAULT 0,
    note TEXT,
    source_document_id INTEGER REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS risks (
    risk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(project_id),
    title TEXT,
    category TEXT,
    probability REAL,
    impact_amount REAL,
    severity TEXT,
    evidence TEXT,
    generated_at TEXT DEFAULT (datetime('now'))
);
