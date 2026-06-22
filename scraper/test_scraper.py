"""
测试 scraper 核心逻辑（不发网络请求）。
运行：pytest test_scraper.py -v
"""

import pytest
from scraper import parse_date, normalize_country, normalize_category, detect_chart_type
from bs4 import BeautifulSoup


# ---- parse_date ----

class TestParseDate:
    def test_normal_date(self):
        assert parse_date("01JAN25") == "2025-01-01"

    def test_four_digit_year(self):
        assert parse_date("15MAR2024") == "2024-03-15"

    def test_current(self):
        assert parse_date("C") == "Current"
        assert parse_date("CURRENT") == "Current"

    def test_unavailable(self):
        assert parse_date("U") is None
        assert parse_date("") is None

    def test_lowercase_input(self):
        assert parse_date("01jan25") == "2025-01-01"

    def test_two_digit_year_boundary(self):
        assert parse_date("01DEC99") == "2099-12-01"
        assert parse_date("01JAN00") == "2000-01-01"

    def test_nbsp(self):
        assert parse_date("\xa001JAN25") == "2025-01-01"

    def test_garbage_returns_none(self):
        assert parse_date("XXX") is None
        assert parse_date("N/A") is None


# ---- normalize_country ----

class TestNormalizeCountry:
    def test_china(self):
        assert normalize_country("CHINA-mainland born") == "China"
        assert normalize_country("China-Mainland Born") == "China"

    def test_india(self):
        assert normalize_country("INDIA") == "India"

    def test_row(self):
        assert normalize_country("All Chargeability Areas Except Those Listed") == "ROW"
        assert normalize_country("ALL CHARGEABILITY") == "ROW"

    def test_philippines(self):
        assert normalize_country("PHILIPPINES") == "Philippines"

    def test_mexico(self):
        assert normalize_country("MEXICO") == "Mexico"


# ---- normalize_category ----

class TestNormalizeCategory:
    def test_eb1(self):
        assert normalize_category("1st", True) == "EB1"
        assert normalize_category("1ST", True) == "EB1"

    def test_eb2(self):
        assert normalize_category("2nd", True) == "EB2"

    def test_eb3(self):
        assert normalize_category("3rd", True) == "EB3"

    def test_eb3_ow(self):
        assert normalize_category("Other Workers", True) == "EB3-OW"

    def test_f1(self):
        assert normalize_category("F1", False) == "F1"
        assert normalize_category("f1", False) == "F1"

    def test_f2a(self):
        assert normalize_category("F2A", False) == "F2A"

    def test_unknown_returns_none(self):
        assert normalize_category("Random", True) is None
        assert normalize_category("X99", False) is None


# ---- detect_chart_type ----

class TestDetectChartType:
    def _make_html(self, text_before: str) -> BeautifulSoup:
        html = f"""<html><body>
        <p>{text_before}</p>
        <table id="target"><tr><td>test</td></tr></table>
        </body></html>"""
        return BeautifulSoup(html, "html.parser")

    def test_detect_chart_a(self):
        soup = self._make_html("A. FINAL ACTION DATES FOR EMPLOYMENT-BASED")
        table = soup.find("table", id="target")
        assert detect_chart_type(table) == "A"

    def test_detect_chart_b(self):
        soup = self._make_html("B. DATES FOR FILING VISA APPLICATIONS")
        table = soup.find("table", id="target")
        assert detect_chart_type(table) == "B"

    def test_default_to_a_when_ambiguous(self):
        soup = self._make_html("Some unrelated text here")
        table = soup.find("table", id="target")
        assert detect_chart_type(table) == "A"

    def test_case_insensitive(self):
        soup = self._make_html("dates for filing applications")
        table = soup.find("table", id="target")
        assert detect_chart_type(table) == "B"


# ---- 集成测试（真实网络，可跳过）----

@pytest.mark.network
def test_real_bulletin_has_data():
    """需要网络：确认最新 Bulletin 解析出非空数据"""
    from scraper import get_bulletin_urls, parse_bulletin_page
    urls = get_bulletin_urls()
    assert len(urls) > 0, "未找到 Bulletin 链接"

    data = parse_bulletin_page(urls[0]["url"])
    assert data is not None
    assert data["year"] >= 2024
    assert len(data["chart_a"]) > 0, f"Chart A 为空（{urls[0]['url']}）"
    assert len(data["chart_b"]) > 0, f"Chart B 为空（{urls[0]['url']}）"

    # 验证每条数据结构
    for entry in data["chart_a"][:5]:
        assert "category" in entry
        assert "country" in entry
        assert "cutoff_date" in entry

    # 确认包含常见类别
    categories = {e["category"] for e in data["chart_a"]}
    assert "EB2" in categories or "EB1" in categories, f"未找到 EB 类别，实际: {categories}"
