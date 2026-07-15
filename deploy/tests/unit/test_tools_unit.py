"""
Unit tests for backend/agents/tools.py.

Seam: the three @tool functions as callable Python functions.
DB dependencies are patched per-test.
"""
import json
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Import once — conftest mocks are already in sys.modules
import backend.agents.tools as tools


# ── helpers ──────────────────────────────────────────────────────────────────

def _claim(
    claim_number="CLM-001",
    date_of_service=None,
    diagnosis_codes=None,
    total_amount=Decimal("500.00"),
    denial_reason_code="",
    denial_reason_description="",
    notes="",
):
    from datetime import date
    m = MagicMock()
    m.claim_number = claim_number
    m.date_of_service = date_of_service or date(2026, 7, 1)
    m.diagnosis_codes = diagnosis_codes or ["Z00.00"]
    m.total_amount = total_amount
    m.denial_reason_code = denial_reason_code
    m.denial_reason_description = denial_reason_description
    m.notes = notes
    return m


def _line(procedure_code="99213", procedure_description="Office visit", quantity=1,
          unit_price=Decimal("500.00"), total_price=Decimal("500.00")):
    m = MagicMock()
    m.procedure_code = procedure_code
    m.procedure_description = procedure_description
    m.quantity = quantity
    m.unit_price = unit_price
    m.total_price = total_price
    return m


def _patient(first_name="Jane", last_name="Doe", insurance_provider="BCBS",
             insurance_policy_number="POL-001", insurance_group_number="GRP-001"):
    m = MagicMock()
    m.first_name = first_name
    m.last_name = last_name
    m.insurance_provider = insurance_provider
    m.insurance_policy_number = insurance_policy_number
    m.insurance_group_number = insurance_group_number
    return m


# ── get_claim_details ─────────────────────────────────────────────────────────

def test_get_claim_details_returns_claim_number():
    claim = _claim(claim_number="CLM-TEST-001")
    line = _line()
    with patch.dict(sys.modules, {
        "_workspaces.backend.claims.models": MagicMock(
            Claim=MagicMock(objects=MagicMock(get=MagicMock(return_value=claim))),
            ClaimLineItem=MagicMock(objects=MagicMock(filter=MagicMock(return_value=[line]))),
        )
    }):
        result = tools.get_claim_details("1")

    assert result["claim_number"] == "CLM-TEST-001"


def test_get_claim_details_returns_line_items():
    claim = _claim()
    lines = [_line("99213", "Office visit", 1, Decimal("200"), Decimal("200")),
             _line("36415", "Blood draw",  1, Decimal("50"),  Decimal("50"))]
    with patch.dict(sys.modules, {
        "_workspaces.backend.claims.models": MagicMock(
            Claim=MagicMock(objects=MagicMock(get=MagicMock(return_value=claim))),
            ClaimLineItem=MagicMock(objects=MagicMock(filter=MagicMock(return_value=lines))),
        )
    }):
        result = tools.get_claim_details("1")

    assert len(result["line_items"]) == 2
    codes = [li["procedure_code"] for li in result["line_items"]]
    assert "99213" in codes
    assert "36415" in codes


def test_get_claim_details_amounts_are_strings():
    """Decimals must be serialized to strings so they're JSON-safe."""
    claim = _claim(total_amount=Decimal("1234.56"))
    line = _line(unit_price=Decimal("100.00"), total_price=Decimal("100.00"))
    with patch.dict(sys.modules, {
        "_workspaces.backend.claims.models": MagicMock(
            Claim=MagicMock(objects=MagicMock(get=MagicMock(return_value=claim))),
            ClaimLineItem=MagicMock(objects=MagicMock(filter=MagicMock(return_value=[line]))),
        )
    }):
        result = tools.get_claim_details("1")

    assert result["total_amount"] == "1234.56"
    assert result["line_items"][0]["unit_price"] == "100.00"


# ── get_patient_insurance ─────────────────────────────────────────────────────

def test_get_patient_insurance_returns_all_fields():
    patient = _patient(
        first_name="Jane", last_name="Smith",
        insurance_provider="Aetna",
        insurance_policy_number="AETNA-9999",
        insurance_group_number="GRP-42",
    )
    with patch.dict(sys.modules, {
        "_workspaces.backend.patients.models": MagicMock(
            Patient=MagicMock(objects=MagicMock(get=MagicMock(return_value=patient))),
        )
    }):
        result = tools.get_patient_insurance("7")

    assert result["first_name"] == "Jane"
    assert result["last_name"] == "Smith"
    assert result["insurance_provider"] == "Aetna"
    assert result["insurance_policy_number"] == "AETNA-9999"
    assert result["insurance_group_number"] == "GRP-42"


# ── update_claim_ai_result ────────────────────────────────────────────────────

def test_update_claim_ai_result_json_field_is_parsed():
    """ai_validation_result and ai_denial_analysis must be stored as dicts, not raw strings."""
    mock_claim = MagicMock()
    mock_claim.id = 3
    with patch.dict(sys.modules, {
        "_workspaces.backend.claims.models": MagicMock(
            Claim=MagicMock(objects=MagicMock(get=MagicMock(return_value=mock_claim))),
        )
    }):
        payload = json.dumps({"valid": True, "completeness_score": 95})
        result = tools.update_claim_ai_result("3", "ai_validation_result", payload)

    stored = mock_claim.ai_validation_result
    assert isinstance(stored, dict), f"Expected dict, got {type(stored)}"
    assert stored["valid"] is True
    assert result == {"updated": "ai_validation_result", "claim_id": "3"}


def test_update_claim_ai_result_appeal_draft_stored_as_text():
    """ai_appeal_draft is plain text — must NOT be JSON-parsed."""
    mock_claim = MagicMock()
    with patch.dict(sys.modules, {
        "_workspaces.backend.claims.models": MagicMock(
            Claim=MagicMock(objects=MagicMock(get=MagicMock(return_value=mock_claim))),
        )
    }):
        letter = "Dear Insurer,\n\nWe are appealing claim CLM-001..."
        tools.update_claim_ai_result("3", "ai_appeal_draft", letter)

    assert mock_claim.ai_appeal_draft == letter
    mock_claim.save.assert_called_once()
