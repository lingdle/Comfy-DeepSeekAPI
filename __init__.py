"""ComfyUI DeepSeek 节点集（V3 schema）。

安装：把整个目录放到 ComfyUI/custom_nodes/Comfy-DeepSeekAPI，重启 ComfyUI。
节点位于 Add Node -> DeepSeek：
  - DeepSeek 模型 API（文本 + 图片 + 联网工具）
  - DeepSeek 搜索 API（网页搜索）
  - DeepSeek 额度 API（查询余额）
"""

try:
    from comfy_api.latest import ComfyExtension
except Exception as exc:  # pragma: no cover - 老版本 ComfyUI 才会走到
    raise RuntimeError(
        "Comfy-DeepSeekAPI 需要支持 V3 节点 API 的 ComfyUI（即存在 comfy_api.latest）。"
        "请升级 ComfyUI 到最新版后重启。原始错误：%s" % exc
    ) from exc

try:
    from comfy_api.latest import io as _comfy_io
except Exception:  # pragma: no cover - 极老版本 comfy_api 没有 io 子模块
    _comfy_io = None

if _comfy_io is None or not hasattr(_comfy_io, "Autogrow"):  # pragma: no cover
    raise RuntimeError(
        "Comfy-DeepSeekAPI 需要 ComfyUI v0.4.0 及以上（io.Autogrow 动态输入）。"
        "请升级 ComfyUI 后重启。"
    )

from .nodes import DeepSeekModelNode
from .nodes_balance import DeepSeekBalanceNode
from .nodes_search import DeepSeekSearchNode
from .nodes_svg import DeepSeekText2SVGNode

__version__ = "1.2.10"


class DeepSeekExtension(ComfyExtension):
    async def get_node_list(self):
        return [DeepSeekModelNode, DeepSeekSearchNode, DeepSeekBalanceNode, DeepSeekText2SVGNode]


async def comfy_entrypoint() -> DeepSeekExtension:
    """ComfyUI 通过这个入口加载扩展（V3 schema）。"""
    return DeepSeekExtension()


__all__ = ["comfy_entrypoint"]

