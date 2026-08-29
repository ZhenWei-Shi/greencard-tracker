"""
抓到新一期 Visa Bulletin 后，给自己发一封邮件提醒。
配置来自环境变量（见 notify_config.env.example），服务器上通过 .env 提供真实值。
任何环节失败都只打日志，不能影响 scraper 主流程。
"""

import json
import os
import smtplib
from datetime import date
from email.mime.text import MIMEText

from forecast import forecast as run_forecast

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def date_diff_months(priority_date_str: str, cutoff_str: str) -> float | None:
    """等价于 test_frontend_logic.py 里已验证的 dateDiffMonths。gap>=0 才算可递交。"""
    try:
        d1 = date.fromisoformat(priority_date_str)
        d2 = date.fromisoformat(cutoff_str)
        return round((d2 - d1).days / 30.44 * 10) / 10
    except Exception:
        return None


def calc_movement_days(prev_cutoff, cur_cutoff):
    """等价于 index.html 里的 calcMovement。返回 dict 或 None（数据不足以比较）。"""
    if prev_cutoff is None or cur_cutoff is None:
        return None
    if prev_cutoff == cur_cutoff:
        return {"type": "same", "days": 0}
    if cur_cutoff == "Current" and prev_cutoff != "Current":
        return {"type": "became_current", "days": None}
    if prev_cutoff == "Current" and cur_cutoff != "Current":
        return {"type": "lost_current", "days": None}
    try:
        d1 = date.fromisoformat(prev_cutoff)
        d2 = date.fromisoformat(cur_cutoff)
    except Exception:
        return None
    days = (d2 - d1).days
    movement_type = "advance" if days > 0 else "retract" if days < 0 else "same"
    return {"type": movement_type, "days": days}


def find_cutoff(entries, category, country):
    for e in entries:
        if e["category"] == category and e["country"] == country:
            return e["cutoff_date"]
    return None


def load_data_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_bulletin(year, month):
    return load_data_json(f"bulletin_{year}_{month:02d}.json")


def previous_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def load_recent_bulletins(year, month, n=18):
    """从 (year, month) 往回连续读最多 n 期，供 forecast 用。缺的月份跳过。"""
    out = []
    y, m = year, month
    for _ in range(n):
        b = load_bulletin(y, m)
        if b:
            out.append(b)
        y, m = previous_month(y, m)
    return out


def format_forecast(fc: dict) -> str:
    """把 forecast() 的返回值转成一行中文。已可递交 / current 时返回空串。"""
    if fc.get("is_current") or fc.get("eligible"):
        return ""
    verb = "获批" if fc.get("chart") == "A" else "递交"
    if fc.get("unavailable"):
        return f"预测：该类别当前 Unavailable，暂无法估算可{verb}时间\n"
    conf_zh = {"low": "低", "medium": "中", "high": "高"}.get(fc.get("confidence"), "未知")
    me = fc.get("months_expected")
    if me is None:
        return f"预测：按当前推进速度，短期内难以排到可{verb}的位置（置信度{conf_zh}）\n"
    opt, cons = fc.get("months_optimistic"), fc.get("months_conservative")
    if opt is not None and cons is not None:
        rng = f"（乐观 {opt:.0f} / 保守 {cons:.0f} 个月）"
    elif opt is not None:
        rng = f"（乐观约 {opt:.0f} 个月起）"
    else:
        rng = ""
    pn, pr = fc.get("prob_current_next"), fc.get("prob_retrogress")
    tail = ""
    if pn is not None and pr is not None:
        tail = f"；下期就轮到 ~{round(pn * 100)}%，退表风险 ~{round(pr * 100)}%"
    return f"预测：按最近节奏约还需 {me:.0f} 个月可{verb}{rng}，置信度{conf_zh}{tail}\n"


def format_movement(mov) -> str:
    if mov is None:
        return "无法与上期对比（缺少上期数据）"
    if mov["type"] == "same":
        return "与上期持平"
    if mov["type"] == "became_current":
        return "上期还没排到，本期变为 Current（无限制）！"
    if mov["type"] == "lost_current":
        return "本期从 Current 退回有截止日期"
    if mov["type"] == "advance":
        return f"较上期前进了 {mov['days']} 天"
    return f"较上期后退了 {abs(mov['days'])} 天"


def format_gap(priority_date, cur_cutoff) -> str:
    if cur_cutoff == "Current":
        return "当前 Current，可以递交"
    if not cur_cutoff:
        return "该类别/国家暂无排期数据"
    gap = date_diff_months(priority_date, cur_cutoff)
    if gap is None:
        return "日期解析失败，无法计算"
    if gap >= 0:
        return f"已可以递交（排期已过你的优先日 {gap} 个月）"
    return f"还需等待约 {abs(gap)} 个月"


CHART_LABELS = {"A": "Final Action Dates（终裁日期）", "B": "Dates for Filing（递交日期）"}


def build_chart_section(year, month, chart, category, country, priority_date) -> str:
    cur_bulletin = load_bulletin(year, month)
    cur_entries = cur_bulletin[f"chart_{chart.lower()}"] if cur_bulletin else []
    cur_cutoff = find_cutoff(cur_entries, category, country)

    prev_year, prev_month = previous_month(year, month)
    prev_bulletin = load_bulletin(prev_year, prev_month)
    prev_entries = prev_bulletin[f"chart_{chart.lower()}"] if prev_bulletin else []
    prev_cutoff = find_cutoff(prev_entries, category, country) if prev_bulletin else None

    movement = calc_movement_days(prev_cutoff, cur_cutoff)

    fc = run_forecast(priority_date, category, country,
                      load_recent_bulletins(year, month), chart)
    forecast_line = format_forecast(fc)

    return (
        f"【Chart {chart} - {CHART_LABELS[chart]}】\n"
        f"本期截止日：{cur_cutoff}\n"
        f"月环比：{format_movement(movement)}\n"
        f"你的优先日 {priority_date} 状态：{format_gap(priority_date, cur_cutoff)}\n"
        f"{forecast_line}"
    )


def months_to_fy_reset(month: int) -> int:
    """距下一个 10/1 财年重置还有几期（1–12）。"""
    return (10 - month) % 12 or 12


def category_retrogressed(year, month, category, country) -> bool:
    """本期该类别/国家在 A 或 B 图是否出现后退 / 退出 Current。"""
    cur, prev = load_bulletin(year, month), load_bulletin(*previous_month(year, month))
    if not cur or not prev:
        return False
    for chart in ("a", "b"):
        mov = calc_movement_days(
            find_cutoff(prev.get(f"chart_{chart}", []), category, country),
            find_cutoff(cur.get(f"chart_{chart}", []), category, country),
        )
        if mov and mov["type"] in ("retract", "lost_current"):
            return True
    return False


def format_fiscal_year_note(month, retrogressed: bool) -> str:
    m = months_to_fy_reset(month)
    parts = []
    if m <= 2:
        parts.append(
            f"距 10/1 财年重置还有 {m} 期——财年末名额收紧，小类别（含 EB4/SR）"
            "此时最容易被退表或转 Unavailable，之后 10 月通常又放开。"
        )
    if retrogressed:
        parts.append("本期你的类别已出现后退，重点关注下期动向。")
    return ("【财年提示】\n" + "\n".join(parts) + "\n") if parts else ""


def format_notices_section(year, month, category) -> str:
    notices = (load_bulletin(year, month) or {}).get("notices") or []
    if not notices:
        return ""
    cat_tag = category.split("-")[0].upper().replace("EB", "EB-")  # EB4-R -> EB-4
    lines = ["【本期官方公告】"]
    for nt in notices:
        star = " ★" if cat_tag and cat_tag in nt["title"].upper() else ""
        lines.append(f"[{nt['letter']}]{star} {nt['title']}")
    c = next((n for n in notices if n["letter"] == "C"), None)
    if c:
        txt = c["text"][:600] + ("…" if len(c["text"]) > 600 else "")
        lines += ["", f"  ({c['letter']}) {txt}"]
    return "\n".join(lines) + "\n"


def format_uscis_chart_note(category) -> str:
    u = load_data_json("uscis_charts.json") or {}
    if not u.get("month"):
        return ""
    is_family = category.upper().startswith("F")
    which = u.get("family" if is_family else "employment")
    if which not in ("A", "B"):
        return ""
    kind = "家庭类(family)" if is_family else "职业类(employment)"
    label = "Chart A / Final Action Dates" if which == "A" else "Chart B / Dates for Filing"
    return f"【USCIS 递交表】{u['month']}：境内交 I-485，{kind}这个月用 {label}\n"


def build_message(year, month) -> tuple[str, str]:
    category = os.environ["NOTIFY_CATEGORY"]
    country = os.environ["NOTIFY_COUNTRY"]
    priority_date = os.environ["NOTIFY_PRIORITY_DATE"]

    subject = f"Visa Bulletin {year}-{month:02d} 已更新"
    sections = [
        build_chart_section(year, month, chart, category, country, priority_date)
        for chart in ("A", "B")
    ]
    retro = category_retrogressed(year, month, category, country)
    tail = "\n".join(
        s for s in (
            format_uscis_chart_note(category),
            format_fiscal_year_note(month, retro),
            format_notices_section(year, month, category),
        ) if s
    )
    body = f"{subject}\n\n类别：{category}  国家：{country}\n\n" + "\n".join(sections)
    if tail:
        body += "\n" + tail
    return subject, body


def send_email(subject: str, body: str) -> None:
    to_addr = os.environ["NOTIFY_TO_EMAIL"]
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_addr

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, [to_addr], msg.as_string())


def notify_new_bulletin(year, month) -> None:
    try:
        subject, body = build_message(year, month)
        send_email(subject, body)
        print(f"通知邮件已发送：{subject}")
    except Exception as e:
        print(f"通知邮件发送失败（不影响抓取结果）：{e}")
