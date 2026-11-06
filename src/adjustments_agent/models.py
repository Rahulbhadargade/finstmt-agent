from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    INFO = "INFO"      # note only
    WARN = "WARN"      # post, but tell the user
    REVIEW = "REVIEW"  # quarantine: a human must decide
    BLOCK = "BLOCK"    # reject: cannot be posted as written


SEV_RANK = {"INFO": 0, "WARN": 1, "REVIEW": 2, "BLOCK": 3}


class Decision(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNINGS = "ACCEPTED_WITH_WARNINGS"
    ACCEPTED_BY_OVERRIDE = "ACCEPTED_BY_OVERRIDE"  # quarantined, then approved by a named human
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


POSTED = {Decision.ACCEPTED, Decision.ACCEPTED_WITH_WARNINGS, Decision.ACCEPTED_BY_OVERRIDE}


@dataclass
class Finding:
    rule: str
    severity: Severity
    title: str                  # short headline
    plain: str                  # plain-English explanation for a finance user
    action: str                 # what the user should do next
    facts: dict = field(default_factory=dict)        # evidence: every number used above
    suggestions: list = field(default_factory=list)  # e.g. ranked account candidates (never auto-applied)


@dataclass
class EntryResult:
    entry: dict
    content_hash: str
    decision: Decision
    findings: list
    rule_trace: list            # [(rule_id, "pass" | "fail" | "skipped")]
    override: dict | None = None
    summary: str = ""           # plain-English summary shown to the user
    summary_source: str = "template"  # "template" or "llm"
