# Final UI / reasoning revision

This revision focuses on presenting the system as an engineering decision-support product rather than a technical RAG demo.

## User-facing changes
- Renamed **Risk review** to **Risk assessment**.
- Removed probability/likelihood percentages from the UI; severity is deterministic and evidence-backed.
- Added impact/consequence lines to risk findings.
- Made the evidence section collapsed by default.
- Simplified obligation tables and removed internal extraction-confidence fields from the primary view.
- Displayed contractual consequences as text rather than converting weekly penalties into misleading daily values.
- Improved source excerpts to avoid duplicated section references.

## Retrieval changes
- Added lightweight query expansion for delay, penalty, completion, delivery, quality and safety questions.
- Added project-scoped retrieval and stronger preference for contract clauses for contractual questions.
- The offline demo can synthesize penalty answers from the retrieved clauses without exposing implementation details.

## Risk changes
- Added specific findings for structural steel delivery, concrete testing, and cement buffer issues when supported by project evidence.
- Added evidence-strength labels instead of pseudo-probabilities.
- Added concrete, evidence-backed recommended actions.

## Testing
The Riverside query:

> What penalties apply for delayed civil work?

now retrieves Section 10.1 and Section 7.2 from the Riverside contract and distinguishes completion-delay and delivery-delay provisions without claiming that the penalties are cumulative.
