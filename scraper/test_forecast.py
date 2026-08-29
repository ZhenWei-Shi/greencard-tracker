"""
测试 forecast.py 的纯函数逻辑（不碰网络 / 文件）。
运行：pytest scraper/test_forecast.py -v
"""

from datetime import date

from forecast import (
    extract_series,
    observed_pace,
    latest_move_days,
    pace_at_month,
    cumulative_advance,
    months_to_current,
    forecast,
)


def make_bulletins(cutoffs, category="EB4", country="China", chart="A"):
    """cutoffs: [(年, 月, cutoff值), ...]，构造最小 bulletin dict 列表。"""
    key = "chart_a" if chart.upper() == "A" else "chart_b"
    out = []
    for y, m, c in cutoffs:
        out.append({
            "year": y, "month": m,
            key: [{"category": category, "country": country, "cutoff_date": c}],
        })
    return out


# ---- extract_series ----

class TestExtractSeries:
    def test_sorts_ascending_regardless_of_input_order(self):
        b = make_bulletins([(2026, 3, "2020-01-01"), (2026, 1, "2019-11-01"), (2026, 2, "2019-12-01")])
        s = extract_series(b, "EB4", "China", "A")
        assert [d.month for d, _ in s] == [1, 2, 3]

    def test_missing_row_gives_none(self):
        b = make_bulletins([(2026, 1, "2020-01-01")])
        s = extract_series(b, "EB4", "India", "A")   # 换个国家
        assert s == [(date(2026, 1, 1), None)]

    def test_chart_b_key(self):
        b = make_bulletins([(2026, 1, "2021-01-01")], chart="B")
        assert extract_series(b, "EB4", "China", "B")[0][1] == "2021-01-01"
        assert extract_series(b, "EB4", "China", "A")[0][1] is None


# ---- observed_pace ----

class TestObservedPace:
    def test_steady_30_days_per_month(self):
        # 每月推进约 30 天：12 个月推进约 360 天
        b = make_bulletins([(2025, m, f"2020-{m:02d}-01") for m in range(1, 13)])
        s = extract_series(b, "EB4", "China", "A")
        pace = observed_pace(s, None)
        assert 28 <= pace <= 32

    def test_current_months_count_against_pace(self):
        b = make_bulletins([
            (2025, 1, "2020-01-01"),
            (2025, 2, "Current"),
            (2025, 3, "2020-02-01"),
        ])
        s = extract_series(b, "EB4", "China", "A")
        # 只有两个数值点，跨 2 个日历月，净推进 31 天 → ~15.5 天/月
        assert observed_pace(s, None) < 20

    def test_too_few_points(self):
        b = make_bulletins([(2025, 1, "2020-01-01")])
        assert observed_pace(extract_series(b, "EB4", "China", "A"), None) is None

    def test_retrogression_negative_pace(self):
        b = make_bulletins([(2025, 1, "2020-06-01"), (2025, 2, "2020-03-01")])
        s = extract_series(b, "EB4", "China", "A")
        assert observed_pace(s, None) < 0


# ---- latest_move_days ----

def test_latest_move_days():
    b = make_bulletins([(2025, 1, "2020-01-01"), (2025, 2, "2020-02-10")])
    s = extract_series(b, "EB4", "China", "A")
    assert latest_move_days(s) == 40

def test_latest_move_days_retrogression():
    b = make_bulletins([(2025, 1, "2020-06-01"), (2025, 2, "2020-05-01")])
    s = extract_series(b, "EB4", "China", "A")
    assert latest_move_days(s) == -31


# ---- 衰减模型 ----

class TestDecayModel:
    def test_pace_at_month_near_term_is_blend(self):
        # y<=12 时 = 0.55*near + 0.2*recent + 0.25*long
        p = pace_at_month(6, near=100, recent=100, mid=100, long_=100)
        assert abs(p - 100) < 1e-9

    def test_pace_converges_to_long_anchor_far_out(self):
        p = pace_at_month(240, near=999, recent=999, mid=40, long_=20)
        # 远期 = 0.6*long + 0.4*mid = 12 + 16 = 28，与 near 无关
        assert abs(p - 28) < 1e-9

    def test_cumulative_advance_monotonic(self):
        a = cumulative_advance(10, 30, 30, 30, 30)
        b = cumulative_advance(20, 30, 30, 30, 30)
        assert b > a > 0

    def test_cumulative_advance_zero(self):
        assert cumulative_advance(0, 30, 30, 30, 30) == 0.0

    def test_months_to_current_inverts_steady_pace(self):
        # 稳定 30 天/月，缺口 300 天 → 约 10 个月
        m = months_to_current(300, 30, 30, 30, 30)
        assert 9 <= m <= 11

    def test_months_to_current_already_covered(self):
        assert months_to_current(0, 30, 30, 30, 30) == 0.0
        assert months_to_current(-50, 30, 30, 30, 30) == 0.0

    def test_months_to_current_never_reaches(self):
        assert months_to_current(100000, 1, 1, 1, 1) is None

    def test_zero_pace_never_reaches(self):
        assert months_to_current(300, 0, 0, 0, 0) is None


# ---- forecast 主入口 ----

class TestForecast:
    def _steady(self, start_year=2024, months=24, step_days=30, cat="EB4", country="China", chart="A"):
        cutoffs = []
        base = date(2019, 1, 1)
        y, m = start_year, 1
        for i in range(months):
            cur = date.fromordinal(base.toordinal() + i * step_days)
            cutoffs.append((y, m, cur.isoformat()))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return make_bulletins(cutoffs, cat, country, chart)

    def test_already_current(self):
        b = make_bulletins([(2026, 1, "Current"), (2026, 2, "Current")])
        r = forecast("2024-12-06", "EB4", "China", b, "A")
        assert r["is_current"] and r["eligible"]
        assert r["months_expected"] == 0.0

    def test_unavailable(self):
        b = make_bulletins([(2026, 1, None), (2026, 2, None)])
        r = forecast("2024-12-06", "EB4", "China", b, "A")
        assert r["unavailable"] and not r["eligible"]
        assert r["months_expected"] is None

    def test_priority_date_already_covered(self):
        b = self._steady(months=12)
        # 最新 cutoff 会远晚于 2019 年的 PD
        r = forecast("2019-01-01", "EB4", "China", b, "A")
        assert r["eligible"] and r["months_expected"] == 0.0

    def test_steady_advance_gives_reasonable_estimate(self):
        b = self._steady(months=24, step_days=30)
        # 24 个月后最新 cutoff ≈ 2019-01-01 + 23*30 天 ≈ 2020-11 月
        # PD 设在最新 cutoff 之后约 300 天
        latest = extract_series(b, "EB4", "China", "A")[-1][1]
        pd = date.fromordinal(date.fromisoformat(latest).toordinal() + 300).isoformat()
        r = forecast(pd, "EB4", "China", b, "A", today=date(2026, 2, 15))
        assert r["distance_days"] > 0
        assert r["months_expected"] is not None
        assert 6 <= r["months_expected"] <= 16
        assert r["months_optimistic"] <= r["months_expected"] <= r["months_conservative"]

    def test_confidence_low_when_barely_moving(self):
        # 每月推进 1 天 → 长期 12 天/年 < 30 → low
        b = self._steady(months=24, step_days=1)
        latest = extract_series(b, "EB4", "China", "A")[-1][1]
        pd = date.fromordinal(date.fromisoformat(latest).toordinal() + 400).isoformat()
        r = forecast(pd, "EB4", "China", b, "A")
        assert r["confidence"] == "low"

    def test_retrogression_raises_retrogress_prob(self):
        cutoffs = [(2025, 1, "2021-06-01"), (2025, 2, "2021-07-01"), (2025, 3, "2021-04-01")]
        b = make_bulletins(cutoffs)
        r = forecast("2024-12-06", "EB4", "China", b, "A", today=date(2025, 3, 20))
        assert r["this_month_days"] < 0
        assert r["prob_retrogress"] >= 0.40
        assert r["prob_advance"] == 0.35

    def test_fiscal_year_end_raises_retrogress_prob(self):
        b = self._steady(months=18, step_days=20)
        latest = extract_series(b, "EB4", "China", "A")[-1][1]
        pd = date.fromordinal(date.fromisoformat(latest).toordinal() + 200).isoformat()
        r_summer = forecast(pd, "EB4", "China", b, "A", today=date(2026, 8, 15))
        r_winter = forecast(pd, "EB4", "China", b, "A", today=date(2026, 1, 15))
        assert r_summer["prob_retrogress"] >= 0.25
        assert r_winter["prob_retrogress"] == 0.10

    def test_scenarios_ordered(self):
        b = self._steady(months=24, step_days=25)
        latest = extract_series(b, "EB4", "China", "A")[-1][1]
        pd = date.fromordinal(date.fromisoformat(latest).toordinal() + 500).isoformat()
        r = forecast(pd, "EB4", "China", b, "A")
        opt, exp, cons = r["months_optimistic"], r["months_expected"], r["months_conservative"]
        assert opt is not None and exp is not None
        assert opt <= exp
        if cons is not None:
            assert exp <= cons
