"""配置解析：api_key 支持字面量与环境变量占位符，base_url 归一化。"""

import re
from os import environ

from .errors import ConfigError

_PLACEHOLDERS = (
    re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$"),
    re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$"),
    re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE),
    re.compile(r"^%([A-Za-z_][A-Za-z0-9_]*)%$"),
)

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_API_KEY_PLACEHOLDER = "${DEEPSEEK_API_KEY}"
KEY_URL = "https://platform.deepseek.com/api_keys"


def resolve_api_key(raw):
    """支持三种写法：

    1. 直接填 key：sk-xxxxxxxx
    2. 占位符：${DEEPSEEK_API_KEY} / $DEEPSEEK_API_KEY / env:DEEPSEEK_API_KEY / %DEEPSEEK_API_KEY%
    3. 裸环境变量名：DEEPSEEK_API_KEY（全大写且系统里确实存在该变量）
    """
    value = (raw or "").strip()
    if not value:
        raise ConfigError(
            "api_key 为空：请填 sk-...（创建： https://platform.deepseek.com/api_keys），"
            "或填 ${DEEPSEEK_API_KEY} 从环境变量读取"
        )

    for pattern in _PLACEHOLDERS:
        matched = pattern.match(value)
        if matched:
            name = matched.group(1)
            env_value = (environ.get(name) or "").strip()
            if not env_value:
                raise ConfigError(
                    "环境变量 %s 未设置：请在启动 ComfyUI 前设置它，"
                    "或直接在 api_key 里填 sk-...（创建 key：%s）" % (name, KEY_URL)
                )
            return env_value

    if _ENV_NAME.match(value) and value.isupper():
        env_value = (environ.get(value) or "").strip()
        if not env_value:
            raise ConfigError(
                "看起来你填的是环境变量名 %s，但系统里没有这个变量；"
                "请设置它，或直接填 sk-...（创建 key：%s）" % (value, KEY_URL)
            )
        return env_value

    return value


def normalize_base_url(raw):
    value = (raw or "").strip() or DEFAULT_BASE_URL
    if not re.match(r"^https?://", value, re.IGNORECASE):
        raise ConfigError("base_url 必须以 http:// 或 https:// 开头，当前值：%s" % value)
    return value.rstrip("/")


def mask_secret(value):
    """日志/报错里用，绝不回显完整 key。"""
    text = (value or "").strip()
    if len(text) <= 8:
        return "*" * len(text)
    return text[:5] + "****" + text[-4:]

