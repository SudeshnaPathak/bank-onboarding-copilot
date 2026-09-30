from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

_PATH = Path(__file__).with_name("rules.yaml")


@lru_cache
def load_rules() -> dict:
    return yaml.safe_load(_PATH.read_text())


def rules_version() -> dict:
    return {"version": load_rules()["version"], "sha256": hashlib.sha256(_PATH.read_bytes()).hexdigest()[:12]}


def threshold(name: str):
    return load_rules()["thresholds"][name]


def make_flag(code: str, message: str, evidence: dict, confirmed_by_customer: bool = False) -> dict:
    spec = load_rules()["flags"][code]
    return {"code": code, "severity": spec["severity"], "title": spec["title"], "message": message,
            "evidence": evidence, "confirmed_by_customer": confirmed_by_customer}


def score_flags(flags: list[dict]) -> tuple[int, list[dict], str]:
    rules = load_rules()
    total, breakdown = 100.0, []
    for f in flags:
        base = rules["flags"][f["code"]]["penalty"]
        factor = rules["confirmed_multiplier"] if f.get("confirmed_by_customer") else 1.0
        penalty = round(base * factor, 1)
        total -= penalty
        breakdown.append({"code": f["code"], "title": f["title"], "penalty": penalty,
                          "reduced_because_confirmed": factor != 1.0})
    score = max(int(round(total)), 0)
    bands = rules["bands"]
    band = "clean" if score >= bands["ready"] else "review" if score >= bands["review"] else "attention"
    return score, breakdown, band
