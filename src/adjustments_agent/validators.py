"""Deterministic validation rules for one journal entry. Every rule is plain code with a stable ID,
returns Findings (empty list = pass) and records the numbers it used. No LLM is involved here."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Finding, Severity
from .suggest import suggest_accounts
from .util import money, sha256_text, dumps

ZERO = Decimal(0)
CENT = Decimal("0.005")


@dataclass
class Context:
    coa: dict
    tb_net: dict
    prior_net: dict
    tb_rows: list
    fx: dict
    period_range: tuple
    materiality: Decimal
    batch_ids: Counter = field(default_factory=Counter)
    batch_hashes: dict = field(default_factory=dict)  # content hash -> [entry ids]


def norm_lines(entry: dict) -> list:
    out = []
    for i, l in enumerate(entry.get("lines") or [], start=1):
        raw = str(l.get("account", "")).strip()
        out.append({"n": i, "account": int(raw) if raw.isdigit() else None, "raw": raw,
                    "debit": Decimal(str(l.get("debit", 0) or 0)), "credit": Decimal(str(l.get("credit", 0) or 0)),
                    "memo": l.get("memo", "")})
    return out


def content_hash(entry: dict) -> str:
    key = {"date": entry.get("date"), "lines": sorted((l["raw"], str(l["debit"]), str(l["credit"])) for l in norm_lines(entry))}
    return sha256_text(dumps(key))


def totals(lines):
    return sum((l["debit"] for l in lines), ZERO), sum((l["credit"] for l in lines), ZERO)


# ---------------------------------------------------------------- rules

def r01_structure(e, ctx):
    lines = norm_lines(e)
    problems = []
    if not e.get("id"):
        problems.append("the entry has no ID")
    if len(lines) < 2:
        problems.append("it has fewer than two lines")
    for l in lines:
        if l["debit"] < 0 or l["credit"] < 0:
            problems.append(f"line {l['n']} has a negative amount")
        if l["debit"] > 0 and l["credit"] > 0:
            problems.append(f"line {l['n']} has both a debit and a credit")
        if l["debit"] == 0 and l["credit"] == 0:
            problems.append(f"line {l['n']} has no amount")
    if not problems:
        return []
    return [Finding("R01", Severity.BLOCK, "Malformed entry",
                    "This entry cannot be read as a journal entry because " + "; ".join(problems) + ".",
                    "Ask the preparer to correct and resubmit it. Nothing was posted.", {"problems": problems})]


def r02_balanced(e, ctx):
    dr, cr = totals(norm_lines(e))
    if abs(dr - cr) <= CENT:
        return []
    return [Finding("R02", Severity.BLOCK, "Debits do not equal credits",
                    f"Debits total {money(dr)} but credits total {money(cr)}, so the entry is out of balance by "
                    f"{money(abs(dr - cr))}. Posting it would break the trial balance.",
                    f"Ask the preparer ({e.get('source', 'source unknown')}) which amount is correct and resubmit. "
                    "Nothing was posted and nothing was auto-corrected.",
                    {"debits": dr, "credits": cr, "difference": dr - cr})]


def r03_accounts(e, ctx):
    out, unknown = [], []
    for l in norm_lines(e):
        a = ctx.coa.get(l["account"])
        if a is None:
            unknown.append(l)
        elif a["type"] == "Header":
            out.append(Finding("R03", Severity.BLOCK, f"Posting to header account {l['raw']}",
                               f"Account {l['raw']} ('{a['name']}') is a summary header; amounts can only be posted to detail accounts.",
                               "Choose a detail account under that header and resubmit.", {"account": l["raw"]}))
    for l in unknown:
        texts = [e.get("description", ""), l["memo"]]
        sugg = suggest_accounts(l["account"] or 0, texts, ctx.coa)
        other = {x["account"] for x in norm_lines(e) if x["account"] and x["account"] in ctx.coa}
        note = ""
        if sugg and sugg[0]["account"] in other:
            note = (f" Note: mapping {l['raw']} to {sugg[0]['account']} would make this entry post to the same "
                    "account on both sides (net zero), so the real fix is probably a new COA account, not a remap.")
        out.append(Finding("R03", Severity.REVIEW, f"Account {l['raw']} is not in the chart of accounts",
                           f"Line {l['n']} posts {money(l['debit'] or l['credit'])} to account {l['raw']}, which does not exist in the COA "
                           f"(memo: '{l['memo']}'). The closest existing accounts are listed as suggestions only; none were applied." + note,
                           "Either add the account to the COA or tell me which existing account to use; then the entry is re-checked.",
                           {"account": l["raw"], "line": l["n"]}, suggestions=sugg))
    return out


def r04_circular(e, ctx):
    lines = norm_lines(e)
    net: dict = {}
    for l in lines:
        net[l["raw"]] = net.get(l["raw"], ZERO) + l["debit"] - l["credit"]
    if lines and all(abs(v) <= CENT for v in net.values()):
        accts = ", ".join(sorted(net))
        dr, _ = totals(lines)
        return [Finding("R04", Severity.BLOCK, "Entry nets to zero (circular)",
                        f"Every line posts to the same account(s) ({accts}) and cancels out: {money(dr)} is debited and credited to the "
                        "same place, so the entry changes nothing. Intercompany settlements need a different account on each side "
                        "(for example cash against the intercompany payable).",
                        "Ask the preparer for the intended counter-account (usually cash or the intercompany receivable) and resubmit.",
                        {"accounts": sorted(net), "amount": dr})]
    return []


def r05_period(e, ctx):
    d = str(e.get("date", ""))
    lo, hi = (x.isoformat() for x in ctx.period_range)
    if lo <= d <= hi:
        return []
    return [Finding("R05", Severity.REVIEW, "Entry date outside the period",
                    f"The entry is dated {d or 'blank'} but the period runs {lo} to {hi}.",
                    "Confirm the correct posting date or whether it belongs to another period.", {"date": d})]


def r06_duplicates(e, ctx):
    out = []
    if ctx.batch_ids[e.get("id")] > 1:
        out.append(Finding("R06", Severity.BLOCK, "Duplicate entry ID", f"ID {e.get('id')} appears more than once in the batch.",
                           "IDs must be unique so every posting can be traced.", {"id": e.get("id")}))
    same = [x for x in ctx.batch_hashes.get(content_hash(e), []) if x != e.get("id")]
    if same:
        out.append(Finding("R06", Severity.REVIEW, "Same postings as another entry",
                           f"This entry has the same date and amounts as {', '.join(same)}; it may be a duplicate.",
                           "Confirm it is not a duplicate before posting.", {"same_as": same}))
    return out


def r07_fx_reval(e, ctx):
    lines = norm_lines(e)
    accts = {l["account"] for l in lines}
    if not (1110 in accts and accts & {7300, 7310} and "reval" in e.get("description", "").lower()):
        return []
    stated = sum((l["debit"] - l["credit"] for l in lines if l["account"] == 1110), ZERO)
    out = []
    eur = sum((r["debit"] - r["credit"] for r in ctx.tb_rows if r["code"] == 1110 and r["ccy"] == "EUR"), ZERO)
    end, avg, opn = (ctx.fx.get(("EUR", k)) for k in ("period_end", "period_average", "opening"))
    if eur and end and avg and opn:
        cands = {"average-to-closing rate": eur * (end - avg), "opening-to-closing rate": eur * (end - opn)}
        ok = any(abs(stated - c) <= abs(c) * Decimal("0.01") for c in cands.values())
        if not ok:
            detail = "; ".join(f"{k}: {money(v)}" for k, v in cands.items())
            out.append(Finding("R07", Severity.REVIEW, "FX revaluation amount does not reconcile",
                               f"The entry revalues EUR cash by {money(stated)}. Recomputing from the EUR balance (EUR {eur:,.2f}) and the "
                               f"rates file gives {detail}. The entry matches neither (within 1%).",
                               "Ask the preparer which rates and balance were used, or approve it explicitly if the difference is understood.",
                               {"stated": stated, "eur_balance": eur, "recomputed": cands}))
    others = {r["ccy"] for r in ctx.tb_rows if r["code"] == 1110 and r["ccy"] not in ("USD", "EUR")}
    for ccy in sorted(others):
        if (ccy, "period_end") not in ctx.fx:
            bal = sum((r["debit"] - r["credit"] for r in ctx.tb_rows if r["code"] == 1110 and r["ccy"] == ccy), ZERO)
            out.append(Finding("R07", Severity.WARN, f"{ccy} cash is not revalued",
                               f"{ccy} cash of {bal:,.2f} also needs revaluation, but there is no {ccy} period-end rate, so this entry covers EUR only.",
                               f"Provide the {ccy} period-end rate.", {"currency": ccy, "balance": bal}))
    return out


def r08_depreciation_overlap(e, ctx):
    lines = norm_lines(e)
    if not (any(l["account"] == 6500 and l["debit"] > 0 for l in lines) and any(l["account"] == 1211 and l["credit"] > 0 for l in lines)):
        return []
    expense = ctx.tb_net.get(6500, ZERO)
    moved = ctx.prior_net.get(1211, ZERO) - ctx.tb_net.get(1211, ZERO)  # credit movement on accumulated depreciation
    if expense and abs(moved - expense) <= abs(expense) * Decimal("0.01"):
        amt = sum((l["debit"] for l in lines if l["account"] == 6500), ZERO)
        return [Finding("R08", Severity.REVIEW, "Possible duplicate depreciation",
                        f"Accumulated depreciation already grew by {money(moved)} since the prior period, which equals the depreciation expense "
                        f"already in the TB ({money(expense)}). Adding {money(amt)} more may double count.",
                        "Check the fixed asset register: is this amount incremental to what the TB already contains?",
                        {"accum_dep_movement": moved, "expense_in_tb": expense, "entry_amount": amt})]
    return []


def r09_materiality(e, ctx):
    dr, _ = totals(norm_lines(e))
    if dr >= ctx.materiality:
        return [Finding("R09", Severity.WARN, "Above review threshold",
                        f"At {money(dr)} this entry is at or above the {money(ctx.materiality)} review threshold. It was posted, but an approver should sign it off.",
                        "Get approver sign-off and attach the supporting workbook.", {"amount": dr, "threshold": ctx.materiality})]
    return []


def r10_sign_flip(e, ctx):
    net: dict = {}
    for l in norm_lines(e):
        net[l["account"]] = net.get(l["account"], ZERO) + l["debit"] - l["credit"]
    out = []
    for acct, delta in net.items():
        pre = ctx.tb_net.get(acct, ZERO)
        if acct in ctx.coa and pre != 0 and (pre > 0) != (pre + delta > 0) and pre + delta != 0:
            out.append(Finding("R10", Severity.WARN, f"Account {acct} changes sign",
                               f"'{ctx.coa[acct]['name']}' moves from {money(pre)} to {money(pre + delta)} (debit minus credit), flipping its normal side.",
                               "Check that the amount is not too large.", {"account": acct, "before": pre, "after": pre + delta}))
    return out


def r11_tbd_category(e, ctx):
    hit = sorted({l["account"] for l in norm_lines(e) if ctx.coa.get(l["account"], {}).get("cf_category") == "TBD"})
    return [Finding("R11", Severity.INFO, f"Cash-flow category undecided for {a}",
                    f"Account {a} ('{ctx.coa[a]['name']}') has no cash-flow category in the COA, so this entry's effect on the cash-flow statement is unclassified.",
                    "Decide the category in the COA.", {"account": a}) for a in hit]


RULES = [("R01", "structure", r01_structure), ("R02", "balanced", r02_balanced), ("R03", "accounts", r03_accounts),
         ("R04", "circular", r04_circular), ("R05", "period", r05_period), ("R06", "duplicates", r06_duplicates),
         ("R07", "fx_reval", r07_fx_reval), ("R08", "depreciation_overlap", r08_depreciation_overlap),
         ("R09", "materiality", r09_materiality), ("R10", "sign_flip", r10_sign_flip), ("R11", "tbd_category", r11_tbd_category)]


def validate(entry: dict, ctx: Context):
    """Run every rule. Returns (findings, trace). If the entry is malformed (R01), the rest are skipped."""
    findings, trace = [], []
    for rid, _name, fn in RULES:
        if findings and findings[0].rule == "R01":
            trace.append((rid, "skipped"))
            continue
        f = fn(entry, ctx)
        trace.append((rid, "fail" if f else "pass"))
        findings.extend(f)
    return findings, trace
