"""
抓取 Visa Bulletin 并输出到 ../data/ 目录的 JSON 文件。
运行：python scraper.py [--history N]
"""

import re
import json
import os
import argparse
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BASE_URL = "https://adoption.state.gov"
BULLETIN_INDEX = f"{BASE_URL}/content/travel/en/legal/visa-law0/visa-bulletin.html"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

COUNTRY_ALIASES = {
    "ALL CHARGEABILITY": "ROW",
    "CHINA": "China",
    "INDIA": "India",
    "MEXICO": "Mexico",
    "PHILIPPINES": "Philippines",
}

# 表头第一格关键词 → 分类模式
FAMILY_HEADER   = "FAMILY"
EMPLOYMENT_HEADER = "EMPLOYMENT"

# 类别名称映射（大写匹配前缀）
EB_CATEGORIES = {
    "1ST": "EB1", "2ND": "EB2", "3RD": "EB3",
    "OTHER WORKERS": "EB3-OW",
    "4TH": "EB4",
    "CERTAIN RELIGIOUS": "EB4-R",
    "5TH": "EB5",
    "TARGETED EMPLOYMENT": "EB5-TEA",
    "SET-ASIDE": "EB5-TEA",
    "UNRESERVED": "EB5-UR",
}

FB_CATEGORIES = {
    "F1": "F1", "F2A": "F2A", "F2B": "F2B", "F3": "F3", "F4": "F4",
}


def parse_date(raw: str) -> str | None:
    raw = raw.strip().upper().replace("\xa0", "")
    if raw in ("C", "CURRENT"):
        return "Current"
    if raw in ("U", "UNAVAILABLE", ""):
        return None
    m = re.match(r"(\d{2})([A-Z]{3})(\d{2,4})", raw)
    if not m:
        return None
    day, mon, yr = m.groups()
    year = int(yr) if len(yr) == 4 else 2000 + int(yr)
    month = MONTH_MAP.get(mon)
    if not month:
        return None
    return f"{year:04d}-{month:02d}-{int(day):02d}"


def normalize_country(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip().upper()
    for key, val in COUNTRY_ALIASES.items():
        if raw.startswith(key):
            return val
    return raw.title()


def normalize_category(raw: str, is_employment: bool) -> str | None:
    raw = re.sub(r"\s+", " ", raw).strip().upper()
    src = EB_CATEGORIES if is_employment else FB_CATEGORIES
    for key, val in src.items():
        if raw.startswith(key):
            return val
    return None


def detect_chart_type(table) -> str:
    """向上搜索文本节点，找 FINAL ACTION / DATES FOR FILING"""
    for text_node in table.find_all_previous(string=True):
        txt = text_node.strip().upper()
        if not txt:
            continue
        if "FINAL ACTION" in txt:
            return "A"
        if "DATE FOR FILING" in txt or "DATES FOR FILING" in txt:
            return "B"
        # 遇到另一个表格类型标题就停止
        if "EMPLOYMENT-BASED" in txt or "FAMILY-SPONSORED" in txt:
            break
    return "A"


def parse_table(table, is_employment: bool) -> list[dict]:
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    header_cells = [td.get_text(" ", strip=True) for td in rows[0].find_all(["td", "th"])]
    # 第一格是类型标签（Family-Sponsored / Employment-based），跳过
    countries = [normalize_country(c) for c in header_cells[1:]]

    entries = []
    for row in rows[1:]:
        cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
        if not cells:
            continue
        category = normalize_category(cells[0], is_employment)
        if not category:
            continue
        for i, country in enumerate(countries):
            if i + 1 >= len(cells):
                break
            entries.append({
                "category": category,
                "country": country,
                "cutoff_date": parse_date(cells[i + 1]),
            })
    return entries


def get_bulletin_urls() -> list[dict]:
    resp = requests.get(BULLETIN_INDEX, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, urls = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "visa-bulletin-for" in href.lower():
            full = href if href.startswith("http") else BASE_URL + href
            if full not in seen:
                seen.add(full)
                urls.append({"url": full, "text": a.get_text(strip=True)})

    # 索引页链接顺序不保证按时间排列（adoption.state.gov 镜像会把某些月份排在前面），
    # 这里按公告的 年-月 从新到旧排序，保证 --history N 取到的是最新的 N 期。
    def sort_key(item):
        m = re.search(r"visa-bulletin-for-(\w+)-(\d{4})", item["url"])
        if not m:
            return (0, 0)
        return (int(m.group(2)), MONTH_MAP.get(m.group(1).upper()[:3], 0))

    urls.sort(key=sort_key, reverse=True)
    return urls


def nest_entries(entries: list[dict]) -> dict:
    """把扁平的 [{category, country, cutoff_date}] 折叠成 {类别: {国家: 值}} 两层对象，
    方便前端 / 预测直接寻址（data.final_action['EB4']['China']），不用再遍历 find。"""
    out: dict = {}
    for e in entries:
        out.setdefault(e["category"], {})[e["country"]] = e["cutoff_date"]
    return out


def parse_bulletin_page(url: str) -> dict | None:
    m = re.search(r"visa-bulletin-for-(\w+)-(\d{4})", url)
    if not m:
        return None
    month_name, year = m.group(1).upper(), int(m.group(2))
    month = MONTH_MAP.get(month_name[:3])
    if not month:
        return None

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {"year": year, "month": month, "url": url, "chart_a": [], "chart_b": []}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 4:
            continue
        header_cells = [td.get_text(" ", strip=True).upper() for td in rows[0].find_all(["td", "th"])]
        if not header_cells:
            continue

        first = header_cells[0]
        if FAMILY_HEADER in first:
            is_employment = False
        elif EMPLOYMENT_HEADER in first:
            is_employment = True
        else:
            continue

        chart_type = detect_chart_type(table)
        entries = parse_table(table, is_employment)

        if chart_type == "A":
            result["chart_a"].extend(entries)
        else:
            result["chart_b"].extend(entries)

    # 扁平数组保留（前端旧逻辑、notifier 都还在用），额外产出嵌套结构：
    #   final_action = Chart A（终裁日期）  filing = Chart B（可递交日期）
    # 值仍是三态：日期字符串 / "Current" / null。
    result["final_action"] = nest_entries(result["chart_a"])
    result["filing"] = nest_entries(result["chart_b"])

    return result


def save_bulletin(data: dict) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"bulletin_{data['year']}_{data['month']:02d}.json"
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {filename}  (A:{len(data['chart_a'])} B:{len(data['chart_b'])})")
    return path


def rebuild_index():
    files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.startswith("bulletin_") and f.endswith(".json")],
        reverse=True,
    )
    index = []
    for fname in files:
        path = os.path.join(DATA_DIR, fname)
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        # 顺手给老快照补上嵌套结构（早于本次改动抓的文件没有 final_action / filing）
        if "final_action" not in d or "filing" not in d:
            d["final_action"] = nest_entries(d.get("chart_a", []))
            d["filing"] = nest_entries(d.get("chart_b", []))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        index.append({"year": d["year"], "month": d["month"], "file": fname})

    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"bulletins": index, "updated_at": datetime.now(timezone.utc).isoformat()},
            f, indent=2,
        )
    print(f"index.json 已更新，共 {len(index)} 期")


def get_latest_from_index():
    """读取当前 index.json 里记录的最新一期 (year, month)，没有则返回 None。"""
    path = os.path.join(DATA_DIR, "index.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        idx = json.load(f)
    bulletins = idx.get("bulletins", [])
    return (bulletins[0]["year"], bulletins[0]["month"]) if bulletins else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, default=1,
                        help="抓取最近 N 期（默认 1）")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    old_latest = get_latest_from_index()

    urls = get_bulletin_urls()
    n = min(args.history, len(urls))
    print(f"找到 {len(urls)} 期 Bulletin，抓取最近 {n} 期...")

    for i, item in enumerate(urls[:n]):
        print(f"[{i+1}/{n}] {item['url']}")
        try:
            data = parse_bulletin_page(item["url"])
            if data:
                save_bulletin(data)
        except Exception as e:
            print(f"  跳过（错误：{e}）")

    rebuild_index()

    new_latest = get_latest_from_index()
    if new_latest and new_latest != old_latest:
        try:
            import notifier
            notifier.notify_new_bulletin(*new_latest)
        except Exception as e:
            print(f"通知模块调用失败（不影响抓取结果）：{e}")

    print("完成")


if __name__ == "__main__":
    main()
