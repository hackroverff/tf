from __future__ import annotations

from dataclasses import replace

from src.config import load_config
from src.data_generator import SyntheticDataGenerator


def test_editable_initial_ramp_changes_generated_output() -> None:
    """A scenario input must flow to data, not remain a documentary config row."""
    config = load_config()
    baseline = SyntheticDataGenerator(config).generate()
    assumptions = config.assumptions.copy()
    assumptions.loc[assumptions["assumption_id"] == "A042", "value"] = "3.0"
    changed = SyntheticDataGenerator(replace(config, assumptions=assumptions)).generate()

    base_profile = baseline["viral_profile"].sort_values("date").reset_index(drop=True)
    changed_profile = changed["viral_profile"].sort_values("date").reset_index(drop=True)
    assert base_profile.loc[0, "qc_demand_multiplier"] == 2.5
    assert changed_profile.loc[0, "qc_demand_multiplier"] == 3.0
    assert changed_profile.loc[0, "qc_demand_multiplier"] != base_profile.loc[0, "qc_demand_multiplier"]

    base_daily = baseline["daily_sales"]
    changed_daily = changed["daily_sales"]
    base_dp_qc = base_daily[(base_daily["flavor_id"] == "DP") & (base_daily["channel_id"] == "QC")]["true_demand_bottles"].sum()
    changed_dp_qc = changed_daily[(changed_daily["flavor_id"] == "DP") & (changed_daily["channel_id"] == "QC")]["true_demand_bottles"].sum()
    # The 4x uplift remains DP QC only in both configurations.
    assert base_dp_qc > 0 and changed_dp_qc > 0
    for frame in [base_daily, changed_daily]:
        other = frame[(frame["flavor_id"] != "DP") & (frame["viral_multiplier_ground_truth"] > 1.0)]
        assert other.empty
