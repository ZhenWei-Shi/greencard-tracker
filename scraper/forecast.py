"""
排期预测（纯函数，不碰网络 / 文件 / 时间以外的副作用）。

思路借鉴自公开站 gc.jmjvc.us 的做法，核心是一个「随时间衰减的推进速度」模型：
近期用实测节奏，越往远越锚定长期历史均值，避免拿最近两三个月的异常速度直接线性外推
出「三个月就排到」这种误导性结论。再套二分搜索求「还需几个月排到你的优先日」。

不是机器学习，就是一套启发式 + 阈值。对个人自用足够，且比线性外推稳健。

主入口：forecast(priority_date, category, country, bulletins, chart)

    bulletins: 一串 bulletin dict（含 year / month / chart_a / chart_b），顺序随意。
    返回见 forecast() 文档字符串。

前端 index.html 里有一份等价的 JS 实现，改这里记得同步那边。
"""

from datetime import date


# 每类别-国家的长期推进速度兜底表，单位「天/年」。
# 只在历史数据不足（<约 2 年）时用；有足够历史时一律以实测为准。
# 数值粗糙，够用即可——真正关心的类别请让历史数据说话。
LONG_TERM_FALLBACK_DAYS_PER_YEAR = {
    "EB4-China": 120, "EB4-India": 120, "EB4-ROW": 150,
    "EB4-R-China": 120, "EB4-R-ROW": 150,
    "EB2-China": 60, "EB3-China": 80,
    "EB2-India": 25, "EB3-India": 30,
    "_default": 200,
}


def _fallback_long_rate(category: str, country: str) -> float:
    """天/月。"""
    key = f"{category}-{country}"
    per_year = LONG_TERM_FALLBACK_DAYS_PER_YEAR.get(
        key, LONG_TERM_FALLBACK_DAYS_PER_YEAR["_default"]
    )
    return per_year / 12.0


# ---------------------------------------------------------------------------
# 从 bulletin 列表里抽出某类别 / 国家 / 图表的时间序列
# ---------------------------------------------------------------------------

def extract_series(bulletins, category: str, country: str, chart: str = "A") -> list[tuple]:
    """返回按月份升序的 [(date(年,月,1), cutoff), ...]。

    cutoff 三态：ISO 日期字符串 / "Current" / None（Unavailable 或缺数据）。
    """
    key = "chart_a" if str(chart).upper() == "A" else "chart_b"
    rows = []
    for b in bulletins:
        try:
            md = date(int(b["year"]), int(b["month"]), 1)
        except (KeyError, TypeError, ValueError):
            continue
        cutoff = None
        for e in b.get(key, []):
            if e.get("category") == category and e.get("country") == country:
                cutoff = e.get("cutoff_date")
                break
        rows.append((md, cutoff))
    rows.sort(key=lambda r: r[0])
    return rows


def _numeric_points(series) -> list[tuple]:
    """只保留 cutoff 是真实日期的点，转成 (月份 date, cutoff date)。"""
    out = []
    for md, c in series:
        if isinstance(c, str) and c != "Current":
            try:
                out.append((md, date.fromisoformat(c)))
            except ValueError:
                continue
    return out


def observed_pace(series, window: int | None = None) -> float | None:
    """最近 window 个月步长内的实测推进速度（天/月）。

    用「净推进天数 / 跨越的日历月数」，跨过 Current / 空缺的月份也算在分母里
    （这些月份没前进，本就该拉低速度）。window=None 表示用全部历史。
    """
    pts = _numeric_points(series)
    if len(pts) < 2:
        return None
    if window is not None:
        pts = pts[-(window + 1):]
        if len(pts) < 2:
            return None
    (m0, c0), (m1, c1) = pts[0], pts[-1]
    span_months = (m1.year - m0.year) * 12 + (m1.month - m0.month)
    if span_months <= 0:
        return None
    return (c1 - c0).days / span_months


def latest_move_days(series) -> int | None:
    """最近一次可比的月环比移动（天，带符号）。"""
    pts = _numeric_points(series)
    if len(pts) < 2:
        return None
    return (pts[-1][1] - pts[-2][1]).days


# ---------------------------------------------------------------------------
# 衰减外推模型
# ---------------------------------------------------------------------------

def pace_at_month(y: float, near: float, recent: float, mid: float, long_: float) -> float:
    """预测未来第 y 个月的推进速度（天/月）。所有入参都是天/月。

    y ≤ 12   : 主要看近期实测（0.55 near + 0.20 recent + 0.25 long）
    12–36    : 线性过渡到中期均值 mid
    36–120   : 从 mid 线性过渡到长期锚点 (0.6 long + 0.4 mid)
    > 120    : 完全用长期锚点
    """
    base = 0.55 * near + 0.20 * recent + 0.25 * long_
    if y <= 12:
        return base
    if y <= 36:
        f = (y - 12) / 24.0
        return (1 - f) * base + f * mid
    if y <= 120:
        f = (y - 36) / 84.0
        anchor = 0.6 * long_ + 0.4 * mid
        return (1 - f) * mid + f * anchor
    return 0.6 * long_ + 0.4 * mid


def cumulative_advance(months: float, near: float, recent: float, mid: float, long_: float) -> float:
    """未来 months 个月内累计推进的天数。"""
    if months <= 0:
        return 0.0
    total = 0.0
    full = int(months)
    for y in range(1, full + 1):
        total += pace_at_month(y, near, recent, mid, long_)
    frac = months - full
    if frac > 0:
        total += pace_at_month(full + 1, near, recent, mid, long_) * frac
    return total


def months_to_current(gap_days: float, near: float, recent: float, mid: float,
                      long_: float, cap: int = 720) -> float | None:
    """二分搜索：累计推进 ≥ gap_days 所需的最少月数。排不到（cap 内）返回 None。"""
    if gap_days <= 0:
        return 0.0
    if cumulative_advance(cap, near, recent, mid, long_) < gap_days:
        return None
    lo, hi = 0.0, float(cap)
    for _ in range(40):
        m = (lo + hi) / 2
        if cumulative_advance(m, near, recent, mid, long_) < gap_days:
            lo = m
        else:
            hi = m
        if hi - lo < 0.05:
            break
    return round((lo + hi) / 2, 1)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def _months_until_fy_end(today: date) -> float:
    """距下一个 9/30 财年末的月数。财年末排期最容易退表。"""
    sep30 = date(today.year, 9, 30)
    if today > sep30:
        sep30 = date(today.year + 1, 9, 30)
    return (sep30 - today).days / 30.44


def forecast(priority_date: str, category: str, country: str, bulletins,
             chart: str = "A", today: date | None = None) -> dict:
    """预测某个 case 在指定图表（A=获批 / B=递交）下的排期。

    返回 dict（不可用 / 已 current / 已可递交 时部分字段为 None）：
        as_of                  最新一期月份 "YYYY-MM"
        chart                  "A" / "B"
        current_cutoff         最新一期该格子的值
        eligible               优先日是否已被覆盖（cutoff ≥ 优先日，含 Current）
        is_current             该格子是否为 Current
        unavailable            该格子是否为 Unavailable
        distance_days          排期还需前进多少天才追上你的优先日（>0 表示还在等）
        this_month_days        最近一次月环比移动（天，带符号）
        avg_pace_days_per_month  当前采用的近期节奏
        months_expected        预期还需月数（None = cap 内排不到）
        months_optimistic      乐观情景（近期节奏 ×1.5）
        months_conservative    保守情景（近期节奏 ×0.35）
        prob_current_next      下期就轮到的粗略概率
        prob_advance           下期继续前进的粗略概率
        prob_retrogress        下期退表的粗略概率
        confidence             "low" / "medium" / "high"
    """
    today = today or date.today()
    series = extract_series(bulletins, category, country, chart)

    result = {
        "as_of": series[-1][0].strftime("%Y-%m") if series else None,
        "chart": str(chart).upper(),
        "current_cutoff": None,
        "eligible": False,
        "is_current": False,
        "unavailable": False,
        "distance_days": None,
        "this_month_days": latest_move_days(series),
        "avg_pace_days_per_month": None,
        "months_expected": None,
        "months_optimistic": None,
        "months_conservative": None,
        "prob_current_next": None,
        "prob_advance": None,
        "prob_retrogress": None,
        "confidence": "low",
    }

    # 最新一期的 cutoff（跳过末尾缺数据的月份）
    current = None
    for _, c in reversed(series):
        if c is not None:
            current = c
            break
    result["current_cutoff"] = current

    if current == "Current":
        result.update(eligible=True, is_current=True, confidence="high",
                      months_expected=0.0, months_optimistic=0.0, months_conservative=0.0)
        return result

    if current is None:
        result["unavailable"] = True
        return result

    try:
        pd = date.fromisoformat(priority_date)
        cut = date.fromisoformat(current)
    except (TypeError, ValueError):
        return result

    # 排期还需前进多少天才追上优先日。<=0 表示 cutoff 已越过优先日 → 已可递交/获批。
    distance_days = (pd - cut).days
    result["distance_days"] = distance_days
    move = result["this_month_days"]

    if distance_days <= 0:
        result.update(eligible=True, confidence="high",
                      months_expected=0.0, months_optimistic=0.0, months_conservative=0.0)
        return result

    # 四档节奏（天/月）。注意用「is None」判断而不是布尔真假——
    # 实测速度可能正好是 0（近几期持平），那是有效信号，不该被当成缺数据跳过。
    near = observed_pace(series, 3)
    if near is None:
        near = observed_pace(series, 6)
    recent = observed_pace(series, 12)
    mid = observed_pace(series, 24)
    long_ = observed_pace(series, None)

    if long_ is None:
        long_ = _fallback_long_rate(category, country)
    if recent is None:
        recent = long_
    if mid is None:
        mid = recent

    # 近期停滞或后退（3–6 个月净推进 ≤ 0，或没有短窗数据）时，用「12 个月均速 → 全程均速
    # → 兜底表」的顺序取一个正的外推基准：一个平月/坏月不代表永久停滞。
    # 这种情况把置信度压到 low，退表 / 停滞的风险另有 this_month_days / prob_* 反映。
    near_stalled = near is None or near <= 0
    if near_stalled:
        if recent > 0:
            near = recent
        elif long_ > 0:
            near = long_
        else:
            near = _fallback_long_rate(category, country)

    result["avg_pace_days_per_month"] = round(near, 1)
    # 前端走势图用这几个值把 cutoff 线往未来外推（见 index.html renderTrend）
    result["paces"] = {"near": near, "recent": recent, "mid": mid, "long_": long_}

    def scenario(mult):
        return months_to_current(
            distance_days, max(near * mult, 0.0), max(recent, 0.0),
            max(mid, 0.0), max(long_, 0.0),
        )

    result["months_expected"] = scenario(1.0)
    result["months_optimistic"] = scenario(1.5)
    result["months_conservative"] = scenario(0.35)

    # 概率（粗略启发式）
    exp_1mo = pace_at_month(1, max(near, 0.0), max(recent, 0.0), max(mid, 0.0), max(long_, 0.0))
    if exp_1mo <= 0:
        p_next = 0.02
    elif exp_1mo >= distance_days:
        p_next = 0.75
    elif distance_days < 1.5 * exp_1mo:
        p_next = 0.40
    elif distance_days < 3 * exp_1mo:
        p_next = 0.10
    else:
        p_next = 0.02
    result["prob_current_next"] = p_next

    if move is None:
        result["prob_advance"] = 0.60
    elif move > 0:
        result["prob_advance"] = 0.72
    elif move < 0:
        result["prob_advance"] = 0.35
    else:
        result["prob_advance"] = 0.45

    p_retro = 0.10
    if _months_until_fy_end(today) < 3:
        p_retro = max(p_retro, 0.25)
    if move is not None and move < 0:
        p_retro = max(p_retro, 0.40)
    result["prob_retrogress"] = p_retro

    conf = "medium"
    if long_ * 12 < 30:
        conf = "low"
    me = result["months_expected"]
    if me is None or me > 120:
        conf = "low"
    if near_stalled:
        conf = "low"
    if near >= 60 and move is not None and move > 0 and not near_stalled:
        conf = "high"
    result["confidence"] = conf

    return result
