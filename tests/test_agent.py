import copy
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from adjustments_agent.explain import LLMPolisher, guard
from adjustments_agent.loader import load_inputs, net_by_account
from adjustments_agent.models import Decision, Severity
from adjustments_agent.pipeline import run
from adjustments_agent.suggest import suggest_accounts
from adjustments_agent.validators import Context, validate, content_hash

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def inp():
    return load_inputs(DATA)


@pytest.fixture()
def ctx(inp):
    c = Context(coa=inp.coa, tb_net=net_by_account(inp.tb_rows), prior_net=net_by_account(inp.prior_rows),
                tb_rows=inp.tb_rows, fx=inp.fx, period_range=inp.period_range, materiality=Decimal("500000"))
    return c


def entry(lines, **kw):
    e = {"id": "T-1", "description": "test", "date": "2024-12-31", "source": "test", "lines": [
        {"account": a, "debit": Decimal(d), "credit": Decimal(c), "memo": "m"} for a, d, c in lines]}
    e.update(kw)
    return e


def rules_failed(e, ctx):
    ctx.batch_ids = Counter([e["id"]])
    f, _ = validate(e, ctx)
    return {x.rule for x in f if x.severity != Severity.INFO}


# ---- the seeded defects, end to end
def test_sample_batch_decisions(tmp_path):
    out = run(DATA, tmp_path)
    d = {r.entry["id"]: r.decision for r in out["results"]}
    assert d == {"JE-001": Decision.ACCEPTED_WITH_WARNINGS, "JE-002": Decision.REJECTED, "JE-003": Decision.QUARANTINED,
                 "JE-004": Decision.ACCEPTED, "JE-005": Decision.QUARANTINED, "JE-006": Decision.QUARANTINED,
                 "JE-007": Decision.ACCEPTED, "JE-008": Decision.REJECTED, "JE-009": Decision.ACCEPTED,
                 "JE-010": Decision.ACCEPTED}
    assert out["post"]["ni_after"] - out["post"]["ni_before"] == Decimal("-1008000")
    assert out["post"]["imbalance_after"] == out["post"]["imbalance_before"]  # posted batch is balanced


def test_outputs_are_deterministic(tmp_path):
    run(DATA, tmp_path / "a")
    run(DATA, tmp_path / "b")
    for name in ("decisions.json", "audit_log.jsonl", "post_adjustment_tb.csv", "adjustment_report.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


# ---- individual rules on small synthetic entries
def test_unbalanced_is_blocked(ctx):
    assert "R02" in rules_failed(entry([(6100, "100", "0"), (2120, "0", "90")]), ctx)


def test_unknown_account_is_quarantined_with_suggestions(ctx):
    e = entry([(6315, "100", "0"), (2120, "0", "100")])
    f, _ = validate(e, ctx)
    r03 = [x for x in f if x.rule == "R03"][0]
    assert r03.severity == Severity.REVIEW and r03.suggestions and all(s["confidence"] <= 0.9 for s in r03.suggestions)


def test_header_account_is_blocked(ctx):
    assert "R03" in rules_failed(entry([(6000, "100", "0"), (2120, "0", "100")]), ctx)


def test_circular_entry_is_blocked(ctx):
    assert "R04" in rules_failed(entry([(2170, "50", "0"), (2170, "0", "50")]), ctx)


def test_out_of_period_date(ctx):
    assert "R05" in rules_failed(entry([(6100, "1", "0"), (2120, "0", "1")], date="2025-01-15"), ctx)


def test_malformed_entry_skips_other_rules(ctx):
    e = entry([(6100, "100", "0")])
    f, trace = validate(e, ctx)
    assert f[0].rule == "R01" and all(s == "skipped" for _, s in trace[1:])


def test_duplicate_content_flagged(ctx):
    a, b = entry([(6100, "5", "0"), (2120, "0", "5")]), entry([(6100, "5", "0"), (2120, "0", "5")], id="T-2")
    ctx.batch_ids = Counter(["T-1", "T-2"])
    ctx.batch_hashes = {content_hash(a): ["T-1", "T-2"]}
    f, _ = validate(a, ctx)
    assert any(x.rule == "R06" for x in f)


def test_fx_reval_that_reconciles_passes(ctx):
    bal = Decimal("825400")
    good = (bal * (Decimal("1.095") - Decimal("1.082"))).quantize(Decimal("0.01"))
    e = entry([(1110, str(good), "0"), (7310, "0", str(good))], description="FX revaluation of EUR cash")
    assert "R07" not in {x.rule for x in validate(e, ctx)[0] if x.severity == Severity.REVIEW}


def test_account_suggestion_ranks_sibling_first(inp):
    s = suggest_accounts(6315, ["conference travel"], inp.coa)
    assert s[0]["account"] == 6310


# ---- human-in-the-loop
def test_approval_needs_named_approver_and_bad_remap_is_caught(tmp_path):
    out = run(DATA, tmp_path, resolutions={
        "JE-006": {"action": "approve"},                                             # no approver -> stays on hold
        "JE-005": {"action": "approve", "approved_by": "x", "account_remap": {"6315": "6310"}},  # circular -> rejected
        "JE-003": {"action": "approve", "approved_by": "x", "note": "ok"},          # approved
        "JE-002": {"action": "approve", "approved_by": "x"}})                       # rejected entries can't be overridden
    d = {r.entry["id"]: r.decision for r in out["results"]}
    assert d["JE-006"] == Decision.QUARANTINED
    assert d["JE-005"] == Decision.REJECTED
    assert d["JE-003"] == Decision.ACCEPTED_BY_OVERRIDE
    assert d["JE-002"] == Decision.REJECTED


def test_approving_unknown_account_without_remap_does_not_post(tmp_path):
    out = run(DATA, tmp_path, resolutions={"JE-005": {"action": "approve", "approved_by": "x"}})
    assert {r.entry["id"]: r.decision for r in out["results"]}["JE-005"] == Decision.QUARANTINED


# ---- LLM guard (no network: fake client)
class FakeClient:
    def __init__(self, text):
        self.messages = self
        self.text = text

    def create(self, **kw):
        class M:  # minimal response shape
            content = [type("B", (), {"text": self.text})()]
        return M()


def _run_with(text, tmp_path):
    return run(DATA, tmp_path, polisher=LLMPolisher(client=FakeClient(text)))


def test_llm_text_with_invented_numbers_is_rejected(tmp_path):
    out = _run_with("JE-002 is out of balance by $9,999.", tmp_path)
    r = [x for x in out["results"] if x.entry["id"] == "JE-002"][0]
    assert r.summary_source == "template"


def test_llm_text_using_only_known_numbers_is_accepted():
    payload = {"decision": "REJECTED", "findings": [{"plain": "out of balance by $3,500.00"}]}
    assert guard("The entry is out of balance by $3,500.", payload)[0]
    assert not guard("The entry was posted for $3,500.", payload)[0]
