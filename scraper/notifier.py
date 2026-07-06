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


def load_bulletin(year, month):
    path = os.path.join(DATA_DIR, f"bulletin_{year}_{month:02d}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def previous_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


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


def build_message(year, month) -> tuple[str, str]:
    category = os.environ["NOTIFY_CATEGORY"]
    country = os.environ["NOTIFY_COUNTRY"]
    chart = os.environ.get("NOTIFY_CHART", "A")
    priority_date = os.environ["NOTIFY_PRIORITY_DATE"]

    cur_bulletin = load_bulletin(year, month)
    cur_entries = cur_bulletin[f"chart_{chart.lower()}"] if cur_bulletin else []
    cur_cutoff = find_cutoff(cur_entries, category, country)

    prev_year, prev_month = previous_month(year, month)
    prev_bulletin = load_bulletin(prev_year, prev_month)
    prev_entries = prev_bulletin[f"chart_{chart.lower()}"] if prev_bulletin else []
    prev_cutoff = find_cutoff(prev_entries, category, country) if prev_bulletin else None

    movement = calc_movement_days(prev_cutoff, cur_cutoff)

    subject = f"Visa Bulletin {year}-{month:02d} 已更新"
    body = (
        f"{subject}\n\n"
        f"类别：{category}  国家：{country}  Chart：{chart}\n"
        f"本期截止日：{cur_cutoff}\n"
        f"月环比：{format_movement(movement)}\n"
        f"你的优先日 {priority_date} 状态：{format_gap(priority_date, cur_cutoff)}\n"
    )
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
