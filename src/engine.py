from __future__ import annotations

# K12+K13+K16 Trinity-CONTRARIAN 2026-05-17 (Cross-LLM-validated)
def k12_provenance(payload: bytes, key: bytes = b"df-trinity-contrarian-v1") -> dict:
    import hashlib, hmac

    return {
        "payload_hash": hashlib.sha256(payload).hexdigest(),
        "hmac_sha256": hmac.new(key, payload, hashlib.sha256).hexdigest(),
    }


def k13_anchor(payload_hash: str) -> dict:
    from datetime import datetime, timezone

    return {
        "anchor_type": "rfc3161-mock",
        "iso_ts": datetime.now(timezone.utc).isoformat(),
        "payload_hash": payload_hash,
    }


def k16_lock_or_exit(df_name: str):
    import fcntl, os, sys

    lock_path = f"/tmp/df-trinity-{df_name}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        sys.exit(3)


"""DF-LEXVANCE-COMPLIANCE-TRACKER Engine.

Rule-based compliance tracker for GDPR, AI Act, GwG and Berufsrecht evidence.
The real mode is still environment-gated, but the implementation evaluates
caller-supplied records instead of returning fixed placeholder scores.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional


PRUEFBEREICHE = ("GDPR", "AI_ACT", "GWG", "BERUFSRECHT")

RISK_LOW = 0.0
RISK_MED = 0.5
RISK_HIGH = 0.85

_DOMAIN_ALIASES = {
    "AI ACT": "AI_ACT",
    "AIACT": "AI_ACT",
    "AML": "GWG",
    "GELDWAESCHE": "GWG",
    "GELDWÄSCHE": "GWG",
    "LEGAL_ETHICS": "BERUFSRECHT",
    "PROFESSIONAL_ETHICS": "BERUFSRECHT",
}


@dataclass(frozen=True)
class ComplianceResult:
    mandant_id: str
    risk_score: float
    risk_class: str
    findings_count: int
    bereiche_geprueft: tuple
    source: str
    iso_timestamp: str
    phronesis_ticket: Optional[str] = None
    findings: tuple = field(default_factory=tuple)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_risk(score: float) -> str:
    assert 0.0 <= score <= 1.0, f"invalid risk_score: {score}"
    if score >= RISK_HIGH:
        return "HIGH"
    if score >= RISK_MED:
        return "MED"
    return "LOW"


def _domain(value: object) -> str:
    raw = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return _DOMAIN_ALIASES.get(raw, raw)


def _flag(record: Mapping[str, object], name: str, default: bool = False) -> bool:
    value = record.get(name, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ja", "y"}
    return bool(value)


def _number(record: Mapping[str, object], name: str, default: float = 0.0) -> float:
    value = record.get(name, default)
    if value is None or value == "":
        return default
    return float(value)


def _finding(domain: str, code: str, weight: float, detail: str) -> dict:
    return {"domain": domain, "code": code, "weight": weight, "detail": detail}


def _evaluate_record(record: Mapping[str, object]) -> tuple[dict, ...]:
    domain = _domain(record.get("bereich") or record.get("domain"))
    findings = []

    if domain == "GDPR":
        if _flag(record, "personal_data") and not _flag(record, "lawful_basis"):
            findings.append(_finding(domain, "GDPR_LAWFUL_BASIS_MISSING", 0.34, "personal data without lawful basis"))
        if _flag(record, "special_category_data") and not _flag(record, "explicit_consent"):
            findings.append(_finding(domain, "GDPR_ART9_CONSENT_MISSING", 0.28, "special category data without explicit consent"))
        if _number(record, "retention_days", 0) > 365:
            findings.append(_finding(domain, "GDPR_RETENTION_EXCESS", 0.18, "retention period exceeds one year"))

    if domain == "AI_ACT":
        if _flag(record, "ai_system") and str(record.get("risk_tier", "")).strip().lower() == "high":
            if not _flag(record, "human_oversight"):
                findings.append(_finding(domain, "AI_ACT_OVERSIGHT_MISSING", 0.27, "high-risk AI without human oversight"))
            if not _flag(record, "conformity_assessment"):
                findings.append(_finding(domain, "AI_ACT_CONFORMITY_MISSING", 0.24, "high-risk AI without conformity assessment"))

    if domain == "GWG":
        amount = _number(record, "transaction_amount_eur", 0)
        if amount >= 10000 and not _flag(record, "beneficial_owner_verified"):
            findings.append(_finding(domain, "GWG_UBO_UNVERIFIED", 0.24, "large transaction without beneficial-owner verification"))
        if _flag(record, "pep_match") and not _flag(record, "enhanced_due_diligence"):
            findings.append(_finding(domain, "GWG_PEP_EDD_MISSING", 0.22, "PEP match without enhanced due diligence"))

    if domain == "BERUFSRECHT":
        if _flag(record, "conflict_of_interest") and not _flag(record, "conflict_waiver"):
            findings.append(_finding(domain, "BERUFSRECHT_CONFLICT_UNWAIVED", 0.22, "conflict of interest without waiver"))
        if _flag(record, "client_funds") and not _flag(record, "segregated_account"):
            findings.append(_finding(domain, "BERUFSRECHT_CLIENT_FUNDS_NOT_SEGREGATED", 0.2, "client funds not held separately"))

    return tuple(findings)


def _normalise_bereiche(pruef_bereiche: Optional[Iterable[str]]) -> tuple:
    if pruef_bereiche is None:
        return PRUEFBEREICHE
    selected = tuple(_domain(value) for value in pruef_bereiche)
    unknown = tuple(value for value in selected if value not in PRUEFBEREICHE)
    if unknown:
        raise ValueError(f"unknown pruef_bereiche: {unknown}")
    return selected


def evaluate_compliance_evidence(
    mandant_id: str,
    evidence_records: Iterable[Mapping[str, object]],
    pruef_bereiche: Optional[Iterable[str]] = None,
    source: str = "real-api",
    phronesis_ticket: Optional[str] = None,
) -> ComplianceResult:
    assert mandant_id, "mandant_id required"
    bereiche = _normalise_bereiche(pruef_bereiche)
    findings = []

    for record in evidence_records:
        if _domain(record.get("bereich") or record.get("domain")) in bereiche:
            findings.extend(_evaluate_record(record))

    risk_score = min(1.0, round(sum(item["weight"] for item in findings), 2))
    risk_class = _classify_risk(risk_score)
    return ComplianceResult(
        mandant_id=mandant_id,
        risk_score=risk_score,
        risk_class=risk_class,
        findings_count=len(findings),
        bereiche_geprueft=bereiche,
        source=source,
        iso_timestamp=iso_now(),
        phronesis_ticket=phronesis_ticket,
        findings=tuple(findings),
    )


def mock_compliance_check(mandant_id: str, pruef_bereiche: Optional[Iterable[str]] = None) -> ComplianceResult:
    assert mandant_id, "mandant_id required"
    return evaluate_compliance_evidence(
        mandant_id=mandant_id,
        evidence_records=(),
        pruef_bereiche=pruef_bereiche,
        source="mock",
    )


def real_compliance_check(
    mandant_id: str,
    pruef_bereiche: Optional[Iterable[str]] = None,
    phronesis_ticket: Optional[str] = None,
    evidence_records: Optional[Iterable[Mapping[str, object]]] = None,
) -> ComplianceResult:
    assert mandant_id, "mandant_id required"
    if not phronesis_ticket:
        phronesis_ticket = os.environ.get("PHRONESIS_TICKET")
    if not phronesis_ticket:
        return mock_compliance_check(mandant_id, pruef_bereiche)
    return evaluate_compliance_evidence(
        mandant_id=mandant_id,
        evidence_records=evidence_records or (),
        pruef_bereiche=pruef_bereiche,
        source="real-api",
        phronesis_ticket=phronesis_ticket,
    )


def dispatch_compliance_check(
    mandant_id: str,
    pruef_bereiche: Optional[Iterable[str]] = None,
    evidence_records: Optional[Iterable[Mapping[str, object]]] = None,
) -> ComplianceResult:
    real_enabled = os.environ.get("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "").lower() == "true"
    if real_enabled:
        return real_compliance_check(mandant_id, pruef_bereiche, evidence_records=evidence_records)
    return mock_compliance_check(mandant_id, pruef_bereiche)


def needs_escalation(result: ComplianceResult) -> bool:
    return result.risk_class == "HIGH"


def to_audit_record(result: ComplianceResult) -> dict:
    return {
        "ts": result.iso_timestamp,
        "df": "DF-LEXVANCE-COMPLIANCE-TRACKER",
        "mandant_id": result.mandant_id,
        "risk_score": result.risk_score,
        "risk_class": result.risk_class,
        "findings_count": result.findings_count,
        "source": result.source,
        "phronesis_ticket": result.phronesis_ticket or "none",
        "finding_codes": tuple(item["code"] for item in result.findings),
    }
