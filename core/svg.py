"""从文本里取出 SVG，并落盘到 output 目录做节点预览。

模型输出常见形态，都要能吃：
1. svg 代码块（三反引号）
2. 无语言标记的代码块
3. 正文里直接夹一段 <svg>…</svg>
"""

import os
import re
import uuid

FENCE = "```"
_FENCE = re.compile(FENCE + r"[a-zA-Z0-9_+-]*\s*\n(.*?)" + FENCE, re.DOTALL)
_TAG = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
_NO_XMLNS = re.compile(r"<svg\b(?![^>]*\bxmlns\s*=)", re.IGNORECASE)

SVG_NAMESPACE = 'xmlns="http://www.w3.org/2000/svg"'


class SVGNotFound(ValueError):
    """文本里没有可用的 <svg> 片段。"""


def _first_tag(chunk):
    match = _TAG.search(chunk or "")
    return match.group(0) if match else None


def ensure_xmlns(markup):
    """缺 xmlns 的 <svg> 补上，浏览器/下游才能当图片渲染。"""
    if _NO_XMLNS.search(markup):
        return _NO_XMLNS.sub("<svg " + SVG_NAMESPACE, markup, count=1)
    return markup


def extract_svg(text):
    """返回第一个 SVG 片段（已补 xmlns）；找不到返回 None。

    优先看代码块，再看全文；多个 SVG 只取第一个。
    """
    if not text:
        return None
    for block in _FENCE.findall(text):
        found = _first_tag(block)
        if found:
            return ensure_xmlns(found.strip())
    found = _first_tag(text)
    return ensure_xmlns(found.strip()) if found else None


def save_preview(payload, prefix="text2svg"):
    """把 SVG 写进 ComfyUI 输出目录，返回 ui.images 用的条目。

    不在 ComfyUI 里（例如单元测试）时返回 None，由调用方退回文本预览。
    """
    try:
        import folder_paths
    except Exception:
        return None

    out_dir = folder_paths.get_output_directory()
    name = "%s_%s.svg" % (prefix, uuid.uuid4().hex[:8])
    with open(os.path.join(out_dir, name), "wb") as handle:
        handle.write(payload)
    return {"filename": name, "subfolder": "", "type": "output"}
