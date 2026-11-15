"""DeepSeek 额度（余额）查询节点（V3 schema）。

精简实现：GET /user/balance → 一行汇总文本 + 原始 JSON 输出。
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

LOG = logging.getLogger("DeepSeekAPI")

NODE_ID = "DeepSeekAPI_Balance"


def _pick_info(infos, currency):
    """按 currency 选一条 balance_info；auto 时优先 CNY，否则取第一条。"""
    if not infos:
        return None
    wanted = (currency or "auto").strip().upper()
    if wanted in ("CNY", "USD"):
        for info in infos:
            if (info.get("currency") or "").upper() == wanted:
                return info
    for info in infos:
        if (info.get("currency") or "").upper() == "CNY":
            return info
    return infos[0]


def _format_summary(available, infos, chosen):
    if chosen is None:
        return "额度：%s（接口未返回余额明细）" % ("可用" if available else "不可用")

    currency = chosen.get("currency") or "?"
    total = chosen.get("total_balance") or "0.00"
    granted = chosen.get("granted_balance") or "0.00"
    topped = chosen.get("topped_up_balance") or "0.00"

    status = "可用" if available else "不可用（余额不足或账户受限）"
    text = "额度：%s ｜ %s %s（赠送 %s / 充值 %s）" % (status, currency, total, granted, topped)

    others = [info for info in infos if info is not chosen]
    if others:
        extra = "、".join(
            "%s %s" % (info.get("currency") or "?", info.get("total_balance") or "0.00")
            for info in others
        )
        text += " ｜ 其它币种：%s" % extra
    return text


class DeepSeekBalanceNode(io.ComfyNode):
    """查询账户额度：汇总文本 + 原始 JSON。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="DeepSeek 额度 API",
            category="DeepSeek",
            description=(
                "查询账户额度（GET /user/balance）。"
                "输出一行汇总文本 + 接口原始 JSON（含 is_available、balance_infos 等全部字段）。"
                "查询本身不消耗 token、不产生费用。\nQuery the account balance via GET /user/balance. Outputs a one-line summary plus the raw JSON response. The lookup costs no tokens and no money."
            ),
            search_aliases=["deepseek", "balance", "quota", "credit", "额度", "余额", "充值"],
            inputs=[
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
                    tooltip="API 地址，默认 https://api.deepseek.com（填 /v1 结尾也行，节点会自动处理）\nBase URL, default https://api.deepseek.com (a trailing /v1 is handled automatically)",
                ),
                io.Combo.Input(
                    "currency",
                    options=["auto", "CNY", "USD"],
                    default="auto",
                    tooltip="汇总文本里显示哪个币种；auto = 优先 CNY，没有则取第一个。JSON 输出始终是完整返回\nWhich currency to show in the summary; auto = CNY first, otherwise the first entry. JSON output is always the full response",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="text",
                    tooltip="一行汇总，例如：额度：可用 ｜ CNY 81.00（赠送 10.00 / 充值 71.00）\nOne-line summary, e.g. balance: available | CNY 81.00 (granted 10.00 / topped up 71.00)",
                ),
                io.String.Output(
                    display_name="json",
                    tooltip='接口原始 JSON，例如\nRaw API response JSON, e.g. {"is_available": true, "balance_infos": [...]}',
                ),
            ],
        )

    @classmethod
    def execute(cls, api_key, base_url, currency="auto"):
        key = resolve_api_key(api_key)
        endpoint = normalize_base_url(base_url)

        data = DeepSeekClient(key, endpoint).balance()

        available = bool(data.get("is_available"))
        infos = data.get("balance_infos") or []
        chosen = _pick_info(infos, currency)

        summary = _format_summary(available, infos, chosen)
        raw = json.dumps(data, ensure_ascii=False)

        LOG.info("DeepSeek 额度：%s", summary)

        try:
            return io.NodeOutput(summary, raw, ui={"text": [summary]})
        except TypeError:
            LOG.warning("当前 ComfyUI 的 io.NodeOutput 不支持 ui 参数，已跳过节点上的额度显示")
            return io.NodeOutput(summary, raw)

