from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.engine import (
    PRUEFBEREICHE,
    ComplianceResult,
    _classify_risk,
    dispatch_compliance_check,
    evaluate_compliance_evidence,
    mock_compliance_check,
    needs_escalation,
    real_compliance_check,
    to_audit_record,
)


def _clear_env(monkeypatch):
    monkeypatch.delenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", raising=False)
    monkeypatch.delenv("PHRONESIS_TICKET", raising=False)


def test_adversarial_evidence_is_discriminated_by_real_engine(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "true")
    monkeypatch.setenv("PHRONESIS_TICKET", "PT-REAL-001")

    compliant_evidence = (
        {
            "bereich": "GDPR",
            "personal_data": True,
            "lawful_basis": True,
            "special_category_data": True,
            "explicit_consent": True,
            "retention_days": 90,
        },
        {
            "bereich": "AI_ACT",
            "ai_system": True,
            "risk_tier": "high",
            "human_oversight": True,
            "conformity_assessment": True,
        },
        {
            "bereich": "GWG",
            "transaction_amount_eur": 12500,
            "beneficial_owner_verified": True,
            "pep_match": True,
            "enhanced_due_diligence": True,
        },
        {
            "bereich": "BERUFSRECHT",
            "conflict_of_interest": True,
            "conflict_waiver": True,
            "client_funds": True,
            "segregated_account": True,
        },
    )
    adversarial_evidence = tuple(
        {key: (False if isinstance(value, bool) else value) for key, value in record.items()}
        for record in compliant_evidence
    )
    adversarial_evidence = (
        dict(adversarial_evidence[0], retention_days=730),
        dict(adversarial_evidence[1], risk_tier="high", ai_system=True),
        dict(adversarial_evidence[2], transaction_amount_eur=12500, pep_match=True),
        dict(adversarial_evidence[3], conflict_of_interest=True, client_funds=True),
    )

    clean = dispatch_compliance_check("M-CLEAN", evidence_records=compliant_evidence)
    adverse = dispatch_compliance_check("M-ADVERSE", evidence_records=adversarial_evidence)

    assert clean.source == adverse.source == "real-api"
    assert clean.bereiche_geprueft == adverse.bereiche_geprueft == PRUEFBEREICHE
    assert clean.findings_count == 0
    assert adverse.findings_count == len(adverse.findings)
    assert adverse.findings_count > clean.findings_count
    assert adverse.risk_score > clean.risk_score
    assert adverse.risk_class != clean.risk_class
    assert needs_escalation(adverse)
    assert {finding["domain"] for finding in adverse.findings} == set(PRUEFBEREICHE)
    assert {finding["code"] for finding in adverse.findings} == set(to_audit_record(adverse)["finding_codes"])


def test_real_mode_without_ticket_gracefully_uses_mock(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DF_LEXVANCE_COMPLIANCE_REAL_ENABLED", "true")
    result = dispatch_compliance_check(
        "M-NO-TICKET",
        evidence_records=({"bereich": "GDPR", "personal_data": True, "lawful_basis": False},),
    )
    assert result.source == "mock"
    assert result.findings_count == 0
    assert result.phronesis_ticket is None


def test_default_mode_is_disabled_even_when_evidence_is_risky(monkeypatch):
    _clear_env(monkeypatch)
    result = dispatch_compliance_check(
        "M-DEFAULT",
        evidence_records=({"bereich": "GWG", "transaction_amount_eur": 20000, "beneficial_owner_verified": False},),
    )
    assert result.source == "mock"
    assert result.findings_count == 0
    assert result.risk_score == mock_compliance_check("M-DEFAULT").risk_score


def test_subset_checks_only_requested_domain():
    result = evaluate_compliance_evidence(
        "M-SUBSET",
        evidence_records=(
            {"bereich": "GDPR", "personal_data": True, "lawful_basis": False},
            {"bereich": "GWG", "transaction_amount_eur": 20000, "beneficial_owner_verified": False},
        ),
        pruef_bereiche=("GDPR",),
    )
    assert result.bereiche_geprueft == ("GDPR",)
    assert tuple(finding["domain"] for finding in result.findings) == ("GDPR",)


def test_risk_classification_boundaries():
    assert _classify_risk(0.0) == "LOW"
    assert _classify_risk(0.49) == "LOW"
    assert _classify_risk(0.5) == "MED"
    assert _classify_risk(0.84) == "MED"
    assert _classify_risk(0.85) == "HIGH"
    assert _classify_risk(1.0) == "HIGH"


def test_conservation_all_bereiche_default():
    result = real_compliance_check("M-CONS", phronesis_ticket="PT-CONS")
    assert result.bereiche_geprueft == PRUEFBEREICHE
    assert len(result.bereiche_geprueft) == len(set(PRUEFBEREICHE))


def test_needs_escalation_only_for_high():
    low = ComplianceResult(
        mandant_id="x",
        risk_score=0.1,
        risk_class="LOW",
        findings_count=0,
        bereiche_geprueft=PRUEFBEREICHE,
        source="real-api",
        iso_timestamp="2026-05-11T12:00:00+00:00",
    )
    high = ComplianceResult(
        mandant_id="x",
        risk_score=0.9,
        risk_class="HIGH",
        findings_count=1,
        bereiche_geprueft=PRUEFBEREICHE,
        source="real-api",
        iso_timestamp="2026-05-11T12:00:00+00:00",
    )
    assert not needs_escalation(low)
    assert needs_escalation(high)


def test_invalid_risk_score_and_unknown_domain_raise():
    with pytest.raises(AssertionError):
        _classify_risk(1.5)
    with pytest.raises(AssertionError):
        _classify_risk(-0.1)
    with pytest.raises(ValueError):
        evaluate_compliance_evidence("M-BAD", (), pruef_bereiche=("TAX",))
