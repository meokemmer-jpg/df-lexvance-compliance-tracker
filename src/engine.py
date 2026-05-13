"""DF-LEXVANCE-COMPLIANCE-TRACKER Engine [CRUX-MK].

Welle-48 Track-A Wave-1 DC-1 Foundation-DF (Gap-Cluster A).
Skelett-Implementation: Compliance-Check fuer GDPR + AI-Act + GwG + Berufsrecht.

ENV-Var-gated Default-Disabled. Mock-Fallback bei Real-Mode-Disabled.

Pre/Post-Conditions:
- Pre: mandant_id (str, required), pruef_bereiche (list optional, default alle 4)
- Post: ComplianceResult mit source ("mock"|"real-api"), risk_score [0.0-1.0], findings_count
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Pflicht-Bereiche (4 Compliance-Domaenen)
PRUEFBEREICHE = ("GDPR", "AI_ACT", "GWG", "BERUFSRECHT")

# Risk-Score-Klassifikation
RISK_LOW = 0.0
RISK_MED = 0.5
RISK_HIGH = 0.85  # Eskalations-Schwelle


def iso_now() -> str:
    """Pre: -; Post: ISO-UTC-Timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ComplianceResult:
    """Pflicht-Felder per env-var-gated-real-integration-default.md Property-3."""
    mandant_id: str
    risk_score: float       # [0.0-1.0]
    risk_class: str         # "LOW"|"MED"|"HIGH"
    findings_count: int
    bereiche_geprueft: tuple
    source: str             # "mock"|"real-api"
    iso_timestamp: str
    phronesis_ticket: Optional[str] = None
    findings: tuple = field(default_factory=tuple)


def _classify_risk(score: float) -> str:
    """Pre: 0.0 <= score <= 1.0; Post: 'LOW'|'MED'|'HIGH'."""
    assert 0.0 <= score <= 1.0, f"invalid risk_score: {score}"
    if score >= RISK_HIGH:
        return "HIGH"
    if score >= RISK_MED:
        return "MED"
    return "LOW"


def mock_compliance_check(mandant_id: str, pruef_bereiche: Optional[tuple] = None) -> ComplianceResult:
    """Mock-Compliance-Check (Default ohne Real-API).

    Pre: mandant_id non-empty
    Post: ComplianceResult mit source='mock', risk_score=0.5 (MED default), findings_count=0
    """
    assert mandant_id, "mandant_id required"
    bereiche = pruef_bereiche or PRUEFBEREICHE
    return ComplianceResult(
        mandant_id=mandant_id,
        risk_score=RISK_MED,
        risk_class="MED",
        findings_count=0,
        bereiche_geprueft=tuple(bereiche),
        source="mock",
        iso_timestamp=iso_now(),
        phronesis_ticket=None,
        findings=(),
    )


def real_compliance_check(
    mandant_id: str,
    pruef_bereiche: Optional[tuple] = None,
    phronesis_ticket: Optional[str] = None,
) -> ComplianceResult:
    """Real-Compliance-Check (NUR mit PHRONESIS_TICKET + ENV-Var Pflicht).

    Pre: mandant_id non-empty; PHRONESIS_TICKET env-var gesetzt
    Post: ComplianceResult mit source='real-api'; fallback zu mock bei Pflicht-Verletzung
    """
    assert mandant_id, "mandant_id required"
    if not phronesis_ticket:
        phronesis_ticket = os.environ.get("PHRONESIS_TICKET")
    if not phronesis_ticket:
        # graceful_degradation per LC1 + Pflicht per env-var-gated-real-integration-default.md
        return mock_compliance_check(mandant_id, pruef_bereiche)
    # Echte Pruef-Engine ist Welle-49+ Task. Skelett: liefert risk_score=0.0 (LOW)
    bereiche = pruef_bereiche or PRUEFBEREICHE
    return ComplianceResult(
        mandant_id=mandant_id,
        risk_score=RISK_LOW,
        risk_class="LOW",
        findings_count=0,
        bereiche_geprueft=tuple(bereiche),
        source="real-api",
        iso_timestamp=iso_now(),
        phronesis_ticket=phronesis_ticket,
        findings=(),
    )


def dispatch_compliance_check(
    mandant_id: str,
    pruef_bereiche: Optional[tuple] = None,
) -> ComplianceResult:
    """Dispatcher mit ENV-Var-Gating (Default-Disabled per env-var-gated-real-integration-default.md).

    Default: mock_compliance_check.
    Real-Mode: nur wenn DF_LEXVANCE_COMPLIANCE_REAL_ENABLED='true' UND PHRONESIS_TICKET gesetzt.
    """
    real_enabled = os.environ.get("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "").lower() == "true"
    if real_enabled:
        return real_compliance_check(mandant_id, pruef_bereiche)
    return mock_compliance_check(mandant_id, pruef_bereiche)


def needs_escalation(result: ComplianceResult) -> bool:
    """Pre: result valid; Post: True iff HIGH-Risk."""
    return result.risk_class == "HIGH"


def to_audit_record(result: ComplianceResult) -> dict:
    """Serialize ComplianceResult fuer audit-log.jsonl (per audit-trail.md §1)."""
    return {
        "ts": result.iso_timestamp,
        "df": "DF-LEXVANCE-COMPLIANCE-TRACKER",
        "mandant_id": result.mandant_id,
        "risk_score": result.risk_score,
        "risk_class": result.risk_class,
        "source": result.source,
        "phronesis_ticket": result.phronesis_ticket or "none",
    }
