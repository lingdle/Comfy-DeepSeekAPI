"""价格表、峰谷判断与费用估算（单位：元 / 百万 token，2026-11 官方价）。"""

from datetime import datetime, timedelta, timezone

try:  # Python 3.9+；Windows 上可能缺 tzdata，退化为固定 UTC+8
    from zoneinfo import ZoneInfo

    BEIJING = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    BEIJING = timezone(timedelta(hours=8))

# 每项 = (空闲时段单价, 高峰时段单价)
PRICES = {
    "deepseek-flash": {"hit": (0.02, 0.04), "miss": (1.0, 2.0), "out": (4.0, 8.0)},
    "deepseek-v4-pro": {"hit": (0.15, 0.30), "miss": (4.5, 9.0), "out": (13.5, 27.0)},
}

PEAK_HINT = "高峰时段为北京时间工作日 9:00-12:00、14:00-18:00（法定节假日除外）"


def is_peak(now=None):
    """是否处于高峰计费时段（不判断法定节假日，只会多算不会少算）。"""
    if now is None:
        now = datetime.now(BEIJING)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    else:
        now = now.astimezone(BEIJING)

    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return (9 * 60 <= minutes < 12 * 60) or (14 * 60 <= minutes < 18 * 60)


def _usage_value(usage, key, default=0):
    value = usage.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def estimate_cost(model, usage, peak=None):
    """按 usage 估算费用（元）。模型不在价格表里返回 None。"""
    price = PRICES.get((model or "").strip().lower())
    if price is None:
        return None
    if peak is None:
        peak = is_peak()
    index = 1 if peak else 0

    hit = _usage_value(usage, "prompt_cache_hit_tokens")
    miss = _usage_value(usage, "prompt_cache_miss_tokens")
    if not hit and not miss:
        details = usage.get("prompt_tokens_details") or {}
        hit = _usage_value(details, "cached_tokens")
        miss = max(_usage_value(usage, "prompt_tokens") - hit, 0)
    out = _usage_value(usage, "completion_tokens")

    return (hit * price["hit"][index] + miss * price["miss"][index] + out * price["out"][index]) / 1000000.0


def format_usage(model, usage, cost, finish_reason="", n_images=0, peak=None, extra_parts=None):
    """给节点 ui 用的一行摘要。"""
    parts = ["模型 %s" % model]

    prompt_tokens = _usage_value(usage, "prompt_tokens")
    hit = _usage_value(usage, "prompt_cache_hit_tokens")
    completion = _usage_value(usage, "completion_tokens")
    reasoning_tokens = _usage_value(usage.get("completion_tokens_details") or {}, "reasoning_tokens")

    if prompt_tokens:
        text = "输入 %d" % prompt_tokens
        if hit:
            text += "（缓存命中 %d）" % hit
        parts.append(text)
    if completion:
        text = "输出 %d" % completion
        if reasoning_tokens:
            text += "（思考 %d）" % reasoning_tokens
        parts.append(text)
    if n_images:
        parts.append("图片 %d 张" % n_images)
    if extra_parts:
        parts.extend(extra_parts)

    if cost is None:
        parts.append("费用未知（模型不在价格表）")
    else:
        if peak is None:
            peak = is_peak()
        parts.append("估算 ¥%.4f（%s价）" % (cost, "高峰" if peak else "空闲"))

    if finish_reason and finish_reason != "stop":
        hint = {
            "length": "输出达到 max_tokens 被截断，可调大",
            "content_filter": "内容被安全策略过滤",
            "insufficient_system_resource": "服务端资源不足，生成中断",
            "tool_calls": "模型发起了工具调用",
            "aborted": "生成被中断",
        }.get(finish_reason, finish_reason)
        parts.append("⚠ %s" % hint)

    return " · ".join(parts)



# --- 其它计费项（元 / 次，2026-11 官方价）---------------------------------
SEARCH_PRICE_PER_CALL = 5.0 / 1000.0  # 搜索：5 元 / 1000 次
FETCH_PRICE_PER_CALL = 5.0 / 1000.0   # 网页抓取：5 元 / 1000 次

