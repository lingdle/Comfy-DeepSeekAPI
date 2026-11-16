"""DeepSeek 模型 API 节点（V3 schema）。

一个节点覆盖：文本对话、图像识别（最多 5 张）、思考模式开关、成本估算。
默认值：思考关闭（最省钱）；max_tokens 取接口上限 384K（输出长描述不被截断）；
图片不主动缩放，只有长边超过 4096 才缩（服务端本来就会把大图缩到约 1300×1300）。
"""

import json
import logging
import re

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

# 接口规格（platform.deepseek.com）：上下文 1M，max_tokens 1~384K，单次最多 600 张图
MAX_OUTPUT_TOKENS = 393216
MAX_IMAGES_PER_REQUEST = 600
SEND_IMAGES_BY_DEFAULT = 5  # 费用护栏：默认只发 5 张，不是接口限制
MAX_IMAGE_SIDE = 4096  # 内部兜底：只有超过才缩，避免请求体过大


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


_SLOT_INDEX = re.compile(r"(\d+)$")


def _slot_sort_key(name):
    """autogrow 插槽名 image_0、image_10 按数字顺序排，未知名字排最后。"""
    match = _SLOT_INDEX.search(str(name))
    return (0, int(match.group(1)), str(name)) if match else (1, 0, str(name))


def _merge_image_inputs(image_slots, images):
    """合并两路图片输入：autogrow 插槽在前，images（单张或 batch）在后。"""
    merged = []
    if isinstance(image_slots, dict):
        for name in sorted(image_slots, key=_slot_sort_key):
            tensor = image_slots.get(name)
            if tensor is not None:
                merged.append(tensor)
    if images is not None:
        merged.append(images)
    return merged


DEFAULT_VISION_PROMPT = "请详细描述这些图片的内容；如果图中有文字，请一并转写出来。"
NODE_ID = "DeepSeekAPI_Model"


class DeepSeekModelNode(io.ComfyNode):
    """调用 DeepSeek 云端模型（默认 deepseek-flash）的通用节点。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="DeepSeek 模型 API",
            category="DeepSeekAPI",
            description=(
                "调用 DeepSeek 云端模型（默认 deepseek-flash）。"
                "支持纯文本对话，也支持图片识别（image_slots 可动态加插槽，images 可接单张或 batch，"
                "两路合并后最多 max_images 张，插槽里的图排在前面）。"
                "默认关闭思考（thinking=close），省钱且快；需要更强推理时把 thinking 改成 low / high / max。"
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
                    "user_prompt",
                    default="图片上是什么？",
                    multiline=True,
                    placeholder="如：图片上是什么？ / e.g. What is in this image?",
                    tooltip="用户提示词；清空且不接图片会报错",
                ),
                io.String.Input(
                    "system_prompt",
                    default="你是一个图像理解助手",
                    multiline=True,
                    placeholder="如：你是一个图像理解助手 / e.g. You are an image understanding assistant",
                    tooltip="系统提示词，决定模型的角色与规则；默认按图像理解场景写好",
                ),
                io.String.Input(
                    "model",
                    default=DEFAULT_MODEL,
                    tooltip="模型名称，例如 deepseek-flash（支持图片）或 deepseek-v4-pro（仅文本）",
                ),
                io.Combo.Input(
                    "thinking",
                    options=["close", "low", "high", "max"],
                    default="close",
                    tooltip="思考模式：close 关闭（最快最省）；low / high / max 开启思考，档位越高越慢越贵",
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
                io.Autogrow.Input(
                    "image_slots",
                    display_name="多图插槽",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("image"),
                        prefix="image_",
                        min=0,
                        max=10,
                    ),
                    optional=True,
                    tooltip=(
                        "可选：点 + 动态添加图片插槽，每个插槽接一张或一整个 batch。"
                        "插槽里的图排在 images 前面，合并后最多发送 max_images 张"
                    ),
                ),
                io.Image.Input(
                    "images",
                    display_name="images",
                    optional=True,
                    tooltip="可选：一张或多张图片（IMAGE）。接 batch 时按顺序展开，超过 max_images 的部分丢弃",
                    advanced=True,
                ),
                io.Float.Input(
                    "temperature",
                    default=1.0,
                    min=0.0,
                    max=2.0,
                    step=0.1,
                    tooltip="仅在 thinking=close 时生效；提示词扩写建议 1.0-1.3",
                    advanced=True,
                ),
                io.Int.Input(
                    "max_tokens",
                    default=MAX_OUTPUT_TOKENS,
                    min=16,
                    max=MAX_OUTPUT_TOKENS,
                    step=1024,
                    tooltip=(
                        "单次输出上限，默认取接口上限 384K（1~393216）；"
                        "只有生成到上限才会多花钱，调小反而可能把长描述截断"
                    ),
                    advanced=True,
                ),
                io.Combo.Input(
                    "image_detail",
                    options=["low", "high", "original", "auto"],
                    default="low",
                    tooltip="图片精度：low 会把图缩到 512x512，最省 token",
                    advanced=True,
                ),
                io.Int.Input(
                    "max_images",
                    default=SEND_IMAGES_BY_DEFAULT,
                    min=1,
                    max=MAX_IMAGES_PER_REQUEST,
                    step=1,
                    tooltip=(
                        "本次实际发送几张图（images 是 batch 时按顺序取前 N 张）。"
                        "接口最多 600 张，这里默认 5 张只是控制费用与耗时"
                    ),
                    advanced=True,
                ),
            ],
            outputs=[
                io.String.Output(display_name="text", tooltip="模型的最终回答"),
                io.String.Output(display_name="reasoning", tooltip="思考模式的思维链（thinking=close 时为空）"),
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
        images=None,
        image_slots=None,
        user_prompt="",
        system_prompt="",
        model=DEFAULT_MODEL,
        api_key=DEFAULT_API_KEY_PLACEHOLDER,
        base_url=DEFAULT_BASE_URL,
        thinking="close",
        web_search=False,
        read_url=False,
        temperature=1.0,
        max_tokens=MAX_OUTPUT_TOKENS,
        image_detail="low",
        max_images=SEND_IMAGES_BY_DEFAULT,
    ) -> io.NodeOutput:
        model_name = (model or "").strip() or DEFAULT_MODEL
        key = resolve_api_key(api_key)
        endpoint = normalize_base_url(base_url)

        system_text = (system_prompt or "").strip()
        user_text = (user_prompt or "").strip()

        limit = max(1, int(max_images))
        data_urls = []
        for tensor in _merge_image_inputs(image_slots, images):
            if len(data_urls) >= limit:
                break
            data_urls.extend(
                tensor_to_data_urls(
                    tensor, max_images=limit - len(data_urls), max_side=MAX_IMAGE_SIDE
                )
            )
        data_urls = data_urls[:limit]

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

        level = str(thinking or "close").strip().lower()
        if level not in ("close", "low", "high", "max"):
            level = "close"
        thinking_on = level != "close"
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "stream": False,
            "thinking": {"type": "enabled" if thinking_on else "disabled"},
        }
        if thinking_on:
            payload["reasoning_effort"] = level
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

