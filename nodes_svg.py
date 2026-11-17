"""Text2SVG 节点（V3 schema）。

把模型输出文本里的 SVG 提取出来，转成 ComfyUI 的 SVG 类型；
同时写一份到 output 目录，借 ui.images 在节点上直接预览。
"""

import logging
import os
from io import BytesIO

from comfy_api.latest import io

from .core.svg import FENCE, SVGNotFound, extract_svg, save_preview
from .core.friendly import guarded

LOG = logging.getLogger("DeepSeekAPI")

NODE_ID = "DeepSeekAPI_Text2SVG"

# 没提取到 SVG 时输出的占位（1×1，保证 SVG 类型契约成立，下游不会拿到 None）
EMPTY_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" '
    'viewBox="0 0 1 1" data-empty="true"></svg>'
)

PROMPT_HINT = (
    "例如：" + "请只输出一个 SVG，放在 " + FENCE + "svg 代码块里，不要输出别的解释"
)

PROMPT_FILE = os.path.join("example", "cases", "svg-generator-system-prompt.txt")


def recommended_system_prompt():
    """随包附带的 SVG 生成 agent 系统提示词；找不到就返回空串。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROMPT_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:  # pragma: no cover - 打包漏文件时不影响主功能
        LOG.warning("没找到内置 SVG 提示词：%s", path)
        return ""


def _svg_value(markup):
    """构造 SVG 类型的运行时值：SVG([BytesIO(...)])。"""
    payload = markup.encode("utf-8")
    svg_cls = getattr(io.SVG, "Type", None)
    if svg_cls is None:  # pragma: no cover - 极老版本没有 SVG 类型
        return payload
    return svg_cls([BytesIO(payload)])


class DeepSeekText2SVGNode(io.ComfyNode):
    """文本里的 SVG → ComfyUI SVG 类型 + 节点内预览。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="Text2SVG 文本转 SVG",
            category="DeepSeekAPI",
            description=(
                "把 DeepSeek 输出文本里的 SVG 提取出来，转成 ComfyUI 的 SVG 类型。"
                "支持 " + FENCE + "svg 代码块、无语言标记的代码块、正文里直接夹的 <svg>…</svg>；"
                "多个 SVG 只取第一个。没找到 SVG 也不报错：svg_text 为空，agent_prompt 照常输出。"
                "预览：找到时写一份到 output 目录并在节点上显示。"
            ),
            search_aliases=[
                "svg",
                "vector",
                "text2svg",
                "icon",
                "矢量",
                "图标",
                "转svg",
            ],
            inputs=[
                io.String.Input(
                    "text",
                    default="",
                    multiline=True,
                    placeholder="把 DeepSeek 节点的 text 接进来；或直接粘贴模型输出",
                    tooltip="模型输出原文；有没有代码块围栏、前后有没有解释都行",
                ),
                io.Boolean.Input(
                    "preview",
                    default=True,
                    tooltip="写一份 SVG 到 output 目录并在节点上预览；关掉则只输出类型、不落盘",
                    advanced=True,
                ),
            ],
            outputs=[
                io.SVG.Output(
                    display_name="svg",
                    tooltip="ComfyUI 的 SVG 类型（可接任何以 SVG 为输入的节点）",
                ),
                io.String.Output(
                    display_name="svg_text",
                    tooltip="提取出来的 SVG 源码，便于复制或排查",
                ),
                io.String.Output(
                    display_name="agent_prompt",
                    tooltip="随包附带的专家级 SVG 生成 agent 提示词，可直接接到模型节点的 system_prompt",
                ),
            ],
        )

    @classmethod
    @guarded
    def execute(cls, text="", preview=True) -> io.NodeOutput:
        prompt = recommended_system_prompt()
        markup = extract_svg(text)

        if not markup:
            # 没有 SVG 不算失败：正常把 agent 提示词送出去，方便直接接到模型节点
            LOG.info("Text2SVG：文本里没有 SVG，只输出 agent prompt")
            ui = {"text": [prompt]} if prompt else None
            empty = EMPTY_SVG
            try:
                return io.NodeOutput(_svg_value(empty), "", prompt, ui=ui)
            except TypeError:  # pragma: no cover
                return io.NodeOutput(_svg_value(empty), "", prompt)

        entry = None
        if preview:
            try:
                entry = save_preview(markup.encode("utf-8"))
            except Exception as exc:  # pragma: no cover - 写盘失败不影响输出
                LOG.warning("SVG 预览落盘失败，改为文本预览：%s", exc)

        ui = {"images": [entry]} if entry else {"text": [markup]}

        value = _svg_value(markup)
        LOG.info("Text2SVG：%d 字节，预览=%s", len(markup), bool(entry))

        try:
            return io.NodeOutput(value, markup, prompt, ui=ui)
        except TypeError:  # pragma: no cover - 老版本 io.NodeOutput 不支持 ui
            return io.NodeOutput(value, markup, prompt)
