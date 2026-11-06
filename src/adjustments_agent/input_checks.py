"""Data-quality checks on the raw inputs. These never change the data; they produce a findings list
that is shown to the user and written to output/input_findings.json."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .suggest import suggest_accounts
from .util import money


def check_inputs(inp) -> list:
    out = []

    def add(rid, sev, title, detail, **facts):
        out.append({"id": rid, "severity": sev, "title": title, "detail": detail, "facts": facts})

    # DQ-01 TB balance (nominal, as reported)
    dr = sum(r["debit"] for r in inp.tb_rows)
    cr = sum(r["credit"] for r in inp.tb_rows)
    if dr != cr:
        add("DQ-01", "BLOCK", "Trial balance does not balance",
            f"Total debits {money(dr)} vs total credits {money(cr)}: difference {money(dr - cr)} (as reported, "
            "before any FX translation). Not forced to balance; this must be explained, not plugged.",
            debits=dr, credits=cr, difference=dr - cr)

    # DQ-02 duplicate (account, currency) rows
    seen = defaultdict(list)
    for r in inp.tb_rows:
        seen[(r["code"], r["ccy"])].append(r)
    for (code, ccy), rows in seen.items():
        if len(rows) > 1:
            add("DQ-02", "REVIEW", f"Account {code} appears {len(rows)} times in {ccy}",
                "Rows " + ", ".join(f"line {r['row']} ({money(r['debit'] - r['credit'])})" for r in rows) +
                ". They are summed here, but one may be a duplicate export row.",
                code=code, currency=ccy, rows=[r["row"] for r in rows])

    # DQ-03 accounts not in COA (current + prior TB)
    for label, rows in (("trial_balance", inp.tb_rows), ("prior_period_tb", inp.prior_rows)):
        for r in rows:
            if r["code"] not in inp.coa:
                best = suggest_accounts(r["code"], [r["name"]], inp.coa, top=1)[0]
                hint = (f" Possible match (suggestion only): {best['account']} '{best['name']}', confidence {best['confidence']:.2f}."
                        if best["confidence"] >= 0.4 else "")
                add("DQ-03", "REVIEW", f"Account {r['code']} '{r['name']}' is not in the COA ({label})",
                    f"Line {r['row']} carries {money(r['debit'] - r['credit'])} on an account with no COA mapping.{hint}",
                    code=r["code"], file=label, row=r["row"])

    # DQ-04 FX completeness
    for ccy in sorted({r["ccy"] for r in inp.tb_rows} - {"USD"}):
        for rt in ("period_end", "period_average"):
            if (ccy, rt) not in inp.fx:
                add("DQ-04", "REVIEW", f"No {rt} FX rate for {ccy}",
                    f"{ccy} balances exist in the TB but fx_rates.csv has no {rt} rate. Translation and "
                    f"revaluation for {ccy} cannot be verified.", currency=ccy, rate_type=rt)

    # DQ-05 COA hygiene
    children = {v["parent"] for v in inp.coa.values() if v["parent"]}
    for code, a in inp.coa.items():
        if a["type"] == "Header" and code not in children:
            add("DQ-05", "INFO", f"COA header {code} '{a['name']}' has no child accounts", "Nothing maps under it.", code=code)
        if a["cf_category"] == "TBD":
            add("DQ-05", "WARN", f"COA account {code} '{a['name']}' has cash-flow category TBD",
                "The cash-flow statement cannot classify this account until a category is chosen.", code=code)
        if a["type"] == "Header" and not a["normal_balance"]:
            add("DQ-05", "INFO", f"COA header {code} has no normal balance", "Harmless for a header.", code=code)

    # DQ-06 prior-period account list differs
    cur = {r["code"] for r in inp.tb_rows if r["code"] in inp.coa and inp.coa[r["code"]]["statement"] == "BS"}
    pri = {r["code"] for r in inp.prior_rows if r["code"] in inp.coa and inp.coa[r["code"]]["statement"] == "BS"}
    if cur != pri:
        add("DQ-06", "WARN", "Balance-sheet account lists differ between periods",
            f"Only in current: {sorted(cur - pri)}; only in prior: {sorted(pri - cur)}.")
    if any(r["code"] >= 4000 for r in inp.prior_rows):
        add("DQ-06", "WARN", "Prior-period TB has almost no P&L accounts",
            "It looks post-close (balance sheet only), but one P&L-style account (6905) is present. "
            "Retained earnings moved without a visible closing entry; confirm pre- vs post-close.")
    return out
