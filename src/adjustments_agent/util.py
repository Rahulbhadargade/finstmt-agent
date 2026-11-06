from __future__ import annotations

import hashlib
import json
from decimal import Decimal


def money(x: Decimal) -> str:
    x = Decimal(x)
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def to_jsonable(o):
    if isinstance(o, Decimal):
        return str(o)
    if hasattr(o, "value"):  # Enum
        return o.value
    if hasattr(o, "__dataclass_fields__"):
        return {k: to_jsonable(getattr(o, k)) for k in o.__dataclass_fields__}
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    return o


def dumps(o, **kw) -> str:
    return json.dumps(to_jsonable(o), sort_keys=True, **kw)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
