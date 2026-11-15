"""DeepSeek 搜索 API 节点（V3 schema）。

聚焦 POST /v1/tools/search：结构化筛选条件 → 自动拼成搜索语法 → 结构化结果。
"""

import json
import logging

from comfy_api.latest import io

from .core.client import DeepSeekClient
from .core.config import (
    DEFAULT_API_KEY_PLACEHOLDER,
    DEFAULT_BASE_URL,
    normalize_base_url,
    resolve_api_key,
)
from .core.errors import DeepSeekAPIError
from .core.searchquery import build_query
from .core.websearch import format_search_results, format_search_usage

LOG = logging.getLogger("DeepSeekAPI")

NODE_ID = "DeepSeekAPI_Search"
MAX_QUESTION_LEN = 128


class DeepSeekSearchNode(io.ComfyNode):
    """调用 DeepSeek 网页搜索接口的节点。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="DeepSeek 搜索 API",
            category="DeepSeek",
            description=(
                "调用 DeepSeek 网页搜索接口（POST /v1/tools/search）。"
                "搜索语法不用手写：站点/排除/语言/日期都是独立控件，节点自动拼成 site:、-site:、lang:、after: 等。"
                "按次计费（约 ¥0.005/次），与返回条数无关。\nSearch the web via POST /v1/tools/search. No syntax to write by hand: site / exclude / language / date are separate widgets and the node builds the query. Billed per call (about 0.005 CNY), independent of result count."
            ),
            search_aliases=[
                "deepseek",
                "search",
                "web",
                "搜索",
                "联网",
                "检索",
                "网页",
            ],
            inputs=[
                io.String.Input(
                    "ori_question",
                    default="DeepSeek 最新模型是什么？有哪些新特性？",
                    tooltip="触发这次搜索的原始问题（1-128 字符），帮助搜索理解意图；默认给了一个示例\nThe original question behind this search (1-128 chars); helps the engine understand intent. The default is just an example",
                ),
                io.String.Input(
                    "query",
                    default="DeepSeek V4 模型 发布",
                    placeholder="输入关键词即可，不用写 site:/lang: 这类语法",
                    tooltip="搜索词（1-128 字符）。语法请用下面的筛选控件，节点会自动拼接\nQuery keywords (1-128 chars). Use the filter fields below instead of writing syntax by hand",
                ),
                io.String.Input(
                    "site_include",
                    default="",
                    placeholder="如 github.com, huggingface.co（多个用逗号或空格分隔）",
                    tooltip="只在指定站点搜索，等价于 site:a OR site:b；直接粘网址也行，会自动取域名\nOnly search these sites, same as site:a OR site:b. A full URL is accepted and reduced to the domain",
                ),
                io.String.Input(
                    "site_exclude",
                    default="",
                    placeholder="如 example.com, pinterest.com",
                    tooltip="排除指定站点，等价于 -site:a -site:b\nExclude these sites, same as -site:a -site:b",
                ),
                io.String.Input(
                    "exclude_words",
                    default="",
                    placeholder="如 广告, 搬运, release notes",
                    tooltip="排除包含这些词/短语的网页，等价于 -词；用逗号分隔，带空格的短语会自动加引号\nExclude pages containing these words/phrases, same as -word. Comma separated; phrases with spaces are quoted",
                ),
                io.Boolean.Input(
                    "exact_phrase",
                    default=False,
                    tooltip="精确匹配整句：把 query 用双引号包起来（适合找原文/报错信息）\nMatch the whole query as an exact phrase (good for error messages or quoted text)",
                ),
                io.String.Input(
                    "exact_phrases",
                    default="",
                    placeholder="额外精确短语，逗号分隔，如 官方文档, release notes",
                    tooltip="精确匹配这些短语，可多个，等价于 \"短语1\" \"短语2\"（短语内可含空格）\n (match these exact phrases; comma separated; spaces allowed inside a phrase)",
                ),
                io.String.Input(
                    "lang",
                    default="",
                    placeholder="如 zh 或 zh,en",
                    tooltip="限定语言，等价于 lang:zh,en；留空表示不限\nRestrict language, same as lang:zh,en. Leave empty for any language",
                ),
                io.String.Input(
                    "after",
                    default="",
                    placeholder="如 2025 或 2025-01-01",
                    tooltip="只保留该日期之后发布的网页，等价于 after:2025-01-01\nKeep pages published after this date, same as after:2025-01-01",
                ),
                io.String.Input(
                    "before",
                    default="",
                    placeholder="如 2026-06-01",
                    tooltip="只保留该日期之前发布的网页，等价于 before:2026-06-01\nKeep pages published before this date, same as before:2026-06-01",
                ),
                io.String.Input(
                    "api_key",
                    default=DEFAULT_API_KEY_PLACEHOLDER,
                    tooltip=(
                        "填 sk-... 直接使用；或填 ${环境变量名} 从环境变量读取（默认 ${DEEPSEEK_API_KEY}）。"
                        "注意：该值会随工作流保存，分享工作流前请先清空。\nPaste sk-... directly, or env placeholder to read an environment variable. This value is saved in the workflow, so clear it before sharing."
                    ),
                ),
                io.String.Input(
                    "base_url",
                    default=DEFAULT_BASE_URL,
                    tooltip="API 地址，默认 https://api.deepseek.com（也可填 https://api.deepseek.com/v1）\nBase URL, default https://api.deepseek.com (a /v1 suffix also works)",
                ),
                io.Int.Input(
                    "count",
                    default=5,
                    min=1,
                    max=50,
                    step=1,
                    tooltip="返回条数（1-50）。按次计费、与条数无关，默认 5 条足够给模型读\nNumber of results (1-50). Billed per call, count does not change the price; 5 is enough for an LLM",
                ),
                io.Boolean.Input(
                    "need_content",
                    default=False,
                    tooltip="是否返回网页正文，默认关（正文体积大，接模型时注意 token 成本）\nReturn page content as well; off by default because it is large and costs tokens downstream",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="text",
                    tooltip="结构化 Markdown 摘要：标题 / 统计 / 每条 链接·来源·摘要\nStructured Markdown summary: header, stats, then link/source/summary per result",
                ),
                io.String.Output(display_name="json", tooltip="原始 JSON（含 results 数组）\nRaw JSON containing the results array"),
                io.String.Output(
                    display_name="usage",
                    tooltip="实际发出的搜索词、结果条数与估算费用\nThe actual query sent, result count and estimated cost",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        query,
        api_key,
        base_url,
        site_include="",
        site_exclude="",
        exclude_words="",
        exact_phrase=False,
        exact_phrases="",
        lang="",
        after="",
        before="",
        count=5,
        need_content=False,
        ori_question="",
    ):
        question = (ori_question or "").strip() or None
        if question and len(question) > MAX_QUESTION_LEN:
            raise DeepSeekAPIError(
                "ori_question 过长（%d 字符），上限 %d 字符"
                % (len(question), MAX_QUESTION_LEN)
            )

        query_text = build_query(
            query=query,
            site_include=site_include,
            site_exclude=site_exclude,
            exclude_words=exclude_words,
            exact_phrase=bool(exact_phrase),
            exact_phrases=exact_phrases,
            lang=lang,
            after=after,
            before=before,
        )

        key = resolve_api_key(api_key)
        endpoint = normalize_base_url(base_url)

        client = DeepSeekClient(key, endpoint)
        data = client.search(
            query_text,
            count=count,
            need_content=bool(need_content),
            ori_question=question,
        )

        results = data.get("results") or []
        digest = format_search_results(
            results, query=query_text, include_content=bool(need_content)
        )
        summary = format_search_usage(
            query_text, results, need_content=bool(need_content)
        )
        raw = json.dumps(data, ensure_ascii=False)

        LOG.info("DeepSeek 搜索完成：%s", summary)

        try:
            return io.NodeOutput(digest, raw, summary, ui={"text": [summary]})
        except TypeError:
            LOG.warning("当前 ComfyUI 的 io.NodeOutput 不支持 ui 参数，已跳过节点上的用量显示")
            return io.NodeOutput(digest, raw, summary)

