"""The shape gate passes a template. A substance gate should not.

desk_synthesis_contract checks that a first-turn reply is not empty, claims no
execution, asks exactly one question, and uses provisional wording. The template
that shipped in the built product satisfies every one of those, for any objective.
These pin the difference between sounding like an interpretation and naming one.
"""

from __future__ import annotations

from scripts.research_data_mcp.desk_synthesis_contract import first_turn_reply_is_acceptable
from scripts.research_data_mcp.synthesis.reply_substance import (
    named_datasets,
    reply_substance,
    substance_violations,
)

IDS = ["idn_fry_daily_cross_section", "public_macro_ff_factors_daily",
       "stablecoin_trust_engagement_weekly"]

BOILERPLATE = (
    "Provisionally, Historical stablecoin attention should be treated as a latent "
    "research measure, not as an observed field. The mapped Library inputs are "
    "candidate evidence: core signals support the construct, while validation "
    "sources test whether it behaves as intended. Which signal should define the "
    "primary measure?"
)

GROUNDED = (
    "Provisionally I read this as a weekly excess-return panel at yahoo_symbol × week, "
    "2020 onward, built from idn_fry_daily_cross_section with "
    "public_macro_ff_factors_daily as the risk-free benchmark. Which factor set "
    "should define the benchmark?"
)


def test_the_shape_gate_accepts_the_template():
    """This is why it shipped — the contract it had to satisfy was about wording."""
    assert first_turn_reply_is_acceptable(BOILERPLATE) is True


def test_the_substance_gate_rejects_the_same_template():
    result = reply_substance(BOILERPLATE, IDS)
    assert result["complete"] is False
    assert set(result["missing"]) == {"grain", "period", "evidence"}


def test_a_grounded_reply_names_all_three():
    result = reply_substance(GROUNDED, IDS)
    assert result["complete"] is True
    assert result["grain"] == "yahoo_symbol × week"
    assert result["period"] == "2020 onward"
    assert result["evidence"] == ["idn_fry_daily_cross_section", "public_macro_ff_factors_daily"]


def test_the_template_reads_the_same_for_any_objective():
    other = BOILERPLATE.replace("Historical stablecoin attention", "Taiwan issuer filings")
    assert reply_substance(other, IDS)["missing"] == reply_substance(BOILERPLATE, IDS)["missing"]


def test_grain_is_recognised_in_the_forms_researchers_write():
    for phrasing in ("asset × week", "asset-week", "per asset per week", "one row per issuer month"):
        assert reply_substance(f"a panel at {phrasing}, 2020 onward, from idn_fry_daily_cross_section",
                               IDS)["grain"], phrasing


def test_period_is_recognised_as_a_range_or_a_start():
    for phrasing in ("2021–2026", "from 2020", "2021 onward", "2019 to 2026"):
        assert reply_substance(f"asset × week, {phrasing}, idn_fry_daily_cross_section",
                               IDS)["period"], phrasing


def test_a_dataset_that_does_not_exist_is_not_evidence():
    text = "asset × week, 2020 onward, from totally_made_up_panel"
    assert reply_substance(text, IDS)["evidence"] == []
    assert "no_evidence_named" in substance_violations(text, IDS)


def test_named_datasets_needs_the_registry_to_judge():
    assert named_datasets("built from idn_fry_daily_cross_section", []) == []
    assert named_datasets("built from idn_fry_daily_cross_section", IDS) == ["idn_fry_daily_cross_section"]


def test_violations_name_what_is_missing():
    assert substance_violations(BOILERPLATE, IDS) == [
        "no_grain_named", "no_period_named", "no_evidence_named"]
    assert substance_violations(GROUNDED, IDS) == []


def test_presence_is_necessary_and_not_sufficient():
    """A reply can name all three and still be wrong. This gate refuses the empty
    ones; it does not certify the rest."""
    wrong = ("asset × week, 2020 onward, from stablecoin_trust_engagement_weekly, "
             "which measures Indonesian equity returns. Is that right?")
    assert reply_substance(wrong, IDS)["complete"] is True


def test_an_empty_reply_is_missing_everything():
    assert reply_substance("", IDS)["missing"] == ["grain", "period", "evidence"]
