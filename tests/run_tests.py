"""本地自测（不需要 ComfyUI、不需要网络）。

用法：python3 tests/run_tests.py
覆盖：配置解析、峰谷与费用、错误映射、HTTP 重试、V3 schema 结构、execute 载荷。
"""

import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import types

DOLLAR = chr(36)
PLACEHOLDER = DOLLAR + "{DEEPSEEK_API_KEY}"

PKG_DIR = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- comfy_api 桩
class _Type:
    def __init__(self, name):
        self.name = name

    def Input(self, id, **kwargs):
        record = {"kind": "input", "type": self.name, "id": id}
        record.update(kwargs)
        return record

    def Output(self, **kwargs):
        record = {"kind": "output", "type": self.name}
        record.update(kwargs)
        return record


class _AutogrowTemplatePrefix:
    def __init__(self, input=None, prefix="", min=0, max=10):
        self.input = input
        self.prefix = prefix
        self.min = min
        self.max = max


class _Autogrow:
    TemplatePrefix = _AutogrowTemplatePrefix

    @staticmethod
    def Input(id, template=None, **kwargs):
        record = {"kind": "input", "type": "COMFY_AUTOGROW_V3", "id": id, "template": template}
        record.update(kwargs)
        return record


class Schema:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __getattr__(self, item):
        try:
            return self.kwargs[item]
        except KeyError:
            raise AttributeError(item)


class NodeOutput:
    def __init__(self, *args, **kwargs):
        self.results = args
        self.ui = kwargs.get("ui")
        self.kwargs = kwargs


class ComfyNode:
    pass


class ComfyExtension:
    async def get_node_list(self):
        raise NotImplementedError


def _install_stub():
    io = types.SimpleNamespace(
        Schema=Schema,
        NodeOutput=NodeOutput,
        ComfyNode=ComfyNode,
        String=_Type("STRING"),
        Int=_Type("INT"),
        Float=_Type("FLOAT"),
        Boolean=_Type("BOOLEAN"),
        Combo=_Type("COMBO"),
        Image=_Type("IMAGE"),
        Mask=_Type("MASK"),
        Autogrow=_Autogrow,
    )
    latest = types.ModuleType("comfy_api.latest")
    latest.io = io
    latest.ComfyExtension = ComfyExtension
    latest.ComfyNode = ComfyNode
    latest.Schema = Schema
    latest.NodeOutput = NodeOutput

    package = types.ModuleType("comfy_api")
    package.latest = latest
    sys.modules["comfy_api"] = package
    sys.modules["comfy_api.latest"] = latest
    return latest


_install_stub()


def _load_package():
    spec = importlib.util.spec_from_file_location(
        "dsapi", PKG_DIR / "__init__.py", submodule_search_locations=[str(PKG_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dsapi"] = module
    spec.loader.exec_module(module)
    return module


PKG = _load_package()
NS = PKG.nodes
SEARCH = sys.modules["dsapi.nodes_search"]
BAL = sys.modules["dsapi.nodes_balance"]
WEB = sys.modules["dsapi.core.websearch"]
SQ = sys.modules["dsapi.core.searchquery"]
CFG = sys.modules["dsapi.core.config"]
PRC = sys.modules["dsapi.core.pricing"]
ERR = sys.modules["dsapi.core.errors"]
CLI = sys.modules["dsapi.core.client"]
IMG = sys.modules["dsapi.core.imaging"]


# ------------------------------------------------------------------- 测试框架
TESTS = []


def test(func):
    TESTS.append(func)
    return func


class FakeResponse:
    def __init__(self, status, payload=None, text=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, data=None, headers=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "data": data, "headers": headers, "timeout": timeout}
        )
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.init_args = None
        self.payload = None
        self.search_args = None

    def __call__(self, *args, **kwargs):
        self.init_args = (args, kwargs)
        return self

    def chat(self, payload):
        self.payload = payload
        if self.error is not None:
            raise self.error
        return self.response

    def balance(self):
        if self.error is not None:
            raise self.error
        return self.response if self.response is not None else {"is_available": True, "balance_infos": []}

    def search(self, query, count=5, need_content=False, question=None):
        self.search_args = {
            "query": query,
            "count": count,
            "need_content": need_content,
            "question": question,
        }
        if self.error is not None:
            raise self.error
        return self.response if self.response is not None else {"results": []}


# ---------------------------------------------------------------------- 配置
@test
def test_resolve_literal_key():
    assert CFG.resolve_api_key("sk-abcdef") == "sk-abcdef"


@test
def test_resolve_placeholder():
    os.environ["DSAPI_TEST_KEY"] = "sk-from-env"
    try:
        assert CFG.resolve_api_key("@@PLACEHOLDER@@".replace("@@PLACEHOLDER@@", DOLLAR + "{DSAPI_TEST_KEY}")) == "sk-from-env"
        assert CFG.resolve_api_key("env:DSAPI_TEST_KEY") == "sk-from-env"
        assert CFG.resolve_api_key("%DSAPI_TEST_KEY%") == "sk-from-env"
        assert CFG.resolve_api_key("DSAPI_TEST_KEY") == "sk-from-env"
    finally:
        os.environ.pop("DSAPI_TEST_KEY", None)


@test
def test_resolve_missing_env_raises():
    os.environ.pop("DSAPI_NOT_EXIST", None)
    for raw in (DOLLAR + "{DSAPI_NOT_EXIST}", "env:DSAPI_NOT_EXIST", "DSAPI_NOT_EXIST"):
        try:
            CFG.resolve_api_key(raw)
        except ERR.ConfigError:
            continue
        raise AssertionError("应当抛出 ConfigError: %s" % raw)


@test
def test_resolve_empty_raises():
    try:
        CFG.resolve_api_key("   ")
    except ERR.ConfigError:
        return
    raise AssertionError("空 api_key 应当报错")


@test
def test_normalize_base_url():
    assert CFG.normalize_base_url("") == "https://api.deepseek.com"
    assert CFG.normalize_base_url("https://api.deepseek.com/") == "https://api.deepseek.com"
    assert CFG.normalize_base_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com/v1"
    assert CFG.normalize_base_url(" http://127.0.0.1:8000 ") == "http://127.0.0.1:8000"
    try:
        CFG.normalize_base_url("api.deepseek.com")
    except ERR.ConfigError:
        pass
    else:
        raise AssertionError("缺少协议头应当报错")


@test
def test_mask_secret():
    assert CFG.mask_secret("sk-1234567890abcdef").endswith("cdef")
    assert "1234567890" not in CFG.mask_secret("sk-1234567890abcdef")


# ------------------------------------------------------------------ 价格与峰谷
@test
def test_peak_windows():
    from datetime import datetime

    monday = datetime(2026, 11, 16, 9, 0, tzinfo=PRC.BEIJING)
    assert monday.weekday() == 0, "2026-11-16 应当是周一"
    assert PRC.is_peak(monday) is True
    assert PRC.is_peak(monday.replace(hour=8, minute=59)) is False
    assert PRC.is_peak(monday.replace(hour=11, minute=59)) is True
    assert PRC.is_peak(monday.replace(hour=12, minute=0)) is False
    assert PRC.is_peak(monday.replace(hour=13, minute=59)) is False
    assert PRC.is_peak(monday.replace(hour=14, minute=0)) is True
    assert PRC.is_peak(monday.replace(hour=17, minute=59)) is True
    assert PRC.is_peak(monday.replace(hour=18, minute=0)) is False

    saturday = datetime(2026, 11, 14, 10, 0, tzinfo=PRC.BEIJING)
    assert saturday.weekday() == 5, "2026-11-14 应当是周六"
    assert PRC.is_peak(saturday) is False


@test
def test_estimate_cost_flash():
    usage = {"prompt_tokens": 2000, "prompt_cache_hit_tokens": 1000, "prompt_cache_miss_tokens": 1000, "completion_tokens": 1000}
    idle = PRC.estimate_cost("deepseek-flash", usage, peak=False)
    peak = PRC.estimate_cost("deepseek-flash", usage, peak=True)
    assert abs(idle - 0.00502) < 1e-9, idle
    assert abs(peak - 0.01004) < 1e-9, peak
    assert peak == idle * 2


@test
def test_estimate_cost_unknown_model():
    assert PRC.estimate_cost("some-other-model", {"prompt_tokens": 10}) is None


@test
def test_format_usage_warns_on_length():
    text = PRC.format_usage(
        "deepseek-flash",
        {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 0},
        0.001,
        finish_reason="length",
        n_images=2,
    )
    assert "估算" in text
    assert "截断" in text
    assert "图片 2 张" in text


# ------------------------------------------------------------------ 错误映射
@test
def test_error_mapping():
    err = ERR.build_http_error(401, json.dumps({"error": {"message": "invalid api key"}}))
    assert err.status == 401 and err.retryable is False
    assert "认证失败" in str(err) and "invalid api key" in str(err)

    err429 = ERR.build_http_error(429, "{}", attempts=2)
    assert err429.retryable is True and "已自动重试 2 次" in str(err429)

    err500 = ERR.build_http_error(500, "")
    assert err500.retryable is True

    err400 = ERR.build_http_error(400, "bad request")
    assert err400.retryable is False and "bad request" in str(err400)


# ------------------------------------------------------------------ HTTP 重试
@test
def test_client_retries_429_then_succeeds():
    original = CLI._sleep_backoff
    CLI._sleep_backoff = lambda *args, **kwargs: None
    try:
        session = FakeSession([
            FakeResponse(429, {"error": {"message": "rate limited"}}),
            FakeResponse(200, {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}], "usage": {}}),
        ])
        client = CLI.DeepSeekClient("sk-test", "https://api.deepseek.com", session=session)
        data = client.chat({"model": "deepseek-flash", "messages": []})
        assert data["choices"][0]["message"]["content"] == "hi"
        assert len(session.calls) == 2
        assert session.calls[0]["url"] == "https://api.deepseek.com/chat/completions"
        assert session.calls[0]["headers"]["Authorization"] == "Bearer sk-test"
        sent = json.loads(session.calls[0]["data"].decode("utf-8"))
        assert sent["model"] == "deepseek-flash"
    finally:
        CLI._sleep_backoff = original


@test
def test_client_does_not_retry_401():
    session = FakeSession([FakeResponse(401, {"error": {"message": "bad key"}})])
    client = CLI.DeepSeekClient("sk-test", "https://api.deepseek.com", session=session)
    try:
        client.chat({"model": "deepseek-flash", "messages": []})
    except ERR.DeepSeekAPIError as exc:
        assert exc.status == 401
        assert len(session.calls) == 1
        return
    raise AssertionError("401 应当直接抛出")


@test
def test_client_gives_up_after_retries():
    original = CLI._sleep_backoff
    CLI._sleep_backoff = lambda *args, **kwargs: None
    try:
        session = FakeSession([FakeResponse(503, {}), FakeResponse(503, {}), FakeResponse(503, {})])
        client = CLI.DeepSeekClient("sk-test", "https://api.deepseek.com", max_retries=2, session=session)
        try:
            client.chat({"model": "deepseek-flash", "messages": []})
        except ERR.DeepSeekAPIError as exc:
            assert exc.status == 503
            assert len(session.calls) == 3
            return
        raise AssertionError("应当抛出异常")
    finally:
        CLI._sleep_backoff = original


# --------------------------------------------------------------------- 节点
@test
def test_schema_structure():
    schema = NS.DeepSeekModelNode.define_schema()
    assert schema.node_id == "DeepSeekAPI_Model"
    assert schema.category == "DeepSeekAPI"
    assert schema.display_name

    inputs = {item["id"]: item for item in schema.inputs if item["kind"] == "input"}
    assert inputs["model"]["default"] == "deepseek-flash"
    assert inputs["api_key"]["default"] == PLACEHOLDER
    assert inputs["base_url"]["default"] == "https://api.deepseek.com"
    assert inputs["system_prompt"]["multiline"] is True
    assert inputs["user_prompt"]["multiline"] is True
    assert inputs["system_prompt"]["default"] == "你是一个图像理解助手"
    assert inputs["user_prompt"]["default"] == "图片上是什么？"
    assert inputs["thinking"]["default"] == "close"
    assert inputs["thinking"]["options"] == ["close", "low", "high", "max"]
    assert inputs["max_tokens"]["default"] == 1024
    assert inputs["image_detail"]["default"] == "low"
    assert inputs["image_max_side"]["default"] == 1024
    assert inputs["max_images"]["default"] == 5

    assert inputs["images"]["optional"] is True
    assert inputs["images"]["type"] == "IMAGE"

    slots = inputs["image_slots"]
    assert slots["type"] == "COMFY_AUTOGROW_V3"
    assert slots["optional"] is True
    assert slots["template"].prefix == "image_"
    assert slots["template"].min == 0
    assert slots["template"].max == 10

    order = [item["id"] for item in schema.inputs]
    assert order[:9] == [
        "user_prompt",
        "system_prompt",
        "model",
        "thinking",
        "web_search",
        "read_url",
        "api_key",
        "base_url",
        "image_slots",
    ]

    assert inputs["web_search"]["default"] is False
    assert inputs["read_url"]["default"] is False

    outputs = [item for item in schema.outputs if item["kind"] == "output"]
    assert len(outputs) == 5
    assert [item["display_name"] for item in outputs] == [
        "text",
        "reasoning",
        "usage",
        "sources",
        "json",
    ]


@test
def test_entrypoint_returns_nodes():
    async def collect():
        extension = await PKG.comfy_entrypoint()
        return await extension.get_node_list()

    nodes = asyncio.run(collect())
    assert nodes == [
        NS.DeepSeekModelNode,
        SEARCH.DeepSeekSearchNode,
        BAL.DeepSeekBalanceNode,
    ]


@test
def test_execute_text_payload():
    fake = FakeClient(response={
        "choices": [{"message": {"content": "hello there"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 10},
    })
    original = NS.DeepSeekClient
    NS.DeepSeekClient = fake
    try:
        result = NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="be nice",
            user_prompt="hi",
        )
    finally:
        NS.DeepSeekClient = original

    payload = fake.payload
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["temperature"] == 1.0
    assert "reasoning_effort" not in payload
    assert payload["max_tokens"] == 1024
    assert payload["messages"][0] == {"role": "system", "content": "be nice"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}

    assert result.results[0] == "hello there"
    assert result.results[1] == ""
    assert "估算" in result.results[2]
    assert result.ui["text"][0] == result.results[2]

    raw = json.loads(result.results[4])
    assert raw["choices"][0]["message"]["content"] == "hello there"


@test
def test_execute_thinking_payload():
    fake = FakeClient(response={
        "choices": [{"message": {"content": "42", "reasoning_content": "because"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 5,
                  "completion_tokens_details": {"reasoning_tokens": 3}},
    })
    original = NS.DeepSeekClient
    NS.DeepSeekClient = fake
    try:
        result = NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="q",
            thinking="high",
            temperature=0.5,
        )
    finally:
        NS.DeepSeekClient = original

    payload = fake.payload
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert "temperature" not in payload
    assert len(payload["messages"]) == 1
    assert result.results[1] == "because"


@test
def test_execute_with_images(monkeypatch=None):
    calls = {}

    def fake_encode(tensor, max_images=5, max_side=1024, quality=85):
        calls["max_images"] = max_images
        calls["max_side"] = max_side
        return ["data:image/jpeg;base64,AAA"]

    original_encode = NS.tensor_to_data_urls
    original_client = NS.DeepSeekClient
    fake = FakeClient(response={
        "choices": [{"message": {"content": "a cat"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 100},
    })
    NS.tensor_to_data_urls = fake_encode
    NS.DeepSeekClient = fake
    try:
        result = NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="描述",
            images="tensor-slot",
            max_images=3,
        )
    finally:
        NS.tensor_to_data_urls = original_encode
        NS.DeepSeekClient = original_client

    content = fake.payload["messages"][-1]["content"]
    assert isinstance(content, list) and content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["detail"] == "low"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert calls["max_images"] == 3
    assert result.results[0] == "a cat"


@test
def test_merge_image_inputs_order_and_skips_empty():
    assert NS._merge_image_inputs(None, None) == []
    assert NS._merge_image_inputs({}, "batch") == ["batch"]
    assert NS._merge_image_inputs({"image_2": None, "image_10": "c", "image_0": "a"}, "batch") == [
        "a",
        "c",
        "batch",
    ]


@test
def test_execute_merges_autogrow_slots_before_images():
    seen = []

    def fake_encode(tensor, max_images=5, max_side=1024, quality=85):
        seen.append(tensor)
        return ["data:image/jpeg;base64," + str(tensor)]

    original_encode = NS.tensor_to_data_urls
    original_client = NS.DeepSeekClient
    fake = FakeClient(response={
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    })
    NS.tensor_to_data_urls = fake_encode
    NS.DeepSeekClient = fake
    try:
        NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            user_prompt="描述",
            image_slots={"image_1": "B", "image_0": "A", "image_10": "C"},
            images="batch",
            max_images=4,
        )
    finally:
        NS.tensor_to_data_urls = original_encode
        NS.DeepSeekClient = original_client

    assert seen == ["A", "B", "C", "batch"]
    content = fake.payload["messages"][-1]["content"]
    urls = [block["image_url"]["url"] for block in content if block["type"] == "image_url"]
    assert len(urls) == 4


@test
def test_execute_autogrow_slots_take_priority_over_images():
    seen = []

    def fake_encode(tensor, max_images=5, max_side=1024, quality=85):
        seen.append((tensor, max_images))
        return ["data:image/jpeg;base64,AAA"]

    original_encode = NS.tensor_to_data_urls
    original_client = NS.DeepSeekClient
    fake = FakeClient(response={
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    })
    NS.tensor_to_data_urls = fake_encode
    NS.DeepSeekClient = fake
    try:
        NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            user_prompt="描述",
            image_slots={"image_0": "A", "image_1": "B"},
            images="batch",
            max_images=2,
        )
    finally:
        NS.tensor_to_data_urls = original_encode
        NS.DeepSeekClient = original_client

    assert seen == [("A", 2), ("B", 1)]
    content = fake.payload["messages"][-1]["content"]
    assert len([b for b in content if b["type"] == "image_url"]) == 2


@test
def test_execute_vision_uses_default_prompt():
    original_encode = NS.tensor_to_data_urls
    original_client = NS.DeepSeekClient
    fake = FakeClient(response={"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": {}})
    NS.tensor_to_data_urls = lambda tensor, max_images=5, max_side=1024, quality=85: ["data:image/jpeg;base64,AAA"]
    NS.DeepSeekClient = fake
    try:
        NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="",
            images="tensor-slot",
        )
    finally:
        NS.tensor_to_data_urls = original_encode
        NS.DeepSeekClient = original_client
    assert fake.payload["messages"][-1]["content"][0]["text"] == NS.DEFAULT_VISION_PROMPT


@test
def test_execute_rejects_empty_prompt():
    original = NS.DeepSeekClient
    NS.DeepSeekClient = FakeClient(response={"choices": []})
    try:
        try:
            NS.DeepSeekModelNode.execute(
                model="deepseek-flash", api_key="sk-test",
                base_url="https://api.deepseek.com",
                system_prompt="", user_prompt="   ",
            )
        except ERR.DeepSeekAPIError as exc:
            assert "至少" in str(exc)
            return
        raise AssertionError("空提示词应当报错")
    finally:
        NS.DeepSeekClient = original


@test
def test_execute_rejects_pro_with_image():
    original_encode = NS.tensor_to_data_urls
    NS.tensor_to_data_urls = lambda tensor, max_images=5, max_side=1024, quality=85: ["data:image/jpeg;base64,AAA"]
    try:
        try:
            NS.DeepSeekModelNode.execute(
                model="deepseek-v4-pro", api_key="sk-test",
                base_url="https://api.deepseek.com",
                system_prompt="", user_prompt="看这张图",
                images="tensor-slot",
            )
        except ERR.DeepSeekAPIError as exc:
            assert "不支持图片" in str(exc)
            return
        raise AssertionError("v4-pro 带图应当报错")
    finally:
        NS.tensor_to_data_urls = original_encode


# ------------------------------------------------------------------ 搜索节点
@test
def test_search_schema_structure():
    schema = SEARCH.DeepSeekSearchNode.define_schema()
    assert schema.node_id == "DeepSeekAPI_Search"
    assert schema.category == "DeepSeekAPI"

    order = [item["id"] for item in schema.inputs]
    assert order[:4] == ["question", "query", "after", "lang"]

    inputs = {item["id"]: item for item in schema.inputs if item["kind"] == "input"}
    assert inputs["question"]["default"] == "What's the latest DeepSeek news today?"
    assert inputs["question"]["multiline"] is True
    assert inputs["query"]["multiline"] is True
    assert inputs["query"]["default"] == "DeepSeek latest model"
    for field in ("site_include", "site_exclude", "exclude_words", "exact_phrases", "after", "before"):
        assert inputs[field]["default"] == ""
    assert inputs["lang"]["default"] == "zh,en"
    assert inputs["exact_phrase"]["default"] is False
    assert inputs["api_key"]["default"] == PLACEHOLDER
    assert inputs["base_url"]["default"] == "https://api.deepseek.com"
    assert inputs["count"]["default"] == 5
    assert inputs["count"]["min"] == 1 and inputs["count"]["max"] == 50
    assert inputs["need_content"]["default"] is False

    outputs = [item for item in schema.outputs if item["kind"] == "output"]
    assert [item["display_name"] for item in outputs] == ["text", "json", "usage"]


@test
def test_client_search_url_and_body():
    session = FakeSession([FakeResponse(200, {"results": []})])
    client = CLI.DeepSeekClient("sk-test", "https://api.deepseek.com", session=session)
    client.search("DeepSeek site:github.com", count=7, need_content=True)

    call = session.calls[0]
    assert call["url"] == "https://api.deepseek.com/v1/tools/search"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    body = json.loads(call["data"].decode("utf-8"))
    assert body == {
        "query": "DeepSeek site:github.com",
        "count": 7,
        "need_content": True,
    }

    session2 = FakeSession([FakeResponse(200, {"results": []})])
    client2 = CLI.DeepSeekClient("sk-test", "https://api.deepseek.com/v1", session=session2)
    client2.search("x")
    assert session2.calls[0]["url"] == "https://api.deepseek.com/v1/tools/search"


@test
def test_search_digest_and_usage():
    results = [
        {
            "title": "A", "url": "https://a.example", "summary": "摘要A", "snippet": "",
            "content": "", "site_name": "站点A", "date": "2026-06-01T00:00:00+00:00",
            "authority": 3, "rerank_score": 2.4,
        },
        {
            "title": "B", "url": "https://b.example", "summary": "", "snippet": "片段B",
            "content": "正文B", "site_name": None, "date": None,
            "authority": -1, "rerank_score": 0.5,
        },
    ]

    digest = WEB.format_search_results(results, query="测试词")
    assert "# 搜索：测试词" in digest
    assert "共 2 条结果 · 优质 1 条" in digest
    assert "## 1. A" in digest
    assert "https://a.example" in digest
    assert "站点 站点A" in digest
    assert "权威 3/4" in digest
    assert "相关度 2.40" in digest
    assert "## 2. B" in digest and "摘要：片段B" in digest
    assert "正文B" not in digest

    with_content = WEB.format_search_results(results, query="测试词", include_content=True)
    assert "正文：" in with_content and "正文B" in with_content

    usage = WEB.format_search_usage("q", results)
    assert "返回 2 条" in usage
    assert "优质 1 条" in usage
    assert "0.0050" in usage

    assert "没有搜索到结果" in WEB.format_search_results([])


@test
def test_search_execute_payload():
    fake = FakeClient(response={"results": [
        {
            "title": "A", "url": "https://a", "summary": "s", "snippet": "",
            "content": "", "site_name": None, "date": None,
            "authority": 3, "rerank_score": 2.0,
        }
    ]})
    original = SEARCH.DeepSeekClient
    SEARCH.DeepSeekClient = fake
    try:
        result = SEARCH.DeepSeekSearchNode.execute(
            query="  DeepSeek  ",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            count=3,
            need_content=True,
            question="  原始问题 ",
        )
    finally:
        SEARCH.DeepSeekClient = original

    assert fake.search_args == {
        "query": "DeepSeek",
        "count": 3,
        "need_content": True,
        "question": "原始问题",
    }
    assert "## 1. A" in result.results[0]
    assert json.loads(result.results[1])["results"][0]["title"] == "A"
    assert "返回 1 条" in result.results[2]
    assert result.ui["text"][0] == result.results[2]


@test
def test_search_rejects_empty_and_long_query():
    original = SEARCH.DeepSeekClient
    SEARCH.DeepSeekClient = FakeClient(response={"results": []})
    try:
        try:
            SEARCH.DeepSeekSearchNode.execute(
                query="   ", api_key="sk-test", base_url="https://api.deepseek.com"
            )
        except ERR.DeepSeekAPIError as exc:
            assert "搜索词为空" in str(exc)
        else:
            raise AssertionError("空 query 应当报错")

        try:
            SEARCH.DeepSeekSearchNode.execute(
                query="x" * 200, api_key="sk-test", base_url="https://api.deepseek.com"
            )
        except ERR.DeepSeekAPIError as exc:
            assert "超过上限" in str(exc)
        else:
            raise AssertionError("超长 query 应当报错")
    finally:
        SEARCH.DeepSeekClient = original


# ------------------------------------------------------------------ 联网工具
@test
def test_model_web_tools_payload():
    fake = FakeClient(response={"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": {}})
    original = NS.DeepSeekClient
    NS.DeepSeekClient = fake
    try:
        NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="q",
        )
        assert "tools" not in fake.payload

        NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="q",
            web_search=True,
            read_url=True,
        )
        assert fake.payload["tools"] == [
            {"type": "deepseek_web_search"},
            {"type": "deepseek_read_url"},
        ]

        try:
            NS.DeepSeekModelNode.execute(
                model="deepseek-v4-pro",
                api_key="sk-test",
                base_url="https://api.deepseek.com",
                system_prompt="",
                user_prompt="q",
                web_search=True,
            )
        except ERR.DeepSeekAPIError as exc:
            assert "deepseek-flash" in str(exc)
        else:
            raise AssertionError("v4-pro + 联网工具应当报错")
    finally:
        NS.DeepSeekClient = original


@test
def test_model_sources_and_tool_usage():
    fake = FakeClient(response={
        "choices": [{
            "message": {
                "content": "answer",
                "annotations": [
                    {"type": "url_citation", "url_citation": {"url": "https://a.example", "title": "A"}}
                ],
                "server_tool_calls": [{
                    "calls": [{
                        "page": {"url": "https://b.example", "title": "B"},
                        "sources": [{"url": "https://c.example", "title": "C"}],
                    }]
                }],
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 10,
            "server_tool_use": {"tool_search": 1, "tool_fetch": 1, "tool_image_search": 0},
        },
    })
    original = NS.DeepSeekClient
    NS.DeepSeekClient = fake
    try:
        result = NS.DeepSeekModelNode.execute(
            model="deepseek-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            system_prompt="",
            user_prompt="q",
            web_search=True,
            read_url=True,
        )
    finally:
        NS.DeepSeekClient = original

    sources = result.results[3]
    for url in ("https://a.example", "https://b.example", "https://c.example"):
        assert url in sources, sources
    assert "联网 2 次（搜索 1 / 抓取 1 / 图片 0）" in result.results[2]


# ------------------------------------------------------------------ 搜索语法拼接
@test
def test_build_query_filters():
    text = SQ.build_query(
        query="DeepSeek",
        site_include="https://github.com, hf.co",
        site_exclude="example.com",
        exclude_words="广告, release notes",
        exact_phrase=False,
        lang="zh, en",
        after="2025",
        before="2026-06-01",
    )
    assert "DeepSeek" in text
    assert "site:github.com OR site:hf.co" in text
    assert "-site:example.com" in text
    assert "-广告" in text
    assert '-"release notes"' in text
    assert "lang:zh,en" in text
    assert "after:2025" in text
    assert "before:2026-06-01" in text


@test
def test_build_query_exact_phrase_and_defaults():
    assert SQ.build_query(query="hello world", exact_phrase=True) == '"hello world"'
    assert SQ.build_query(query="  hello  ") == "hello"
    assert SQ.build_query(query="a", lang="ZH") == "a lang:zh"


@test
def test_build_query_errors():
    try:
        SQ.build_query(query="")
    except ERR.DeepSeekAPIError as exc:
        assert "搜索词为空" in str(exc)
    else:
        raise AssertionError("空搜索词应当报错")

    try:
        SQ.build_query(query="a", after="去年")
    except ERR.DeepSeekAPIError as exc:
        assert "日期格式" in str(exc)
    else:
        raise AssertionError("非法日期应当报错")

    try:
        SQ.build_query(query="a", site_include="x" * 200)
    except ERR.DeepSeekAPIError as exc:
        assert "超过上限" in str(exc)
    else:
        raise AssertionError("超长搜索词应当报错")


@test
def test_build_query_sanitizes_user_input():
    text = SQ.build_query(
        query="DeepSeek",
        site_include="site:github.com, hf.co OR example.com",
        site_exclude="-site:example.com",
        exclude_words="-广告 -搬运",
        exact_phrases="官方文档, release notes",
    )
    assert "site:github.com OR site:hf.co OR site:example.com" in text
    assert "site:site:" not in text
    assert "site:OR" not in text
    assert "-site:example.com" in text
    assert "-site:-site:" not in text
    assert "-广告" in text and "-搬运" in text
    assert "--广告" not in text
    assert '"官方文档"' in text
    assert '"release notes"' in text


@test
def test_build_query_phrase_switch_and_field():
    assert SQ.build_query(query="hello world", exact_phrase=True) == '"hello world"'
    assert SQ.build_query(query="kw", exact_phrases="a b,c") == 'kw "a b" "c"'
    assert SQ.build_query(query="kw", exact_phrases="") == "kw"


# ------------------------------------------------------------------ 额度节点
@test
def test_client_balance_url():
    session = FakeSession([FakeResponse(200, {"is_available": True, "balance_infos": []})])
    CLI.DeepSeekClient("sk-test", "https://api.deepseek.com", session=session).balance()
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"] == "https://api.deepseek.com/user/balance"

    session2 = FakeSession([FakeResponse(200, {"is_available": True, "balance_infos": []})])
    CLI.DeepSeekClient("sk-test", "https://api.deepseek.com/v1", session=session2).balance()
    assert session2.calls[0]["url"] == "https://api.deepseek.com/user/balance"


@test
def test_balance_node_schema():
    schema = BAL.DeepSeekBalanceNode.define_schema()
    assert schema.node_id == "DeepSeekAPI_Balance"

    inputs = {item["id"]: item for item in schema.inputs if item["kind"] == "input"}
    assert list(inputs) == ["api_key", "base_url", "currency"]
    assert inputs["currency"]["default"] == "auto"
    assert inputs["currency"]["options"] == ["auto", "CNY", "USD"]

    outputs = [item for item in schema.outputs if item["kind"] == "output"]
    assert [item["display_name"] for item in outputs] == ["text", "json"]
    assert [item["type"] for item in outputs] == ["STRING", "STRING"]


@test
def test_balance_execute():
    payload = {
        "is_available": True,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "81.50", "granted_balance": "10.00", "topped_up_balance": "71.50"},
            {"currency": "USD", "total_balance": "3.00", "granted_balance": "0.00", "topped_up_balance": "3.00"},
        ],
    }
    fake = FakeClient(response=payload)
    original = BAL.DeepSeekClient
    BAL.DeepSeekClient = fake
    try:
        result = BAL.DeepSeekBalanceNode.execute(
            api_key="sk-test", base_url="https://api.deepseek.com"
        )
    finally:
        BAL.DeepSeekClient = original

    assert result.results[0].startswith("额度：可用")
    assert "CNY 81.50" in result.results[0]
    assert "其它币种：USD 3.00" in result.results[0]
    assert result.ui["text"][0] == result.results[0]

    data = json.loads(result.results[1])
    assert data["is_available"] is True
    assert data["balance_infos"][0]["currency"] == "CNY"
    assert data["balance_infos"][1]["total_balance"] == "3.00"


@test
def test_balance_execute_currency_and_unavailable():
    payload = {
        "is_available": False,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "0.00", "granted_balance": "0.00", "topped_up_balance": "0.00"},
            {"currency": "USD", "total_balance": "3.00", "granted_balance": "1.00", "topped_up_balance": "2.00"},
        ],
    }
    fake = FakeClient(response=payload)
    original = BAL.DeepSeekClient
    BAL.DeepSeekClient = fake
    try:
        result = BAL.DeepSeekBalanceNode.execute(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            currency="USD",
        )
    finally:
        BAL.DeepSeekClient = original

    assert "不可用" in result.results[0]
    assert "USD 3.00" in result.results[0]
    assert json.loads(result.results[1])["is_available"] is False


# ------------------------------------------------------------------ i18n 测试
I18N_STEMS = [
    ("DeepSeekAPI_Model", NS.DeepSeekModelNode),
    ("DeepSeekAPI_Search", SEARCH.DeepSeekSearchNode),
    ("DeepSeekAPI_Balance", BAL.DeepSeekBalanceNode),
]


def _load_locale(lang):
    path = PKG_DIR / "locales" / lang / "nodeDefs.json"
    assert path.exists(), "missing locale file: %s" % path
    return json.loads(path.read_text(encoding="utf-8"))


@test
def test_locale_files_cover_every_slot():
    zh = _load_locale("zh")
    en = _load_locale("en")
    for node_id, node_cls in I18N_STEMS:
        for lang, data in (("zh", zh), ("en", en)):
            assert node_id in data, "%s missing in %s" % (node_id, lang)
            entry = data[node_id]
            assert entry.get("display_name"), "%s display_name empty (%s)" % (node_id, lang)
            assert entry.get("description"), "%s description empty (%s)" % (node_id, lang)
            schema = node_cls.define_schema().kwargs
            for item in schema["inputs"]:
                ident = item.get("id")
                if not ident:
                    continue
                tooltip = entry.get("inputs", {}).get(ident, {}).get("tooltip")
                assert tooltip, "%s.%s tooltip missing (%s)" % (node_id, ident, lang)
            for index, item in enumerate(schema["outputs"]):
                tooltip = entry.get("outputs", {}).get(str(index), {}).get("tooltip")
                assert tooltip, "%s output %d tooltip missing (%s)" % (node_id, index, lang)


@test
def test_source_strings_stay_monolingual():
    for node_id, node_cls in I18N_STEMS:
        schema = node_cls.define_schema().kwargs
        assert "\n" not in schema["display_name"], node_id
        assert "\n" not in schema["description"], node_id
        for item in schema["inputs"]:
            tooltip = item.get("tooltip")
            if tooltip:
                assert "\n" not in tooltip, "%s.%s still bilingual" % (node_id, item.get("id"))
        for index, item in enumerate(schema["outputs"]):
            tooltip = item.get("tooltip")
            if tooltip:
                assert "\n" not in tooltip, "%s output %d still bilingual" % (node_id, index)



@test
def test_advanced_inputs_are_collapsed():
    model = NS.DeepSeekModelNode.define_schema().kwargs
    search = SEARCH.DeepSeekSearchNode.define_schema().kwargs

    def ids(schema, advanced):
        return [item["id"] for item in schema["inputs"] if bool(item.get("advanced")) is advanced]

    assert ids(model, False) == [
        "user_prompt",
        "system_prompt",
        "model",
        "thinking",
        "web_search",
        "read_url",
        "api_key",
        "base_url",
        "image_slots",
    ]
    assert ids(search, False) == [
        "question",
        "query",
        "after",
        "lang",
        "count",
        "need_content",
        "api_key",
        "base_url",
    ]
    assert len(ids(model, True)) == 6
    assert len(ids(search, True)) == 6



@test
def test_locale_slot_names_match_ids():
    for lang in ("zh", "en"):
        path = PKG_DIR / "locales" / lang / "nodeDefs.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for node_id, entry in data.items():
            for key, value in entry.get("inputs", {}).items():
                assert value.get("name") == key, "%s/%s: name=%r key=%r" % (
                    lang,
                    node_id,
                    value.get("name"),
                    key,
                )


@test
def test_example_workflow_matches_schema():
    path = PKG_DIR / "example_workflows" / "Comfy-DeepSeek-API.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "DeepSeekAPI_Model": NS.DeepSeekModelNode.define_schema().kwargs,
        "DeepSeekAPI_Search": SEARCH.DeepSeekSearchNode.define_schema().kwargs,
        "DeepSeekAPI_Balance": BAL.DeepSeekBalanceNode.define_schema().kwargs,
    }
    checked = 0
    for node in data["nodes"]:
        schema = expected.get(node["type"])
        if schema is None:
            continue
        checked += 1
        ids = [item["id"] for item in schema["inputs"]]
        assert [item["name"] for item in node["inputs"]] == ids, node["type"]
        socket_types = ("IMAGE", "COMFY_AUTOGROW_V3")
        widget_count = sum(
            1 for item in schema["inputs"] if item.get("type") not in socket_types
        )
        assert len(node["widgets_values"]) == widget_count, "%s widgets" % node["type"]
        assert set(node["widgets_values_named"]) == {
            item["id"] for item in schema["inputs"] if item.get("type") not in socket_types
        }, node["type"]
    assert checked == 3



@test
def test_locale_inputs_follow_schema_order():
    expected = {
        "DeepSeekAPI_Model": NS.DeepSeekModelNode.define_schema().kwargs,
        "DeepSeekAPI_Search": SEARCH.DeepSeekSearchNode.define_schema().kwargs,
        "DeepSeekAPI_Balance": BAL.DeepSeekBalanceNode.define_schema().kwargs,
    }
    for lang in ("zh", "en"):
        data = json.loads((PKG_DIR / "locales" / lang / "nodeDefs.json").read_text(encoding="utf-8"))
        assert list(data) == list(expected), "%s: node order" % lang
        for node_id, schema in expected.items():
            ids = [item["id"] for item in schema["inputs"]]
            keys = list(data[node_id].get("inputs", {}))
            assert keys == ids, "%s/%s: %s != %s" % (lang, node_id, keys, ids)



def main():
    failures = []
    for func in TESTS:
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            failures.append((func.__name__, exc))
            print("FAIL %s: %s" % (func.__name__, exc))
        else:
            print("ok   %s" % func.__name__)
    print("\n%d passed, %d failed" % (len(TESTS) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

