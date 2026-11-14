"""DeepSeek HTTP 客户端：对话补全 + 网页搜索，统一重试 / 超时 / 中断 / 错误映射。"""

import json
import logging
import random
import time

import requests

from .errors import DeepSeekAPIError, build_http_error

LOG = logging.getLogger("DeepSeekAPI")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Comfy-DeepSeekAPI/0.6.6"})


def check_interrupt():
    """ComfyUI 里用户点取消时尽快退出；离开 ComfyUI 环境则空操作。"""
    try:
        from comfy import model_management as model_management
    except Exception:
        return
    model_management.throw_exception_if_processing_interrupted()


def _sleep_backoff(attempt, retry_after=None):
    if retry_after:
        try:
            seconds = float(retry_after)
        except (TypeError, ValueError):
            seconds = None
        if seconds is not None and seconds > 0:
            time.sleep(min(seconds, 30.0))
            return
    delay = min(8.0, 2.0 ** attempt) * (0.8 + random.random() * 0.4)
    time.sleep(delay)


class DeepSeekClient:
    def __init__(self, api_key, base_url, timeout=(10.0, 600.0), max_retries=2, session=None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.session = session or _SESSION

    # ------------------------------------------------------------------ 公开方法
    def chat(self, payload):
        """POST {base_url}/chat/completions。"""
        return self._request("POST", self._url("/chat/completions"), payload, "chat")

    def search(self, query, count=5, need_content=False, ori_question=None):
        """POST {base_url}/v1/tools/search（网页搜索，按次计费）。"""
        body = {
            "query": query,
            "count": int(count),
            "need_content": bool(need_content),
        }
        if ori_question:
            body["ori_question"] = ori_question
        return self._request("POST", self._url("/tools/search", versioned=True), body, "search")

    def balance(self):
        """GET /user/balance（查询余额 / 额度）。"""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return self._request("GET", base + "/user/balance", None, "balance")

    # ------------------------------------------------------------------ 内部实现
    def _url(self, path, versioned=False):
        base = self.base_url.rstrip("/")
        if versioned and not base.endswith("/v1"):
            return base + "/v1" + path
        return base + path

    def _request(self, method, url, payload=None, label="request"):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }

        attempt = 0
        while True:
            check_interrupt()
            try:
                response = self.session.request(
                    method, url, data=body, headers=headers, timeout=self.timeout
                )
            except requests.exceptions.RequestException as exc:
                error = DeepSeekAPIError("网络错误：%s" % exc, retryable=True)
                if attempt >= self.max_retries:
                    raise error from exc
                LOG.warning("DeepSeek %s 请求失败（第 %d 次），准备重试：%s", label, attempt + 1, exc)
                _sleep_backoff(attempt)
                attempt += 1
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise DeepSeekAPIError(
                        "DeepSeek %s 返回的不是合法 JSON：%s" % (label, response.text[:200])
                    ) from exc

            error = build_http_error(response.status_code, response.text, attempt)
            if not error.retryable or attempt >= self.max_retries:
                raise error

            LOG.warning(
                "DeepSeek %s 返回 %s（第 %d 次），%.1fs 后重试",
                label,
                response.status_code,
                attempt + 1,
                min(8.0, 2.0 ** attempt),
            )
            _sleep_backoff(attempt, response.headers.get("Retry-After"))
            attempt += 1

