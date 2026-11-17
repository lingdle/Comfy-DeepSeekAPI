"""图层合成的数据层：布局解析、默认布局、指纹、图层规整。

不依赖 torch/numpy，纯标准库，便于单元测试。
"""

import hashlib
import json
import re

LAYOUT_VERSION = 2
MAX_CANVAS = 8192
MAX_LAYERS = 8


_SLOT_INDEX = re.compile(r"(\d+)$")


def sorted_slots(mapping):
    """autogrow 输入是 {"image_0": tensor, ...}；按数字顺序取出非空值。"""
    if not isinstance(mapping, dict):
        return []

    def key(name):
        match = _SLOT_INDEX.search(str(name))
        if match:
            return (0, int(match.group(1)), str(name))
        return (1, 0, str(name))

    return [mapping[name] for name in sorted(mapping, key=key) if mapping[name] is not None]


def parse_layout(text):
    """把 layout_json 解析成 dict；坏数据统一返回 None（当空布局处理）。"""
    if not text or not str(text).strip():
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("layers"), list):
        return None
    return data


def canvas_of(layout, fallback=None, limit=MAX_CANVAS):
    """从存档/参数取画布尺寸，收敛到 [1, MAX_CANVAS]。"""
    width = height = 0
    if isinstance(layout, dict):
        canvas = layout.get("canvas") or {}
        try:
            width = int(canvas.get("width") or 0)
            height = int(canvas.get("height") or 0)
        except (TypeError, ValueError):
            width = height = 0
    if width <= 0 or height <= 0:
        width, height = fallback or (0, 0)
    if width <= 0 or height <= 0:
        width, height = 1024, 1024
    return (
        max(1, min(int(width), limit)),
        max(1, min(int(height), limit)),
    )


def fingerprint(entries):
    """entries: [(index, height, width, digest)]，返回 16 位十六进制。

    指纹同时包含张数与每张图的内容摘要，换图（即使尺寸相同）也会失效。
    """
    payload = "|".join(
        "%d:%dx%d:%s" % (index, height, width, digest)
        for index, height, width, digest in entries
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _contain(size, canvas):
    """等比 contain 到画布内的显示尺寸与居中位置。"""
    width, height = size
    canvas_w, canvas_h = canvas
    if width <= 0 or height <= 0:
        return 0, 0, canvas_w, canvas_h
    scale = min(float(canvas_w) / width, float(canvas_h) / height)
    disp_w = max(1, int(round(width * scale)))
    disp_h = max(1, int(round(height * scale)))
    return (canvas_w - disp_w) // 2, (canvas_h - disp_h) // 2, disp_w, disp_h


def default_layout(sizes, canvas=None, names=None):
    """无存档/存档失效时的默认布局：每层 contain 居中，按索引叠放。"""
    sizes = list(sizes or [])
    if not sizes:
        return None
    canvas_w, canvas_h = canvas_of(None, canvas or sizes[0])
    layers = []
    for index, size in enumerate(sizes):
        x, y, width, height = _contain(size, (canvas_w, canvas_h))
        layers.append(
            {
                "id": "image_%d" % index,
                "index": index,
                "name": (names[index] if names else "图层 %d" % (index + 1)),
                "x": x,
                "y": y,
                "z": index,
                "w": width,
                "h": height,
                "rotation": 0.0,
                "opacity": 1.0,
                "visible": True,
                "keep_aspect": True,
                "flip_h": False,
                "flip_v": False,
            }
        )
    return {
        "version": LAYOUT_VERSION,
        "canvas": {"width": canvas_w, "height": canvas_h},
        "locked": True,
        "fingerprint": "",
        "layers": layers,
    }


def _number(value, fallback, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:  # NaN
        return fallback
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def layout_layers(layout, sizes):
    """把存档规整成可直接渲染的图层列表（按 z 升序，只保留有输入的图层）。

    返回 (layers, ok)：ok=False 表示存档与当前输入不匹配，调用方应回退默认布局。
    """
    stored = (layout or {}).get("layers") or []
    if len(stored) != len(sizes):
        return [], False

    layers = []
    for position, item in enumerate(stored):
        if not isinstance(item, dict):
            return [], False
        width = int(_number(item.get("w"), 0, 1))
        height = int(_number(item.get("h"), 0, 1))
        if width <= 0 or height <= 0:
            return [], False
        index = int(_number(item.get("index"), position, 0, len(sizes) - 1))
        layers.append(
            {
                "index": index,
                "z": int(_number(item.get("z"), position, 0, 9999)),
                "x": int(_number(item.get("x"), 0)),
                "y": int(_number(item.get("y"), 0)),
                "w": width,
                "h": height,
                "rotation": _number(item.get("rotation"), 0.0) % 360.0,
                "opacity": _number(item.get("opacity"), 1.0, 0.0, 1.0),
                "visible": bool(item.get("visible", True)),
                "flip_h": bool(item.get("flip_h", False)),
                "flip_v": bool(item.get("flip_v", False)),
            }
        )
    layers.sort(key=lambda layer: layer["z"])
    return layers, True


def layout_payload(layers, canvas, fp, locked=True):
    """把当前图层写回存档结构（前端保存/后端输出共用）。"""
    width, height = canvas
    return {
        "version": LAYOUT_VERSION,
        "canvas": {"width": int(width), "height": int(height)},
        "locked": bool(locked),
        "fingerprint": fp,
        "layers": [
            {
                "id": "image_%d" % layer.get("index", position),
                "index": layer.get("index", position),
                "name": layer.get("name") or "图层 %d" % (layer.get("index", position) + 1),
                "x": layer.get("x", 0),
                "y": layer.get("y", 0),
                "z": layer.get("z", position),
                "w": layer.get("w", 1),
                "h": layer.get("h", 1),
                "rotation": layer.get("rotation", 0.0),
                "opacity": layer.get("opacity", 1.0),
                "visible": layer.get("visible", True),
                "keep_aspect": layer.get("keep_aspect", True),
                "flip_h": layer.get("flip_h", False),
                "flip_v": layer.get("flip_v", False),
            }
            for position, layer in enumerate(layers)
        ],
    }
