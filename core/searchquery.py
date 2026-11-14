"""把结构化筛选条件拼成 DeepSeek 搜索语法。

严格对齐官方规则（https://api-docs.deepseek.com/zh-cn/guides/search）：
    site:a OR site:b / -site:a / -词 / -"短语" / "短语" / lang:zh,en / after:2025[-01-01] / before:...
所有片段用空格連接；拼接后仍受 query 128 字符上限约束。
"""

import re
from urllib.parse import urlparse

from .errors import DeepSeekAPIError

MAX_QUERY_LEN = 128
_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_QUOTE_PAIRS = (('"', '"'), ("“", "”"), ("'", "'"))


def _strip_quotes(text):
    value = (text or "").strip()
    for left, right in _QUOTE_PAIRS:
        if len(value) >= 2 and value.startswith(left) and value.endswith(right):
            return value[1:-1].strip()
    return value


def _split_terms(raw, split_spaces=True):
    pattern = r"[,，;；\s]+" if split_spaces else r"[,，;；]+"
    terms = []
    for chunk in re.split(pattern, raw or ""):
        term = _strip_quotes(chunk)
        if term and term not in terms:
            terms.append(term)
    return terms


def _split_phrases(raw):
    terms = []
    for chunk in re.split(r"[,，;；]+", raw or ""):
        term = _strip_quotes(chunk)
        if term and term not in terms:
            terms.append(term)
    return terms


def _exclude_terms(raw):
    """排除词：逗号分隔；同时兼容用户直接粘贴 -a -b 的写法。"""
    text = (raw or "").replace("，", ",").replace("；", ",").replace(";", ",")
    terms = []
    for chunk in text.split(","):
        for piece in re.split(r"\s+(?=-)", chunk.strip()):
            value = _strip_quotes(piece)
            while value.startswith("-"):
                value = value[1:].strip()
            if value and value not in terms:
                terms.append(value)
    return terms


def _strip_prefixes(value, prefixes):
    text = (value or "").strip()
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _site_token(term):
    """域名归一：允许直接粘贴 URL、允许已经写了 site: 前缀。"""
    text = _strip_prefixes(term, ("-site:", "site:"))
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.netloc or parsed.path
    text = text.strip().strip("/")
    if text.lower().startswith("www."):
        text = text[4:]
    return text.replace(" ", "")


def _language_terms(raw):
    parts = [_strip_quotes(p).strip().lower() for p in re.split(r"[,，]", raw or "")]
    return ",".join([p for p in parts if p])


def _date_token(value, name):
    text = _strip_quotes(value)
    if not text:
        return ""
    if not _DATE_RE.match(text):
        raise DeepSeekAPIError(
            "%s 的日期格式不对：%s（支持 2025 或 2025-01-01）" % (name, text)
        )
    return text


def build_query(
    query="",
    site_include="",
    site_exclude="",
    exclude_words="",
    exact_phrase=False,
    exact_phrases="",
    lang="",
    after="",
    before="",
):
    """把 base query + 筛选条件拼成一条符合官方语法的搜索词。"""
    parts = []

    base = _strip_quotes(query)
    if base:
        parts.append('"%s"' % base if exact_phrase else base)

    for phrase in _split_phrases(exact_phrases):
        parts.append('"%s"' % phrase)

    includes = []
    for term in _split_terms(site_include):
        if term.strip().lower() in ("or", "and"):
            continue
        token = _site_token(term)
        if token and token not in includes:
            includes.append(token)
    if includes:
        parts.append(" OR ".join("site:%s" % token for token in includes))

    for term in _split_terms(site_exclude):
        token = _site_token(term)
        if token:
            parts.append("-site:%s" % token)

    for term in _exclude_terms(exclude_words):
        parts.append('-%s' % ('"%s"' % term if " " in term else term))

    langs = _language_terms(lang)
    if langs:
        parts.append("lang:%s" % langs)

    after_date = _date_token(after, "after")
    if after_date:
        parts.append("after:%s" % after_date)

    before_date = _date_token(before, "before")
    if before_date:
        parts.append("before:%s" % before_date)

    text = " ".join(parts).strip()
    if not text:
        raise DeepSeekAPIError("搜索词为空：请填写 query，或至少设置一个筛选条件")
    if len(text) > MAX_QUERY_LEN:
        raise DeepSeekAPIError(
            "拼接后的搜索词 %d 字符，超过上限 %d：请精简搜索词或筛选条件"
            % (len(text), MAX_QUERY_LEN)
        )
    return text

