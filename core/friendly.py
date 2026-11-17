"""节点执行兜底：让错误提示对用户友好，完整堆栈只写后台日志。

ComfyUI 会把异常的 traceback 一起发到前端（execution_error.traceback），
任何节点都无法把这段字段置空——除非用 ExecutionBlocker 让节点“静默跳过”，
那样终端节点会连提示都没有，所以这里保留抛错语义，只做两件事：

1. 完整堆栈（含第三方库内部帧）只进日志：LOG.exception(...)
2. 抛给 ComfyUI 的是清洗过的短异常：消息是中文可读说明，
   traceback 里只剩本文件的那一帧（用 from None 掐掉异常链）

已知错误（API / 配置 / 参数类）直接用它自己的中文说明，不重复包装。
"""

import functools
import logging

from .errors import ConfigError, DeepSeekAPIError

LOG = logging.getLogger("DeepSeekAPI")

FRIENDLY_TYPES = (DeepSeekAPIError, ConfigError, ValueError)


class NodeError(RuntimeError):
    """给用户看的错误：消息是中文说明，不含第三方堆栈。"""


def friendly_message(exc):
    """已知错误直接用它自己的中文说明；未知错误只露类型名。"""
    text = str(exc).strip()
    if isinstance(exc, FRIENDLY_TYPES) and text:
        return text
    name = type(exc).__name__
    if text:
        return "%s：%s（详细堆栈见 ComfyUI 控制台日志）" % (name, text)
    return "%s（详细堆栈见 ComfyUI 控制台日志）" % name


def guarded(func):
    """给 execute 包一层：记全量日志，抛只带一句话的短异常。"""

    @functools.wraps(func)
    def wrapper(cls, *args, **kwargs):
        try:
            return func(cls, *args, **kwargs)
        except FRIENDLY_TYPES:
            LOG.exception("节点 %s 报出可读错误", getattr(cls, "__name__", "node"))
            raise
        except Exception as exc:  # noqa: BLE001 - 兜底就是要把所有异常收掉
            LOG.exception("节点 %s 执行失败", getattr(cls, "__name__", "node"))
            raise NodeError(friendly_message(exc)) from None

    return wrapper
