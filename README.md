# Manual adjustments agent (prototype slice)

Part of a design for an agentic financial-statement generator. **Read `docs/ARCHITECTURE.md` first**; this repo implements one slice of it: **validate manual journal entries, quarantine or reject the bad ones, explain why in plain English, and post the good ones with a full audit trail.**

It runs on the messy mock data unchanged. No cleaning is done before processing.

## Run it

Needs Python 3.10+. No third-party packages are required to run.

```bash
cd finstmt-agent
PYTHONPATH=src python -m adjustments_agent            # reads data/, writes output/
PYTHONPATH=src python -m adjustments_agent --resolutions examples/resolutions.example.json --out output_with_approvals
pip install pytest && PYTHONPATH=src python -m pytest -q tests     # 15 tests
```

(Or `pip install -e .` and drop `PYTHONPATH=src`.)

Optional LLM wording: `pip install anthropic`, set `ANTHROPIC_API_KEY`, add `--llm` (model via `FINSTMT_MODEL`). Without it, explanations come from templates. The LLM path was tested with a fake client only, not against the live API.

## What you get in `output/`

| File | What it is |
|---|---|
| `adjustment_report.md` | Start here. Decision per entry in plain English, effect on net income, and the problems found in the input files |
| `decisions.json` | Machine-readable decision, rule trace and findings per entry |
| `review_queue.json` | Quarantined entries waiting for a human, and how to resolve them |
| `post_adjustment_tb.csv` | Pre-adjustment, adjustments and post-adjustment balance per account, with **source TB rows and entry IDs** (traceability) |
| `ledger.json` | Every posted journal line |
| `audit_log.jsonl` | Every rule result, finding, override and posting; no timestamps, so reruns are byte-identical |
| `input_findings.json` | Data-quality problems in the input files |

## Result on the sample batch

| Entry | Decision | Why |
|---|---|---|
| JE-001 bonus accrual 850k | Accepted with warning | Above the 500k review threshold: approver sign-off needed |
| JE-002 marketing reclass | **Rejected** | Debits 28,500 vs credits 25,000 (out by 3,500) |
| JE-003 EUR revaluation | **Quarantined** | 11,200 does not match the recomputed 10,730 or 19,810; GBP has no period-end rate |
| JE-004, 007, 009, 010 | Accepted | Pass all checks |
| JE-005 conference travel | **Quarantined** | Account 6315 not in COA; ranked suggestions shown; a remap to 6310 would make it circular |
| JE-006 depreciation catch-up | **Quarantined** | Accumulated depreciation already moved by exactly the 850k expense in the TB: possible double count |
| JE-008 UK intercompany | **Rejected** | Same account on both sides, nets to zero |

Net income moves from 6,006,500 to 4,998,500 (posted entries total 1,008,000 of expense). The TB's own 4,800 imbalance is reported, not plugged, and is unchanged by the posted entries.

## How it is built

```
loader  ->  input_checks  ->  validators (R01-R11, pure code)  ->  decide  ->  human resolutions (re-validated)
        ->  explain (template, optional LLM behind a number guard)  ->  post + self-check  ->  outputs
```

* `validators.py`: each rule has a stable ID, returns findings with the numbers it used, and is individually testable.
* Severity maps to outcome: `BLOCK` rejects, `REVIEW` quarantines, `WARN` posts with a warning, `INFO` is a note.
* Quarantined entries can be approved with a named approver (`examples/resolutions.example.json`). The entry is re-validated after approval, so a bad fix is still caught. Rejected entries cannot be overridden.
* The posted batch must net to zero or the run aborts.

## Assumptions and limits

* Amounts are used **as reported, without FX translation** (translation belongs to the statement-builder slice; see the open question in the architecture doc).
* Thresholds (500k review limit, 1% reval tolerance) are placeholders, not policy.
* R07 and R08 target the patterns seen in this data; a real system needs a configurable rule library.
* Not built: mapper, FX translation, intercompany elimination, statement generation, persistence. These are designed in `docs/ARCHITECTURE.md`.

## AI tool use

Built with Claude (analysis of the data, drafting design, code and tests). The code was run against the real files and the tests pass; see `docs/REFLECTION.md`.
