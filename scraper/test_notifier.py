"""
测试 notifier.py 里的纯函数逻辑（不发真实邮件、不碰网络）。
运行：pytest scraper/test_notifier.py -v
"""

from notifier import date_diff_months, calc_movement_days, find_cutoff, previous_month


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
