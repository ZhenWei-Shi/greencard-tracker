"""
测试前端 dateDiffMonths 等状态判断逻辑的 Python 等价实现。
确保 gap 符号方向正确：gap = cutoff - priority_date
  gap >= 0 → can file (cutoff is on or after priority date)
  gap <  0 → cannot file yet
运行：pytest test_frontend_logic.py -v
"""

from datetime import date


def date_diff_months(priority_date_str: str, cutoff_str: str) -> float | None:
    """等价于 index.html 中的 dateDiffMonths(priority_date, cutoff)"""
    try:
        d1 = date.fromisoformat(priority_date_str)
        d2 = date.fromisoformat(cutoff_str)
        return round((d2 - d1).days / 30.44 * 10) / 10
    except Exception:
        return None


def check_status(priority_date: str, cutoff: str | None) -> str:
    """等价于 index.html 中的 renderMyStatus 判断逻辑"""
    if cutoff == "Current":
        return "current"
    if not cutoff:
        return "unavailable"
    gap = date_diff_months(priority_date, cutoff)
    if gap is None:
        return "unknown"
    if gap >= 0:
        return "current"   # cutoff >= priority_date → can file
    return "waiting"       # cutoff < priority_date → cannot file yet


# ---- 核心回归测试（来自用户报告的 bug）----

class TestGapDirection:
    def test_2024_priority_date_not_current(self):
        """
        用户报告的 bug：优先日期 2024 年，截止日期 2021 年，
        错误地显示"可递交"。gap 应为负数，状态应为 waiting。
        """
        gap = date_diff_months("2024-06-01", "2021-09-01")
        assert gap < 0, f"期望负数 gap，实际: {gap}"
        assert check_status("2024-06-01", "2021-09-01") == "waiting"

    def test_2020_priority_date_is_current(self):
        """优先日期 2020 年，截止日期 2021 年 → 可递交"""
        gap = date_diff_months("2020-01-01", "2021-09-01")
        assert gap > 0, f"期望正数 gap，实际: {gap}"
        assert check_status("2020-01-01", "2021-09-01") == "current"

    def test_same_date_is_current(self):
        """优先日期恰好等于截止日期 → 可递交"""
        gap = date_diff_months("2021-09-01", "2021-09-01")
        assert gap == 0
        assert check_status("2021-09-01", "2021-09-01") == "current"

    def test_gap_magnitude(self):
        """约 33 个月的差值"""
        gap = date_diff_months("2024-06-01", "2021-09-01")
        assert abs(gap) > 30, f"期望约 33 个月，实际: {gap}"

    def test_current_bulletin_value(self):
        assert check_status("2024-06-01", "Current") == "current"

    def test_unavailable_bulletin_value(self):
        assert check_status("2020-01-01", None) == "unavailable"
