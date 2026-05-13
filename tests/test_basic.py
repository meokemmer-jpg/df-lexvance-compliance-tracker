"""Basic Tests fuer DF-LEXVANCE-COMPLIANCE-TRACKER [CRUX-MK].

Per env-var-gated-real-integration-default.md Pflicht-Tests:
1. Default-Mock-Test (keine ENV-Var → mock)
2. ENV-True + PHRONESIS_TICKET → real-api
3. ENV-True ohne PHRONESIS_TICKET → graceful Fallback zu mock
4. Risk-Classification (boundary + edge-case)
5. Conservation: alle 4 Bereiche geprueft default
"""
from __future__ import annotations

import os
import sys
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.engine import (
    PRUEFBEREICHE,
    RISK_LOW, RISK_MED, RISK_HIGH,
    ComplianceResult,
    mock_compliance_check,
    real_compliance_check,
    dispatch_compliance_check,
    needs_escalation,
    to_audit_record,
    _classify_risk,
)


def _clear_env(monkeypatch):
    monkeypatch.delenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", raising=False)
    monkeypatch.delenv("PHRONESIS_TICKET", raising=False)


def test_default_mock_no_env(monkeypatch):
    """Default-Mock: keine ENV-Var → mock_compliance_check."""
    _clear_env(monkeypatch)
    result = dispatch_compliance_check(mandant_id="M-001")
    assert result.source == "mock"
    assert result.risk_class == "MED"
    assert result.phronesis_ticket is None
    assert result.bereiche_geprueft == PRUEFBEREICHE


def test_env_true_with_phronesis_ticket(monkeypatch):
    """ENV=true + PHRONESIS_TICKET → real-api."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "true")
    monkeypatch.setenv("PHRONESIS_TICKET", "PT-2026-05-11-W48-001")
    result = dispatch_compliance_check(mandant_id="M-002")
    assert result.source == "real-api"
    assert result.phronesis_ticket == "PT-2026-05-11-W48-001"


def test_env_true_without_phronesis_ticket_fallback(monkeypatch):
    """ENV=true ohne PHRONESIS_TICKET → graceful Fallback zu mock (LC1)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "true")
    result = dispatch_compliance_check(mandant_id="M-003")
    assert result.source == "mock", "PHRONESIS-Missing muss graceful fallback ausloesen"


def test_risk_classification_boundaries():
    """Edge-Case: Risk-Score-Klassifikation Schwellen."""
    assert _classify_risk(0.0) == "LOW"
    assert _classify_risk(0.49) == "LOW"
    assert _classify_risk(0.5) == "MED"
    assert _classify_risk(0.84) == "MED"
    assert _classify_risk(0.85) == "HIGH"
    assert _classify_risk(1.0) == "HIGH"


def test_conservation_all_bereiche_default():
    """Conservation: alle 4 Bereiche werden default geprueft."""
    result = mock_compliance_check("M-CONS")
    assert set(result.bereiche_geprueft) == set(PRUEFBEREICHE)
    assert len(result.bereiche_geprueft) == 4


def test_needs_escalation_only_for_high():
    """Eskalation nur bei HIGH-Risk."""
    low = ComplianceResult(
        mandant_id="x", risk_score=0.1, risk_class="LOW",
        findings_count=0, bereiche_geprueft=PRUEFBEREICHE,
        source="mock", iso_timestamp="2026-05-11T12:00:00+00:00",
    )
    high = ComplianceResult(
        mandant_id="x", risk_score=0.9, risk_class="HIGH",
        findings_count=0, bereiche_geprueft=PRUEFBEREICHE,
        source="mock", iso_timestamp="2026-05-11T12:00:00+00:00",
    )
    assert not needs_escalation(low)
    assert needs_escalation(high)


def test_audit_record_format():
    """Audit-Record-Format Pflicht-Felder (per audit-trail.md §1)."""
    result = mock_compliance_check("M-AUD")
    rec = to_audit_record(result)
    assert {"ts", "df", "mandant_id", "risk_score", "risk_class", "source", "phronesis_ticket"} <= set(rec.keys())
    assert rec["df"] == "DF-LEXVANCE-COMPLIANCE-TRACKER"


def test_invalid_risk_score_raises():
    """Pre-Condition: risk_score muss in [0.0, 1.0]."""
    with pytest.raises(AssertionError):
        _classify_risk(1.5)
    with pytest.raises(AssertionError):
        _classify_risk(-0.1)
