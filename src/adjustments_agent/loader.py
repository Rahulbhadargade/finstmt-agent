"""Read the raw input bundle as-is. No cleaning: problems are reported later, not hidden here."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .util import sha256_file

FILES = ["chart_of_accounts.csv", "trial_balance.csv", "prior_period_tb.csv",
         "fx_rates.csv", "manual_adjustments.json"]


@dataclass
class Inputs:
    coa: dict            # code -> {name, type, parent, statement, cf_category, normal_balance}
    tb_rows: list        # [{row, code, name, ccy, debit, credit}]   row = line number in the CSV
    prior_rows: list
    fx: dict             # (ccy, rate_type) -> Decimal
    adjustments: dict
    hashes: dict         # filename -> sha256
    period: str
    period_range: tuple  # (start, end)


def _csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _tb(path):
    out = []
    for i, r in enumerate(_csv(path), start=2):  # header is line 1
        out.append({"row": i, "code": int(r["account_code"]), "name": r["account_name"],
                    "ccy": r["currency"], "debit": Decimal(r["debit"]), "credit": Decimal(r["credit"])})
    return out


def parse_period(p: str) -> tuple:
    year, q = p.split("-Q")
    y, q = int(year), int(q)
    start = date(y, 3 * (q - 1) + 1, 1)
    end = date(y + (q == 4), (3 * q) % 12 + 1, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def load_inputs(data_dir) -> Inputs:
    d = Path(data_dir)
    coa = {}
    for r in _csv(d / "chart_of_accounts.csv"):
        coa[int(r["account_code"])] = {
            "name": r["account_name"], "type": r["account_type"],
            "parent": int(r["parent_code"]) if r["parent_code"] else None,
            "statement": r["statement"], "cf_category": r["cf_category"],
            "normal_balance": r["normal_balance"]}
    fx = {(r["currency"], r["rate_type"]): Decimal(r["rate"]) for r in _csv(d / "fx_rates.csv")}
    with open(d / "manual_adjustments.json", encoding="utf-8") as f:
        adj = json.load(f, parse_float=Decimal)
    return Inputs(coa=coa, tb_rows=_tb(d / "trial_balance.csv"), prior_rows=_tb(d / "prior_period_tb.csv"),
                  fx=fx, adjustments=adj, hashes={n: sha256_file(d / n) for n in FILES},
                  period=adj["period"], period_range=parse_period(adj["period"]))


def net_by_account(rows) -> dict:
    """Debit minus credit per account, as reported (no FX translation; see docs: assumption A1)."""
    out: dict = {}
    for r in rows:
        out[r["code"]] = out.get(r["code"], Decimal(0)) + r["debit"] - r["credit"]
    return out
