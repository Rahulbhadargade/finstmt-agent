"""Plain-English explanations. The template path is always available and is the source of truth.
An optional LLM can rewrite the wording, but it only ever sees the structured findings, and its
output is rejected (falling back to the template) if it introduces any number that is not in them."""
from __future__ import annotations

import json
import os
import re

from .models import Decision, Severity
from .util import dumps, money

HEADLINE = {
    Decision.ACCEPTED: "Passed all checks and was posted.",
    Decision.ACCEPTED_WITH_WARNINGS: "Posted, with points you should know about.",
    Decision.ACCEPTED_BY_OVERRIDE: "Was on hold, then approved by a named reviewer and posted.",
    Decision.QUARANTINED: "On hold for your decision. Not posted.",
    Decision.REJECTED: "Rejected. Not posted.",
}
ICON = {Decision.ACCEPTED: "✅", Decision.ACCEPTED_WITH_WARNINGS: "⚠️", Decision.ACCEPTED_BY_OVERRIDE: "🟦",
        Decision.QUARANTINED: "⏸️", Decision.REJECTED: "❌"}


def template_summary(decision, findings) -> str:
    notable = [f for f in findings if f.severity != Severity.INFO]
    if not notable:
        return HEADLINE[decision]
    body = " ".join(f.plain for f in notable)
    actions = " ".join(dict.fromkeys(f.action for f in notable))
    return f"{HEADLINE[decision]} {body} Next step: {actions}"


def llm_payload(result) -> dict:
    return {"entry_id": result.entry.get("id"), "description": result.entry.get("description"),
            "decision": result.decision.value,
            "findings": [{"rule": f.rule, "severity": f.severity.value, "plain": f.plain, "action": f.action}
                         for f in result.findings if f.severity != Severity.INFO]}


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set:
    return {float(m.replace(",", "")) for m in _NUM.findall(text)}


def guard(text: str, payload: dict) -> tuple:
    """Return (ok, reason). Every number in the LLM text must already appear in the payload."""
    extra = _numbers(text) - _numbers(json.dumps(payload))
    if extra:
        return False, f"introduced numbers not in the findings: {sorted(extra)}"
    if payload["decision"] in ("REJECTED", "QUARANTINED") and re.search(r"\b(was|been|is|were) (posted|approved)\b", text, re.I):
        return False, "text implies the entry was posted/approved"
    return True, ""


SYSTEM = ("You help a finance user understand why a journal entry was accepted, held or rejected. "
          "Rewrite the supplied findings as a short, friendly note (max 120 words, plain prose, no markdown). "
          "Use ONLY the facts and numbers in the JSON. Do not invent numbers, accounts, causes or fixes. "
          "Do not change the decision.")


class LLMPolisher:
    """Optional. Needs `pip install anthropic` and ANTHROPIC_API_KEY. Any failure returns None."""

    def __init__(self, client=None, model: str | None = None):
        self.model = model or os.environ.get("FINSTMT_MODEL", "claude-sonnet-5-5")
        self.client = client

    def polish(self, payload: dict):
        try:
            if self.client is None:
                import anthropic
                self.client = anthropic.Anthropic()
            msg = self.client.messages.create(model=self.model, max_tokens=400, system=SYSTEM,
                                              messages=[{"role": "user", "content": json.dumps(payload)}])
            return msg.content[0].text.strip()
        except Exception:
            return None


def render_report(inp, results, input_findings, post, run_id) -> str:
    counts = {}
    for r in results:
        counts[r.decision.value] = counts.get(r.decision.value, 0) + 1
    L = [f"# Manual adjustments report - {inp.period}", "", f"Run ID: `{run_id[:16]}`  |  Functional currency: {inp.adjustments.get('functional_currency')}", "",
         "## Outcome", "", "| Entry | Description | Amount | Decision | Why |", "|---|---|---:|---|---|"]
    for r in results:
        amt = sum((l["debit"] for l in r.entry.get("lines", [])), 0)
        top = next((f.title for f in sorted(r.findings, key=lambda f: -["INFO", "WARN", "REVIEW", "BLOCK"].index(f.severity.value))
                    if f.severity != Severity.INFO), "-")
        L.append(f"| {r.entry.get('id')} | {r.entry.get('description')} | {money(amt)} | {ICON[r.decision]} {r.decision.value} | {top} |")
    L += ["", "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), "",
          "## Effect of posted entries (as-reported amounts, no FX translation)", "",
          f"- Net income before adjustments: {money(post['ni_before'])}",
          f"- Net income after posted entries: {money(post['ni_after'])} (change {money(post['ni_after'] - post['ni_before'])})",
          f"- TB debits minus credits before: {money(post['imbalance_before'])}; after: {money(post['imbalance_after'])} "
          "(posted entries are balanced, so the pre-existing difference is unchanged and still unexplained)", "",
          "## Entry by entry", ""]
    for r in results:
        e = r.entry
        L += [f"### {e.get('id')} - {e.get('description')}  {ICON[r.decision]} {r.decision.value}", "",
              f"Date {e.get('date')} | Source: {e.get('source')}", "", r.summary, ""]
        for f in r.findings:
            if f.suggestions:
                L.append("Suggested accounts (not applied):")
                for s in f.suggestions:
                    L.append(f"- {s['account']} {s['name']} (confidence {s['confidence']:.2f})")
                L.append("")
        if r.override:
            L += [f"Override: {dumps(r.override)}", ""]
        L += [f"Checks: " + ", ".join(f"{a}={b}" for a, b in r.rule_trace), ""]
    L += ["## Problems found in the input files", "", "| ID | Severity | Finding |", "|---|---|---|"]
    for f in input_findings:
        L.append(f"| {f['id']} | {f['severity']} | {f['title']}. {f['detail']} |")
    return "\n".join(L) + "\n"
