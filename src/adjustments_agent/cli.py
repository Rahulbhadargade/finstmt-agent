import argparse
import json
import sys
from decimal import Decimal

from .explain import LLMPolisher
from .pipeline import run


def main(argv=None):
    p = argparse.ArgumentParser(prog="adjustments_agent", description="Validate and explain manual journal entries.")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="output")
    p.add_argument("--resolutions", help="JSON file of human approvals for quarantined entries")
    p.add_argument("--materiality", default="500000", help="entries at/above this amount get an approver warning")
    p.add_argument("--llm", action="store_true", help="let an LLM reword explanations (needs ANTHROPIC_API_KEY)")
    a = p.parse_args(argv)
    res = json.load(open(a.resolutions)) if a.resolutions else None
    if res:
        res = {k: v for k, v in res.items() if not k.startswith("_")}
    out = run(a.data, a.out, resolutions=res, polisher=LLMPolisher() if a.llm else None, materiality=Decimal(a.materiality))
    print(f"Run {out['run_id'][:12]}  ->  {a.out}/")
    for r in out["results"]:
        print(f"  {r.entry['id']:7} {r.decision.value:24} {r.entry.get('description')}")
    print(f"Net income: {out['post']['ni_before']:,.2f} -> {out['post']['ni_after']:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
