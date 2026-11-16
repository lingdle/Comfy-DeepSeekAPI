"""错误类型与 HTTP 错误 → 中文提示。"""

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

_HINTS = {
    400: "请求格式错误",
    401: "认证失败，api_key 无效或已过期",
    402: "余额不足，请到 DeepSeek 平台充值",
    403: "无权访问该模型或接口",
    404: "接口地址不存在，请检查 base_url",
    408: "请求超时",
    413: "请求体过大（图片太多或太大）",
    422: "参数错误",
    429: "请求过于频繁（并发或速率超限）",
    500: "服务器内部故障",
    502: "网关错误",
    503: "服务器繁忙",
    504: "网关超时",
}


class DeepSeekAPIError(RuntimeError):
    """所有对外错误都用这个类型，ComfyUI 会把 message 显示给用户。"""

    def __init__(self, message, status=None, retryable=False, detail=None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.detail = detail


class ConfigError(DeepSeekAPIError):
    """配置类错误（api_key / base_url 等），不需要重试。"""


def extract_detail(body_text):
    """从错误响应体里挖出最有用的那句话。"""
    text = (body_text or "").strip()
    if not text:
        return ""
    try:
        import json

        data = json.loads(text)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code") or ""
                if msg:
                    return str(msg)[:300]
            for key in ("message", "detail", "msg"):
                if data.get(key):
                    return str(data[key])[:300]
    except Exception:
        pass
    return text[:300].replace("\n", " ")


def build_http_error(status, body_text, attempts=0):
    hint = _HINTS.get(status, "HTTP %s" % status)
    detail = extract_detail(body_text)
    message = "DeepSeek API %s：%s" % (status, hint)
    if detail:
        message += "（%s）" % detail
    if status == 429 and attempts:
        message += "；已自动重试 %d 次，建议降低并发或稍后再试" % attempts
    if status == 401:
        message += "。可填 sk-... 或 ${DEEPSEEK_API_KEY}（从环境变量读取）；创建 key：https://platform.deepseek.com/api_keys"
    if status == 413:
        message += "。图片太大：请减少图片数量或换更小的图（单图 ≤32 MiB，请求体 ≤48 MiB）"
    return DeepSeekAPIError(message, status=status, retryable=status in RETRYABLE_STATUS, detail=detail)

