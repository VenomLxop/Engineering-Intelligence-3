"""Lightweight TF-IDF retrieval over document chunks.

The retriever keeps a small, replaceable interface so a neural embedding model can
be introduced later without changing the rest of the application.
"""
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    project_id: int | None
    text: str
    clause_ref: str | None
    score: float


class TfidfRetriever:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = None
        self.records: list[dict] = []

    def index(self, records: list[dict]):
        self.records = records
        texts = [r["text"] for r in records]
        self.matrix = self.vectorizer.fit_transform(texts) if texts else None

    def query(self, question: str, top_k: int = 5, project_id: int | None = None) -> list[RetrievedChunk]:
        if self.matrix is None or not self.records:
            return []
        allowed = [
            i for i, r in enumerate(self.records)
            if project_id is None or r.get("project_id") == project_id
        ]
        if not allowed:
            return []

        # Lightweight query expansion makes the offline retriever more robust
        # to natural wording. For example, "delayed civil work" should surface
        # clauses written as "liquidated damages for delay in completion".
        expanded = question
        lowered = question.lower()
        if "penalt" in lowered or "liquidated" in lowered or "delay" in lowered:
            expanded += " penalty liquidated damages delay completion delivery"
        if "civil" in lowered or "completion" in lowered:
            expanded += " civil works completion"
        if "material" in lowered or "steel" in lowered or "deliver" in lowered:
            expanded += " material delivery structural steel supply"
        if "quality" in lowered or "testing" in lowered:
            expanded += " quality assurance concrete cube testing non-conformance"
        if "safety" in lowered:
            expanded += " safety obligations safety officer toolbox talks"

        q_vec = self.vectorizer.transform([expanded])
        sims = cosine_similarity(q_vec, self.matrix).flatten()

        # Small lexical boost for exact high-signal terms. This remains a simple
        # TF-IDF retriever, but prevents generic tender text from outranking a
        # clause explicitly containing the requested contractual consequence.
        boost_terms = []
        if "penalt" in lowered or "liquidated" in lowered:
            boost_terms += ["penalty", "liquidated damages"]
        if "delay" in lowered:
            boost_terms += ["delay", "delayed"]
        if "civil" in lowered:
            boost_terms += ["civil works", "completion"]
        if "steel" in lowered:
            boost_terms += ["structural steel", "material delivery"]
        if "material" in lowered and "deliver" in lowered:
            boost_terms += ["deliver", "supply"]

        if boost_terms:
            for i in allowed:
                text = self.records[i]["text"].lower()
                matches = sum(1 for term in boost_terms if term in text)
                sims[i] += min(0.12, 0.03 * matches)
                # For contractual questions, prefer actual contract clauses over
                # tender notices or meeting notes when the clause contains the
                # requested provision.
                if ("penalt" in lowered or "liquidated" in lowered) and self.records[i].get("doc_type") == "contract":
                    sims[i] += 0.08
                if self.records[i].get("clause_ref") and ("penalt" in lowered or "delay" in lowered):
                    sims[i] += 0.025

        ranked = sorted(allowed, key=lambda i: sims[i], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                chunk_id=self.records[i]["chunk_id"],
                document_id=self.records[i]["document_id"],
                project_id=self.records[i].get("project_id"),
                text=self.records[i]["text"],
                clause_ref=self.records[i].get("clause_ref"),
                score=float(sims[i]),
            )
            for i in ranked if sims[i] > 0
        ]


def build_retriever_from_db() -> TfidfRetriever:
    from .db import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT c.chunk_id, c.document_id, d.project_id, d.doc_type, c.text, c.clause_ref "
        "FROM chunks c JOIN documents d ON c.document_id = d.document_id"
    ).fetchall()
    conn.close()
    retriever = TfidfRetriever()
    retriever.index([dict(r) for r in rows])
    return retriever
