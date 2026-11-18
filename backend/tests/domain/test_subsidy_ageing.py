"""FS-009a: the six ageing figures, without a database."""

from __future__ import annotations

import datetime as dt

from api.domain.subsidy_ageing import FIELDS, FIGURES, ageing

TODAY = dt.date(2026, 10, 3)


def test_a_closed_interval_counts_between_its_dates() -> None:
    got = ageing({"app_inward": dt.date(2026, 7, 1), "submission": dt.date(2026, 7, 13)},
                 None, None, TODAY)
    f = got["inward_to_submission"]
    assert (f.days, f.running) == (12, False)
    assert (f.start, f.end) == (dt.date(2026, 7, 1), dt.date(2026, 7, 13))


def test_an_open_interval_runs_to_today_and_a_missing_start_is_null() -> None:
    got = ageing({"supply": dt.date(2026, 8, 23)}, None, None, TODAY)
    assert (got["today_to_supply"].days, got["today_to_supply"].running) == (41, True)
    assert got["wo_to_tpa_received"].days is None and not got["wo_to_tpa_received"].running


def test_full_fp_closes_the_two_figures_that_end_on_it() -> None:
    got = ageing({"supply": dt.date(2026, 8, 1), "fp_submitted": dt.date(2026, 9, 1)},
                 dt.date(2026, 9, 21), None, TODAY)
    assert (got["today_to_supply"].days, got["today_to_supply"].running) == (51, False)
    assert got["fp_submitted_to_full_fp"].days == 20


def test_a_cancelled_application_stops_counting_at_its_cancellation() -> None:
    got = ageing({"tpa_cleared": dt.date(2026, 9, 1)}, None, dt.date(2026, 9, 11), TODAY)
    f = got["tpa_cleared_to_inspection_sent"]
    assert (f.days, f.running) == (10, False)


def test_every_field_named_is_a_seeded_ggrc_stage_field() -> None:
    seeded = {"app_inward", "submission", "supply", "wo_received", "tpa_received", "tpa_cleared",
              "inspection_sent", "tr_date", "fp_submitted"}
    assert set(FIELDS) == seeded and len(FIGURES) == 6
