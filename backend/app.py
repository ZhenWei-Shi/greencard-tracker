from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, date
from models import get_db, init_db

app = Flask(__name__)
CORS(app)

init_db()

# ---- 工具函数 ----

def date_diff_months(d1_str: str, d2_str: str) -> float | None:
    """计算两个 YYYY-MM-DD 日期相差的月数（d2 - d1）"""
    try:
        d1 = date.fromisoformat(d1_str)
        d2 = date.fromisoformat(d2_str)
        return round((d2 - d1).days / 30.44, 1)
    except Exception:
        return None


def row_to_dict(row) -> dict:
    return dict(row)


# ---- API 端点 ----

@app.get("/api/bulletin/latest")
def latest_bulletin():
    """返回最新一期所有排期数据"""
    chart = request.args.get("chart", "A")
    conn = get_db()
    row = conn.execute(
        "SELECT year, month FROM visa_bulletin ORDER BY year DESC, month DESC LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "暂无数据，请先运行 scraper.py"}), 404

    year, month = row["year"], row["month"]
    rows = conn.execute(
        "SELECT category, country, cutoff_date FROM visa_bulletin "
        "WHERE year=? AND month=? AND chart_type=? ORDER BY category, country",
        (year, month, chart),
    ).fetchall()
    conn.close()

    return jsonify({
        "year": year,
        "month": month,
        "chart": chart,
        "data": [row_to_dict(r) for r in rows],
    })


@app.get("/api/bulletin/history")
def bulletin_history():
    """返回指定类别+国家的历史排期走势（最近 24 期）"""
    category = request.args.get("category", "EB2")
    country = request.args.get("country", "China")
    chart = request.args.get("chart", "A")

    conn = get_db()
    rows = conn.execute(
        """
        SELECT year, month, cutoff_date
        FROM visa_bulletin
        WHERE category=? AND country=? AND chart_type=?
        ORDER BY year DESC, month DESC
        LIMIT 24
        """,
        (category, country, chart),
    ).fetchall()
    conn.close()

    history = [row_to_dict(r) for r in reversed(rows)]
    return jsonify({"category": category, "country": country, "chart": chart, "history": history})


@app.get("/api/check")
def check_priority_date():
    """
    检查用户的 Priority Date 当前状态。
    参数：priority_date=2021-06-01&category=EB2&country=China&chart=A
    """
    priority_date = request.args.get("priority_date")
    category = request.args.get("category", "EB2")
    country = request.args.get("country", "China")
    chart = request.args.get("chart", "A")

    if not priority_date:
        return jsonify({"error": "缺少 priority_date 参数"}), 400

    conn = get_db()
    # 最新排期
    row = conn.execute(
        """
        SELECT year, month, cutoff_date
        FROM visa_bulletin
        WHERE category=? AND country=? AND chart_type=?
        ORDER BY year DESC, month DESC LIMIT 1
        """,
        (category, country, chart),
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "未找到该类别/国家的数据"}), 404

    cutoff = row["cutoff_date"]
    status = "unknown"
    months_gap = None

    if cutoff == "Current":
        status = "current"
        months_gap = 0
    elif cutoff is None:
        status = "unavailable"
    else:
        months_gap = date_diff_months(priority_date, cutoff)
        if months_gap is None:
            status = "unknown"
        elif months_gap > 0:
            status = "not_current"  # 排期还未到
        else:
            status = "current"      # 排期已过，可提交

    return jsonify({
        "priority_date": priority_date,
        "category": category,
        "country": country,
        "chart": chart,
        "bulletin_year": row["year"],
        "bulletin_month": row["month"],
        "cutoff_date": cutoff,
        "status": status,
        "months_gap": months_gap,
    })


@app.get("/api/profile")
def get_profile():
    """获取用户保存的设置"""
    conn = get_db()
    row = conn.execute("SELECT * FROM user_profile WHERE id=1").fetchone()
    conn.close()
    return jsonify(row_to_dict(row) if row else {})


@app.post("/api/profile")
def save_profile():
    """保存用户设置"""
    data = request.get_json(force=True)
    conn = get_db()
    conn.execute(
        """
        UPDATE user_profile SET
            category=?, country=?, priority_date=?, email=?, alert_days=?
        WHERE id=1
        """,
        (
            data.get("category"),
            data.get("country"),
            data.get("priority_date"),
            data.get("email"),
            data.get("alert_days", 90),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/categories")
def list_categories():
    """返回数据库中所有可用的签证类别"""
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT category FROM visa_bulletin ORDER BY category"
    ).fetchall()
    conn.close()
    return jsonify([r["category"] for r in rows])


@app.get("/api/countries")
def list_countries():
    """返回数据库中所有可用的国家"""
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT country FROM visa_bulletin ORDER BY country"
    ).fetchall()
    conn.close()
    return jsonify([r["country"] for r in rows])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
