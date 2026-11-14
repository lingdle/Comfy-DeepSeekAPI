"""网页搜索结果 → 给模型读的 Markdown 摘要 + 用量文案。"""

from .pricing import SEARCH_PRICE_PER_CALL

GOOD_SCORE = 1.5
CONTENT_PREVIEW_CHARS = 800
MAX_RESULTS_IN_TEXT = 50


def _clean(text, limit=None):
    """把多行/多空格压成一行，避免破坏 markdown 结构。"""
    value = " ".join((text or "").split())
    if limit and len(value) > limit:
        value = value[:limit] + "…"
    return value


def _short_date(value):
    text = (value or "").strip()
    return text[:10] if text else ""


def format_search_results(results, query="", include_content=False, content_limit=CONTENT_PREVIEW_CHARS):
    """把 results 数组整理成结构化 Markdown（人可读，模型也好解析）。"""
    results = list(results or [])[:MAX_RESULTS_IN_TEXT]
    heading = "# 搜索：%s" % (_clean(query) or "（未提供查询词）")

    if not results:
        return (
            heading
            + "\n\n（没有搜索到结果）\n"
            + "\n建议：去掉 site: / after: / before: 等限定词，或换更宽泛的关键词再试。"
        )

    good = sum(1 for item in results if (item or {}).get("rerank_score", 0) >= GOOD_SCORE)
    lines = [heading, "", "共 %d 条结果 · 优质 %d 条" % (len(results), good)]

    for index, item in enumerate(results, start=1):
        item = item or {}
        title = _clean(item.get("title")) or "(无标题)"
        url = (item.get("url") or "").strip()

        lines.append("")
        lines.append("## %d. %s" % (index, title))
        if url:
            lines.append("- 链接：%s" % url)

        meta = []
        if item.get("site_name"):
            meta.append("站点 %s" % _clean(item["site_name"]))
        date = _short_date(item.get("date"))
        if date:
            meta.append("日期 %s" % date)
        authority = item.get("authority")
        if isinstance(authority, int) and authority >= 0:
            meta.append("权威 %d/4" % authority)
        score = item.get("rerank_score")
        if isinstance(score, (int, float)):
            meta.append("相关度 %.2f" % float(score))
        if meta:
            lines.append("- 来源：%s" % " ｜ ".join(meta))

        summary = _clean(item.get("summary") or item.get("snippet"))
        if summary:
            lines.append("- 摘要：%s" % summary)

        if include_content:
            content = (item.get("content") or "").strip()
            if content:
                preview = _clean(content, content_limit)
                lines.append("- 正文：%s（全文 %d 字）" % (preview, len(content)))

    return "\n".join(lines)


def format_search_usage(query, results, need_content=False, price=SEARCH_PRICE_PER_CALL):
    total = len(results or [])
    good = sum(1 for item in (results or []) if (item or {}).get("rerank_score", 0) >= GOOD_SCORE)

    parts = ["搜索「%s」" % _clean(query, 40)]
    if total:
        parts.append("返回 %d 条" % total)
        if good:
            parts.append("优质 %d 条" % good)
    else:
        parts.append("无结果")
    if need_content:
        parts.append("含正文")
    parts.append("估算 ¥%.4f/次" % price)
    return " · ".join(parts)

