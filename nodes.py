"""DeepSeek 模型 API 节点（V3 schema）。

一个节点覆盖：文本对话、图像识别（最多 5 张）、思考模式开关、成本估算。
默认值全部按"最省钱、最快"设置：思考关闭、max_tokens 1024、图片低精度缩到 1024。
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
from .core.imaging import tensor_to_data_urls
from .core.pricing import SEARCH_PRICE_PER_CALL, estimate_cost, format_usage

LOG = logging.getLogger("DeepSeekAPI")

DEFAULT_MODEL = "deepseek-flash"


def _collect_sources(annotations, steps, limit=10):
    """从 annotations + server_tool_calls 里收集来源链接，按 URL 去重。"""
    seen = {}

    for item in annotations or []:
        if (item or {}).get("type") != "url_citation":
            continue
        citation = item.get("url_citation") or {}
        url = (citation.get("url") or "").strip()
        if url:
            seen.setdefault(url, (citation.get("title") or "").strip() or url)

    for step in steps or []:
        for call in (step or {}).get("calls") or []:
            page = (call or {}).get("page") or {}
            url = (page.get("url") or "").strip()
            if url:
                seen.setdefault(url, (page.get("title") or "").strip() or url)
            for source in (call or {}).get("sources") or []:
                url = (source.get("url") or "").strip()
                if url:
                    seen.setdefault(url, (source.get("title") or "").strip() or url)

    lines = ["- %s — %s" % (title, url) for url, title in list(seen.items())[:limit]]
    return "\n".join(lines)


DEFAULT_VISION_PROMPT = "请详细描述这些图片的内容；如果图中有文字，请一并转写出来。"
NODE_ID = "DeepSeekAPI_Model"


class DeepSeekModelNode(io.ComfyNode):
    """调用 DeepSeek 云端模型（默认 deepseek-flash）的通用节点。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="DeepSeek 模型 API",
            category="DeepSeek",
            description=(
                "调用 DeepSeek 云端模型（默认 deepseek-flash）。"
                "支持纯文本对话，也支持图片识别（images 可接一张或多张，最多 max_images 张）。"
                "默认关闭思考模式，省钱且快；需要更强的推理时把 thinking 改成 enabled。"
            ),
            search_aliases=[
                "deepseek",
                "deepseek-flash",
                "llm",
                "vlm",
                "chat",
                "api",
                "大模型",
                "模型API",
                "视觉",
                "图像理解",
            ],
            inputs=[
                io.String.Input(
                    "model",
                    default=DEFAULT_MODEL,
                    tooltip="模型名称，例如 deepseek-flash（支持图片）或 deepseek-v4-pro（仅文本）",
                ),
                io.String.Input(
                    "api_key",
                    default=DEFAULT_API_KEY_PLACEHOLDER,
                    tooltip=(
                        "填 sk-... 直接使用；或填 ${环境变量名} 从环境变量读取（默认 ${DEEPSEEK_API_KEY}）。"
                        "注意：该值会随工作流保存，分享工作流前请先清空。"
                    ),
                ),
                io.String.Input(
                    "base_url",
                    default=DEFAULT_BASE_URL,
                    tooltip="API 地址，默认 https://api.deepseek.com（也可填 https://api.deepseek.com/v1）",
                ),
                io.Image.Input(
                    "images",
                    display_name="images",
                    optional=True,
                    tooltip="可选：一张或多张图片（IMAGE）。接 batch 时按顺序展开，超过 max_images 的部分丢弃",
                ),
                io.String.Input(
                    "system_prompt",
                    default="你是一个图像理解助手",
                    multiline=True,
                    placeholder="如：你是一个图像理解助手 / e.g. You are an image understanding assistant",
                    tooltip="系统提示词，决定模型的角色与规则；默认按图像理解场景写好",
                ),
                io.String.Input(
                    "user_prompt",
                    default="图片上是什么？",
                    multiline=True,
                    placeholder="如：图片上是什么？ / e.g. What is in this image?",
                    tooltip="用户提示词；清空且不接图片会报错",
                ),
                io.Combo.Input(
                    "thinking",
                    options=["disabled", "enabled"],
                    default="disabled",
                    tooltip="思考模式：disabled 最快最省；enabled 质量更高但更慢更贵",
                ),
                io.Combo.Input(
                    "reasoning_effort",
                    options=["low", "high", "max"],
                    default="low",
                    tooltip="仅在 thinking=enabled 时生效；low 最省钱",
                ),
                io.Float.Input(
                    "temperature",
                    default=1.0,
                    min=0.0,
                    max=2.0,
                    step=0.1,
                    tooltip="仅在 thinking=disabled 时生效；提示词扩写建议 1.0-1.3",
                ),
                io.Int.Input(
                    "max_tokens",
                    default=1024,
                    min=16,
                    max=32768,
                    step=64,
                    tooltip="单次输出上限；越大越慢越贵。只有输出不足时才需要调大",
                ),
                io.Combo.Input(
                    "image_detail",
                    options=["low", "high", "original", "auto"],
                    default="low",
                    tooltip="图片精度：low 会把图缩到 512x512，最省 token",
                ),
                io.Int.Input(
                    "image_max_side",
                    default=1024,
                    min=256,
                    max=2048,
                    step=64,
                    tooltip="上传前把图片长边缩到该值；单图 token 上限为 1024，再大不加分",
                ),
                io.Int.Input(
                    "max_images",
                    default=5,
                    min=1,
                    max=10,
                    step=1,
                    tooltip="最多发送几张图（images 是 batch 时按顺序取前 N 张）",
                ),
                io.Boolean.Input(
                    "web_search",
                    default=False,
                    tooltip="联网工具：让模型自己搜索网页并附引用（deepseek_web_search）。按次计费，默认关闭",
                ),
                io.Boolean.Input(
                    "read_url",
                    default=False,
                    tooltip="联网工具：让模型阅读用户消息里的链接（deepseek_read_url）。按次计费，默认关闭",
                ),
            ],
            outputs=[
                io.String.Output(display_name="text", tooltip="模型的最终回答"),
                io.String.Output(display_name="reasoning", tooltip="思考模式的思维链（thinking=disabled 时为空）"),
                io.String.Output(display_name="usage", tooltip="token 用量与估算费用"),
                io.String.Output(
                    display_name="sources",
                    tooltip="联网搜索/阅读到的来源（每行「标题 — URL」；未开启联网时为空）",
                ),
                io.String.Output(
                    display_name="json",
                    tooltip='接口原始返回 JSON（choices/usage/annotations 等全部字段）',
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        model,
        api_key,
        base_url,
        system_prompt,
        user_prompt,
        images=None,
        thinking="disabled",
        reasoning_effort="low",
        temperature=1.0,
        max_tokens=1024,
        image_detail="low",
        image_max_side=1024,
        max_images=5,
        web_search=False,
        read_url=False,
    ) -> io.NodeOutput:
        model_name = (model or "").strip() or DEFAULT_MODEL
        key = resolve_api_key(api_key)
        endpoint = normalize_base_url(base_url)

        system_text = (system_prompt or "").strip()
        user_text = (user_prompt or "").strip()

        limit = max(1, int(max_images))
        data_urls = []
        if images is not None:
            data_urls = tensor_to_data_urls(
                images, max_images=limit, max_side=image_max_side
            )[:limit]

        if data_urls and model_name.lower() in ("deepseek-v4-pro", "deepseek-pro"):
            raise DeepSeekAPIError(
                "deepseek-v4-pro 不支持图片输入；请把 model 改成 deepseek-flash"
            )

        if not user_text and not data_urls:
            raise DeepSeekAPIError("user_prompt 为空且没有接入图片：请至少填一项")

        messages = []
        if system_text:
            messages.append({"role": "system", "content": system_text})

        if data_urls:
            blocks = [{"type": "text", "text": user_text or DEFAULT_VISION_PROMPT}]
            for url in data_urls:
                blocks.append(
                    {"type": "image_url", "image_url": {"url": url, "detail": image_detail}}
                )
            messages.append({"role": "user", "content": blocks})
        else:
            messages.append({"role": "user", "content": user_text})

        thinking_on = str(thinking).strip().lower() == "enabled"
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "stream": False,
            "thinking": {"type": "enabled" if thinking_on else "disabled"},
        }
        if thinking_on:
            payload["reasoning_effort"] = reasoning_effort or "low"
        else:
            payload["temperature"] = float(temperature)

        tools = []
        if web_search:
            tools.append({"type": "deepseek_web_search"})
        if read_url:
            tools.append({"type": "deepseek_read_url"})
        if tools:
            if not model_name.lower().startswith("deepseek-flash"):
                raise DeepSeekAPIError(
                    "联网工具目前仅支持 deepseek-flash；请把 model 改成 deepseek-flash"
                )
            payload["tools"] = tools

        LOG.info(
            "DeepSeek 请求：model=%s messages=%d images=%d thinking=%s max_tokens=%d",
            model_name,
            len(messages),
            len(data_urls),
            thinking_on,
            int(max_tokens),
        )

        client = DeepSeekClient(key, endpoint)
        data = client.chat(payload)

        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        text = message.get("content") or ""
        reasoning_text = message.get("reasoning_content") or ""
        finish_reason = choice.get("finish_reason") or ""
        usage = data.get("usage") or {}

        sources_text = _collect_sources(
            message.get("annotations"), message.get("server_tool_calls")
        )

        cost = estimate_cost(model_name, usage)
        tool_use = usage.get("server_tool_use") or {}
        searches = int(tool_use.get("tool_search") or 0)
        fetches = int(tool_use.get("tool_fetch") or 0)
        image_searches = int(tool_use.get("tool_image_search") or 0)
        tool_calls_total = searches + fetches + image_searches

        extra_parts = []
        if tool_calls_total:
            extra_parts.append(
                "联网 %d 次（搜索 %d / 抓取 %d / 图片 %d）"
                % (tool_calls_total, searches, fetches, image_searches)
            )
            if cost is not None:
                cost += tool_calls_total * SEARCH_PRICE_PER_CALL

        summary = format_usage(
            model_name,
            usage,
            cost,
            finish_reason=finish_reason,
            n_images=len(data_urls),
            extra_parts=extra_parts,
        )

        raw = json.dumps(data, ensure_ascii=False)

        LOG.info("DeepSeek 完成：%s", summary)

        # ui 文本只是"锦上添花"：个别 ComfyUI 版本若不支持 ui= 参数，也不影响五个输出
        try:
            return io.NodeOutput(
                text, reasoning_text, summary, sources_text, raw, ui={"text": [summary]}
            )
        except TypeError:
            LOG.warning("当前 ComfyUI 的 io.NodeOutput 不支持 ui 参数，已跳过节点上的用量显示")
            return io.NodeOutput(text, reasoning_text, summary, sources_text, raw)

