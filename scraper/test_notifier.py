"""
测试 notifier.py 里的纯函数逻辑（不发真实邮件、不碰网络）。
运行：pytest scraper/test_notifier.py -v
"""

from notifier import (
    date_diff_months, calc_movement_days, find_cutoff, previous_month,
    format_forecast, months_to_fy_reset, format_fiscal_year_note,
    format_uscis_chart_note,
)


class TestDateDiffMonths:
    def test_negative_gap_not_current(self):
        gap = date_diff_months("2024-06-01", "2021-09-01")
        assert gap < 0

    def test_positive_gap_is_current(self):
        gap = date_diff_months("2020-01-01", "2021-09-01")
        assert gap > 0

    def test_same_date_zero_gap(self):
        assert date_diff_months("2021-09-01", "2021-09-01") == 0

    def test_invalid_date_returns_none(self):
        assert date_diff_months("2021-09-01", "Current") is None


class TestCalcMovementDays:
    def test_advance(self):
        mov = calc_movement_days("2021-01-01", "2021-02-01")
        assert mov["type"] == "advance"
        assert mov["days"] == 31

    def test_retract(self):
        mov = calc_movement_days("2021-02-01", "2021-01-01")
        assert mov["type"] == "retract"
        assert mov["days"] == -31

    def test_same_date(self):
        mov = calc_movement_days("2021-01-01", "2021-01-01")
        assert mov["type"] == "same"
        assert mov["days"] == 0

    def test_became_current(self):
        mov = calc_movement_days("2021-01-01", "Current")
        assert mov["type"] == "became_current"

    def test_lost_current(self):
        mov = calc_movement_days("Current", "2021-01-01")
        assert mov["type"] == "lost_current"

    def test_current_to_current_is_same(self):
        mov = calc_movement_days("Current", "Current")
        assert mov["type"] == "same"

    def test_missing_prev_returns_none(self):
        assert calc_movement_days(None, "2021-01-01") is None

    def test_missing_cur_returns_none(self):
        assert calc_movement_days("2021-01-01", None) is None


class TestFindCutoff:
    def test_found(self):
        entries = [
            {"category": "EB2", "country": "China", "cutoff_date": "2021-06-01"},
            {"category": "EB2", "country": "India", "cutoff_date": "2012-01-01"},
        ]
        assert find_cutoff(entries, "EB2", "China") == "2021-06-01"

    def test_not_found(self):
        entries = [{"category": "EB2", "country": "China", "cutoff_date": "2021-06-01"}]
        assert find_cutoff(entries, "EB3", "Mexico") is None


class TestPreviousMonth:
    def test_normal(self):
        assert previous_month(2026, 7) == (2026, 6)

    def test_year_rollover(self):
        assert previous_month(2026, 1) == (2025, 12)


class TestFormatForecast:
    def test_eligible_returns_empty(self):
        assert format_forecast({"eligible": True, "chart": "A"}) == ""
        assert format_forecast({"is_current": True, "chart": "B"}) == ""

    def test_unavailable(self):
        line = format_forecast({"chart": "A", "unavailable": True})
        assert "Unavailable" in line and "获批" in line

    def test_never_reaches(self):
        line = format_forecast({
            "chart": "B", "months_expected": None, "confidence": "low",
        })
        assert "难以排到" in line and "递交" in line

    def test_normal_line_has_range_and_probs(self):
        line = format_forecast({
            "chart": "A", "months_expected": 18.0, "months_optimistic": 12.0,
            "months_conservative": 40.0, "confidence": "medium",
            "prob_current_next": 0.1, "prob_retrogress": 0.25,
        })
        assert "18 个月" in line and "获批" in line
        assert "乐观 12" in line and "保守 40" in line
        assert "~10%" in line and "~25%" in line
        assert "置信度中" in line


class TestMonthsToFyReset:
    def test_september_is_one(self):
        assert months_to_fy_reset(9) == 1

    def test_october_is_twelve(self):
        assert months_to_fy_reset(10) == 12

    def test_january_is_nine(self):
        assert months_to_fy_reset(1) == 9


class TestFormatFiscalYearNote:
    def test_quiet_mid_year_no_note(self):
        assert format_fiscal_year_note(3, retrogressed=False) == ""

    def test_near_year_end_warns(self):
        note = format_fiscal_year_note(9, retrogressed=False)
        assert "财年重置" in note and "1 期" in note

    def test_retrogression_line_added(self):
        note = format_fiscal_year_note(3, retrogressed=True)
        assert "后退" in note

    def test_both_conditions(self):
        note = format_fiscal_year_note(8, retrogressed=True)
        assert "财年重置" in note and "后退" in note


class TestFormatUscisChartNote:
    def test_empty_when_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr("notifier.DATA_DIR", str(tmp_path))
        assert format_uscis_chart_note("EB4") == ""

    def test_employment_uses_employment_value(self, tmp_path, monkeypatch):
        (tmp_path / "uscis_charts.json").write_text(
            '{"month": "2026-09", "family": "B", "employment": "A"}', encoding="utf-8"
        )
        monkeypatch.setattr("notifier.DATA_DIR", str(tmp_path))
        note = format_uscis_chart_note("EB4")
        assert "2026-09" in note and "Chart A" in note and "职业类" in note

    def test_family_uses_family_value(self, tmp_path, monkeypatch):
        (tmp_path / "uscis_charts.json").write_text(
            '{"month": "2026-09", "family": "B", "employment": "A"}', encoding="utf-8"
        )
        monkeypatch.setattr("notifier.DATA_DIR", str(tmp_path))
        note = format_uscis_chart_note("F2A")
        assert "Chart B" in note and "家庭类" in note
