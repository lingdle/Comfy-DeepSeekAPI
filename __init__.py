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

from .nodes import DeepSeekModelNode
from .nodes_balance import DeepSeekBalanceNode
from .nodes_search import DeepSeekSearchNode

__version__ = "1.0.10"


class DeepSeekExtension(ComfyExtension):
    async def get_node_list(self):
        return [DeepSeekModelNode, DeepSeekSearchNode, DeepSeekBalanceNode]


async def comfy_entrypoint() -> DeepSeekExtension:
    """ComfyUI 通过这个入口加载扩展（V3 schema）。"""
    return DeepSeekExtension()


__all__ = ["comfy_entrypoint"]

