"""读取节点 schema 的公共工具（纯标准库，不需要 ComfyUI）。

节点源码里的 NODE_ID / define_schema 结构由 AST 解析，供 audit.py、
validate_example.py、build_zip.py 复用。
"""

import ast
import re
from pathlib import Path

NODE_FILES = ("nodes.py", "nodes_search.py", "nodes_balance.py", "nodes_svg.py")

TYPE_MAP = {
    "String": "STRING",
    "Int": "INT",
    "Float": "FLOAT",
    "Boolean": "BOOLEAN",
    "Combo": "COMBO",
    "Image": "IMAGE",
    # autogrow 组在 schema 里是一个插槽集合，不算控件，按 socket 处理
    "Autogrow": "IMAGE",
}


def repo_root() -> Path:
    """本文件位于 <root>/tools/schema_utils.py。"""
    return Path(__file__).resolve().parents[1]


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _schema_call(class_def):
    for item in class_def.body:
        if isinstance(item, ast.FunctionDef) and item.name == "define_schema":
            for sub in ast.walk(item):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "Schema"
                ):
                    return sub
    return None


def parse_schemas(root: Path):
    """返回 {node_id: {...}}，保持源码中的节点顺序。"""
    schemas = {}
    for filename in NODE_FILES:
        path = root / filename
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        match = re.search(r'^NODE_ID = "([^"]+)"', source, re.M)
        node_id = match.group(1) if match else filename
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            call = _schema_call(node)
            if call is None:
                continue
            kwargs = {kw.arg: kw.value for kw in call.keywords}
            inputs = []
            if "inputs" in kwargs and isinstance(kwargs["inputs"], ast.List):
                for item in kwargs["inputs"].elts:
                    if not isinstance(item, ast.Call):
                        continue
                    ident = _const(item.args[0]) if item.args else None
                    if not ident:
                        continue
                    kind = item.func.value.attr if isinstance(item.func, ast.Attribute) else ""
                    advanced = False
                    default = None
                    for kw in item.keywords:
                        if kw.arg == "advanced" and isinstance(kw.value, ast.Constant):
                            advanced = bool(kw.value.value)
                        if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                            default = kw.value.value
                    inputs.append(
                        {
                            "id": ident,
                            "type": TYPE_MAP.get(kind, kind.upper()),
                            "advanced": advanced,
                            "default": default,
                        }
                    )
            outputs = []
            if "outputs" in kwargs and isinstance(kwargs["outputs"], ast.List):
                for item in kwargs["outputs"].elts:
                    if not isinstance(item, ast.Call):
                        continue
                    display = ""
                    for kw in item.keywords:
                        if kw.arg == "display_name":
                            display = _const(kw.value) or ""
                    outputs.append(display)
            schemas[node_id] = {
                "file": filename,
                "class": node.name,
                "display_name": _const(kwargs.get("display_name")) if "display_name" in kwargs else "",
                "description": _const(kwargs.get("description")) if "description" in kwargs else "",
                "inputs": inputs,
                "outputs": outputs,
            }
    return schemas


def package_version(root: Path):
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.M)
    return match.group(1) if match else ""


def load_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))
