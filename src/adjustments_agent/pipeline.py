"""Orchestrator: plain code, fixed order, no LLM deciding what happens next."""
from __future__ import annotations

import copy
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from . import __version__
from .explain import LLMPolisher, llm_payload, guard, render_report, template_summary
from .input_checks import check_inputs
from .loader import load_inputs, net_by_account
from .models import Decision, EntryResult, POSTED, SEV_RANK, Severity
from .util import dumps, sha256_text
from .validators import Context, RULES, content_hash, norm_lines, validate

ZERO = Decimal(0)


class PostingError(Exception):
    """Raised when our own output fails a self-check. Better to stop than to emit a wrong ledger."""


def decide(findings) -> Decision:
    worst = max((SEV_RANK[f.severity.value] for f in findings), default=-1)
    return (Decision.REJECTED if worst == 3 else Decision.QUARANTINED if worst == 2
            else Decision.ACCEPTED_WITH_WARNINGS if worst == 1 else Decision.ACCEPTED)


def _remap(entry, mapping):
    e = copy.deepcopy(entry)
    for l in e["lines"]:
        l["account"] = mapping.get(str(l["account"]), l["account"])
    return e


def _apply_resolution(res: EntryResult, resolution: dict, ctx, audit):
    """Human-in-the-loop: an approver can approve a quarantined entry, optionally remapping accounts.
    The result is re-validated, so a bad 'fix' (e.g. one that makes the entry circular) is still caught.
    Rejected entries cannot be overridden: they must be corrected and resubmitted."""
    if res.decision != Decision.QUARANTINED:
        audit({"event": "resolution_ignored", "entry": res.entry["id"], "reason": f"entry is {res.decision.value}; only quarantined entries can be approved"})
        return
    entry2 = _remap(res.entry, resolution.get("account_remap", {}))
    f2, trace2 = validate(entry2, ctx)
    worst = max((SEV_RANK[f.severity.value] for f in f2), default=-1)
    info = {"approved_by": resolution.get("approved_by"), "note": resolution.get("note"),
            "account_remap": resolution.get("account_remap", {})}
    unresolved_acct = any(f.rule == "R03" and f.severity == Severity.REVIEW for f in f2)
    if worst == 3:
        res.decision, res.findings, res.rule_trace, res.entry = Decision.REJECTED, f2, trace2, entry2
        info["outcome"] = "re-validation after the resolution found a blocking problem"
    elif unresolved_acct or resolution.get("action") != "approve" or not resolution.get("approved_by"):
        info["outcome"] = "not approved: needs action=approve, a named approver, and every account to exist in the COA"
    else:
        res.decision, res.findings, res.rule_trace, res.entry = Decision.ACCEPTED_BY_OVERRIDE, f2, trace2, entry2
        info["outcome"] = "approved and posted"
    res.override = info
    audit({"event": "resolution", "entry": res.entry["id"], **info})


def run(data_dir, out_dir, resolutions=None, polisher=None, materiality=Decimal("500000")) -> dict:
    inp = load_inputs(data_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    resolutions = resolutions or {}
    run_id = sha256_text(dumps({"inputs": inp.hashes, "materiality": str(materiality), "resolutions": resolutions,
                                "rules": [r[0] for r in RULES], "version": __version__}))
    events = []
    audit = events.append
    audit({"event": "run_start", "run_id": run_id, "version": __version__, "input_sha256": inp.hashes,
           "materiality": str(materiality), "llm": bool(polisher)})

    # 1. input checks (reported, never silently fixed)
    input_findings = check_inputs(inp)
    for f in input_findings:
        audit({"event": "input_finding", **f})

    # 2. validate every entry
    entries = inp.adjustments["entries"]
    ctx = Context(coa=inp.coa, tb_net=net_by_account(inp.tb_rows), prior_net=net_by_account(inp.prior_rows),
                  tb_rows=inp.tb_rows, fx=inp.fx, period_range=inp.period_range, materiality=materiality)
    ctx.batch_ids = Counter(e.get("id") for e in entries)
    for e in entries:
        ctx.batch_hashes.setdefault(content_hash(e), []).append(e.get("id"))
    results = []
    for e in entries:
        findings, trace = validate(e, ctx)
        r = EntryResult(entry=e, content_hash=content_hash(e), decision=decide(findings), findings=findings, rule_trace=trace)
        for rid, status in trace:
            audit({"event": "rule", "entry": e.get("id"), "rule": rid, "result": status})
        for f in findings:
            audit({"event": "finding", "entry": e.get("id"), **{k: getattr(f, k) for k in ("rule", "severity", "title", "plain", "action", "facts", "suggestions")}})
        audit({"event": "decision", "entry": e.get("id"), "decision": r.decision.value, "content_hash": r.content_hash})
        results.append(r)

    # 3. human resolutions
    for r in results:
        if r.entry.get("id") in resolutions:
            _apply_resolution(r, resolutions[r.entry["id"]], ctx, audit)

    # 4. explanations (template first; optional LLM rewrite behind a guard)
    for r in results:
        r.summary = template_summary(r.decision, r.findings)
        if polisher and any(f.severity != Severity.INFO for f in r.findings):
            payload = llm_payload(r)
            text = polisher.polish(payload)
            if text is None:
                audit({"event": "llm_unavailable", "entry": r.entry.get("id")})
            else:
                ok, why = guard(text, payload)
                audit({"event": "llm_guard", "entry": r.entry.get("id"), "accepted": ok, "reason": why})
                if ok:
                    r.summary, r.summary_source = text, "llm"

    # 5. post accepted entries to a ledger and roll the TB forward
    ledger = []
    for r in results:
        if r.decision in POSTED:
            for l in norm_lines(r.entry):
                ledger.append({"entry": r.entry["id"], "line": l["n"], "account": l["account"], "debit": l["debit"],
                               "credit": l["credit"], "memo": l["memo"], "source": r.entry.get("source"), "decision": r.decision.value})
                audit({"event": "posted", "entry": r.entry["id"], "line": l["n"], "account": l["account"],
                       "debit": l["debit"], "credit": l["credit"]})
    adj_net = defaultdict(lambda: ZERO)
    jes = defaultdict(list)
    for l in ledger:
        adj_net[l["account"]] += l["debit"] - l["credit"]
        if l["entry"] not in jes[l["account"]]:
            jes[l["account"]].append(l["entry"])
    if sum(adj_net.values(), ZERO) != 0:  # self-check: posted batch must net to zero
        raise PostingError(f"posted entries do not balance: {sum(adj_net.values(), ZERO)}")
    rows_by_acct = defaultdict(list)
    for r in inp.tb_rows:
        rows_by_acct[r["code"]].append(r["row"])
    names = {r["code"]: r["name"] for r in inp.tb_rows}
    pre = net_by_account(inp.tb_rows)
    post_rows = []
    for code in sorted(set(pre) | set(adj_net)):
        post_rows.append({"account_code": code, "account_name": inp.coa.get(code, {}).get("name") or names.get(code, ""),
                          "in_coa": code in inp.coa, "pre_net_dr_minus_cr": pre.get(code, ZERO),
                          "adjustments_net": adj_net.get(code, ZERO), "post_net_dr_minus_cr": pre.get(code, ZERO) + adj_net.get(code, ZERO),
                          "tb_source_rows": ";".join(f"trial_balance.csv:{x}" for x in rows_by_acct.get(code, [])),
                          "adjustment_entries": ";".join(jes.get(code, []))})
    pl = [c for c in set(pre) | set(adj_net) if inp.coa.get(c, {}).get("statement") == "PL" and inp.coa[c]["type"] != "Header"]
    ni_before = -sum((pre.get(c, ZERO) for c in pl), ZERO)
    ni_after = -sum((pre.get(c, ZERO) + adj_net.get(c, ZERO) for c in pl), ZERO)
    imb_before = sum(pre.values(), ZERO)
    post = {"ni_before": ni_before, "ni_after": ni_after, "imbalance_before": imb_before,
            "imbalance_after": imb_before + sum(adj_net.values(), ZERO)}
    audit({"event": "run_end", "posted_lines": len(ledger), **{k: v for k, v in post.items()},
           "decisions": dict(Counter(r.decision.value for r in results))})

    # 6. write outputs (deterministic: same inputs + same resolutions => byte-identical files)
    (out / "decisions.json").write_text(json.dumps({
        "run_id": run_id, "period": inp.period,
        "entries": [{"id": r.entry.get("id"), "decision": r.decision.value, "content_hash": r.content_hash,
                     "summary": r.summary, "summary_source": r.summary_source, "rule_trace": r.rule_trace,
                     "findings": [json.loads(dumps(f)) for f in r.findings], "override": r.override} for r in results]},
        indent=2, sort_keys=True))
    (out / "review_queue.json").write_text(json.dumps([
        {"id": r.entry["id"], "why": [f.title for f in r.findings if f.severity == Severity.REVIEW],
         "how_to_resolve": "add an entry to a resolutions file: {action: approve, approved_by: <name>, note: <why>, account_remap: {...}}"}
        for r in results if r.decision == Decision.QUARANTINED], indent=2))
    (out / "input_findings.json").write_text(json.dumps(json.loads(dumps(input_findings)), indent=2))
    (out / "ledger.json").write_text(json.dumps(json.loads(dumps(ledger)), indent=2))
    with open(out / "post_adjustment_tb.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(post_rows[0].keys()))
        w.writeheader()
        for row in post_rows:
            w.writerow({k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()})
    (out / "audit_log.jsonl").write_text("\n".join(dumps(ev) for ev in events) + "\n")
    (out / "adjustment_report.md").write_text(
    render_report(inp, results, input_findings, post, run_id),
    encoding="utf-8"
)
    return {"run_id": run_id, "results": results, "post": post, "input_findings": input_findings}
