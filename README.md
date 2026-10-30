# HouseScope / v2

An inspectable inspection-to-renovation workflow. Luna extracts source observations; application code resolves evidence, consolidates repeated findings, applies priority policies, builds shared repair scopes, records human review and measures reference coverage.

## Run

Requires Node.js 20+ and Python 3.9+. Add your existing OpenAI key to `OPENAI_API_KEY` in the ignored root `.env`, then:

```sh
bash scripts/start.sh
```

Open http://localhost:3000. The API is at http://127.0.0.1:8000/docs. Restart after `.env` changes. The model is fixed to `gpt-6-luna`; the project budget is capped at $5. No production hosting or authentication is configured.

## Walk through the engineering

1. Click **Kentucky benchmark** to register the local public sample. This does not call a model.
2. Open **Document map**. Inspect text-block outlines, page references and the summary/detail structure.
3. Open **Evaluation**. Inspect the 24 curated reference entries and the excluded dryer limitation. Model metrics remain unmeasured until actual extraction.
4. Click **Analyze report** when you want a paid Luna run. The **Pipeline trace** shows durable stages and cached-section counts.
5. In **Findings**, open a record. Switch between source passages and inspect highlighted PDF lines, merge reasons, original variants and priority rule IDs.
6. Correct the interpretation or priority, add a note, then accept, reject or leave pending. Each save creates an immutable audit revision; stale writes return 409.
7. Open **Repair graph**. Inspect linked findings, shared diagnostic scopes, missing quantities, topological prerequisites and unconfirmed relationships.
8. Open **Evaluation** after extraction. Inspect precision, recall, detail-page localization, missed labels and unmatched predictions. Scores use the original extraction, not corrected review output.
9. Export the Markdown assessment, full evidence JSON or review annotation candidates. **Buyer questions** prepares follow-up questions without a model call. In **Pipeline trace**, **Reapply local policies** recomputes evidence, grouping, planning and evaluation from saved observations without paying for extraction again.

## Pipeline

- **Index:** PyMuPDF extracts text blocks, lines, words, coordinates and physical page numbers. Recognizable numbered inspection references connect summary and detail observations. The numbered-reference adapter supports formats like `5.4.1`; other report formats still use quotation grounding without that shortcut.
- **Segment:** Whole layout blocks are packed into bounded batches. Oversized blocks overlap by 350 characters. Every block keeps its page identity; there is no vector search or silent page truncation.
- **Extract:** Luna supplies typed observations, quotations, location, source reference and inspector statements. The schema contains no model-assigned priority, pricing or planning fields.
- **Ground:** Normalized exact quotation checks bind passages to word-coordinate highlights. Reference claims are checked against local observation segments. Negated observations, limitations, boilerplate and weak title/evidence overlap are held for review. These mechanical gates are not semantic proof.
- **Consolidate:** A validated common report reference or identical source passage/location can merge observations. All evidence and raw variants survive. Fuzzy title matches remain suggestions. Conflicting extracted kinds, severity or negated descriptions are flagged.
- **Decide:** Versioned Python policies assign priorities from cited text and inspector categories. Human overrides retain their provenance. Shared trade scopes avoid charging for the same diagnostic visit once per finding.
- **Plan:** Explicit prerequisites form an acyclic task graph. Moisture evaluation precedes source correction. Drainage/moisture co-occurrence is a hypothesis, not a diagnosis. Finish restoration is conditional on relevant source findings.
- **Evaluate:** An exact-document-hash fixture provides one-to-one reference matching, false positives, misses and detail-page quote/coordinate localization. Raw extraction is scored independently of review corrections.

## Human review

The original extraction and quotations are immutable. Review events carry revisions, decisions, corrected fields and notes. Acceptance cannot manufacture missing evidence; a source quotation must match. A reviewer can resolve mechanical support flags, so professional judgment still matters. Rejected findings are excluded from planning. Pending findings that pass mechanical gates can enter a provisional plan; acceptance is shown separately.

Review exports are annotation candidates, not automatically independent ground truth. No reviewer identity/authentication is provided in this local prototype.

## Costs and budget

Repair dollar ranges are illustrative development assumptions, not market data or quotes. Prices attach to shared scopes, not individual findings. Unknown quantities remain unknown, unpriced work stays visible, and scope overlaps still need professional review. Debris-only roof findings are not given a roof-repair price.

The SQLite ledger reserves a conservative maximum before each paid call inside an immediate transaction. Published Luna rates used are input $0.10 / million and output $0.50 / million (checked 2026-10-30). Input bytes, schema, overhead, output cap and a 2x margin determine the reservation. Known usage replaces reservations; unknown failures keep theirs. SDK retries are disabled. Resume is explicit and successful sections are content-addressed checkpoints.

The $5 limit applies to this app's price-based local ledger. It is not an account-wide provider billing limit. Other apps, changed prices and deleting the ledger are outside its control. Implementation and offline checks used no API calls. One subsequent live Kentucky baseline cost $0.0102074 across five extraction sections; see docs/BASELINE.md. Local parser/policy replay added no API cost.

## Evaluation and focused validation

```sh
.venv/bin/python -m pytest backend/tests -q
(cd frontend && npm run build)
.venv/bin/python scripts/evaluate.py --pdf fixtures/peirson-kentucky-sample.pdf --check-reference --output docs/reference-integrity.json
```

To evaluate a saved, genuinely analyzed report without another model call:

```sh
.venv/bin/python scripts/evaluate.py --pdf fixtures/peirson-kentucky-sample.pdf --output docs/extraction-evaluation.json
```

The Kentucky annotation fixture was curated by this agent after reading the source; it has not received an independent human audit. It contains 24 defect/maintenance observations and excludes a dryer limitation listed in the 25-entry summary. Reference matching and localization metrics do not establish semantic accuracy. Offline annotation checks and mock-response pipeline tests are not model-quality results.

## Storage and recovery

`data/housescope.sqlite` holds reports, usage, raw extraction provenance, pipeline runs, stage events and append-only review history. Originals, layout artifacts and extraction checkpoints are stored under ignored `data/`. Legacy assessments are upgraded using their existing extraction without another paid call. Existing billing history is retained. At restart, in-flight stages are marked interrupted and their reports become resumable.

This implementation uses a single FastAPI process with background tasks, not a distributed durable queue. A closed browser does not cancel processing; a terminated backend does. Document originals stay on disk; extracted text is sent to OpenAI when analysis starts. `store=False` is requested for model responses; it is not a claim of zero provider retention.

## Source map

- `backend/document.py`: layout extraction, source references and geometry
- `backend/models.py`: observation and review contracts
- `backend/pipeline.py`: orchestration, checkpoints and stage traces
- `backend/rules.py`: auditable priority and support policies
- `backend/engine.py`: consolidation, review overlays and repair graph
- `backend/evaluation.py`: benchmark matching and error accounting
- `backend/storage.py`: persistence, budget transactions and review revisions
- `backend/main.py`: API, highlighted page rendering and exports
- `frontend/components/`: evidence workbench, document map, evaluation and trace views
- `fixtures/annotations/`: curated reference labels (no original PDFs committed)

See `docs/ARCHITECTURE.md` for design decisions and limitations. Public samples retain their inspectors' attribution and are not licensed for unrestricted redistribution. This is an independent prototype with no affiliation to House IQ.

## Source-based cost estimation

The **Cost estimate** tab adds a quantity-based repair budget using a small cited US reference catalog and custom quote inputs. Set quantities, source assumptions, a local factor, contingency and fees; inspect partial scope coverage, then save/export a revision. It replaces the interface's old illustrative scenario totals with a separate, transparent budgeting workflow. There are no additional AI calls. See [cost-estimation method and source ranges](docs/COST_ESTIMATION.md).
