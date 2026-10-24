from __future__ import annotations

import pandas as pd
import pytest

from src.recommendations import apply_decision, approval_summary, empty_approval_log


def sample_risks() -> pd.DataFrame:
    return pd.DataFrame({
        "risk_id": ["R1", "R2"],
        "status": ["PROPOSED", "PROPOSED"],
        "recommended_action": ["Action 1", "Action 2"],
        "execution_status": ["NOT_EXECUTED_HUMAN_DECISION_ONLY"] * 2,
    })


def test_modify_then_approve_has_complete_audit_trail() -> None:
    risks = sample_risks()
    log = empty_approval_log()
    risks, log = apply_decision(
        risks, log, "R1", "MODIFY", "S&OP Lead", "Reduce scope",
        "Pilot one depot first", "2026-04-01 10:00",
    )
    assert risks.loc[0, "status"] == "PROPOSED_MODIFIED"
    assert risks.loc[0, "recommended_action"] == "Pilot one depot first"
    risks, log = apply_decision(risks, log, "R1", "APPROVE", "COO", "Approved", timestamp="2026-04-02 10:00")
    assert risks.loc[0, "status"] == "APPROVED"
    assert log["log_id"].tolist() == [1, 2]
    assert log["previous_status"].tolist() == ["PROPOSED", "PROPOSED_MODIFIED"]
    assert log["execution_status"].eq("NOT_EXECUTED_HUMAN_DECISION_ONLY").all()
    assert approval_summary(risks) == {"proposed": 1, "approved": 1, "rejected": 0, "executed": 0}


def test_reject_and_invalid_modify() -> None:
    risks = sample_risks()
    risks, log = apply_decision(risks, None, "R2", "REJECT", "COO", "Too expensive", timestamp="2026-04-01")
    assert risks.loc[1, "status"] == "REJECTED"
    assert len(log) == 1
    with pytest.raises(ValueError, match="replacement action"):
        apply_decision(risks, log, "R1", "MODIFY", "S&OP Lead")
