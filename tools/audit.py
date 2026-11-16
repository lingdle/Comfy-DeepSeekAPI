"""一致性审计：版本 / 多语言 / 示例工作流 与 schema 是否同步。

用法：python3 tools/audit.py
不依赖 ComfyUI，纯标准库。任何不一致都会返回非 0。
"""

import json
import re
import sys

from schema_utils import package_version, parse_schemas, repo_root


def check_versions(root, issues):
    version = package_version(root)
    init_text = (root / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'__version__ = "([^"]+)"', init_text)
    init_version = init_match.group(1) if init_match else ""

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    log_match = re.search(r"当前版本：\*\*([^*]+)\*\*", changelog)
    log_version = log_match.group(1) if log_match else ""

    if not (version == init_version == log_version):
        issues.append(
            "版本不一致: pyproject=%s __init__=%s CHANGELOG=%s"
            % (version, init_version, log_version)
        )
    return version


def check_locales(root, schemas, issues):
    for lang in ("zh", "en"):
        path = root / "locales" / lang / "nodeDefs.json"
        if not path.exists():
            issues.append("缺少 locales/%s/nodeDefs.json" % lang)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if list(data) != list(schemas):
            issues.append(
                "locales/%s 节点集合或顺序不一致: %s != %s"
                % (lang, list(data), list(schemas))
            )
        for node_id, spec in schemas.items():
            entry = data.get(node_id)
            if entry is None:
                issues.append("locales/%s 缺少节点 %s" % (lang, node_id))
                continue
            if not entry.get("display_name"):
                issues.append("locales/%s %s 缺 display_name" % (lang, node_id))
            if not entry.get("description"):
                issues.append("locales/%s %s 缺 description" % (lang, node_id))
            ids = [item["id"] for item in spec["inputs"]]
            keys = list(entry.get("inputs", {}))
            if keys != ids:
                issues.append(
                    "locales/%s %s 输入顺序/集合不一致: %s != %s"
                    % (lang, node_id, keys, ids)
                )
            for key, value in entry.get("inputs", {}).items():
                if value.get("name") != key:
                    issues.append(
                        "locales/%s %s.%s 的 name=%r，应为 %r"
                        % (lang, node_id, key, value.get("name"), key)
                    )
                if not value.get("tooltip"):
                    issues.append("locales/%s %s.%s 缺 tooltip" % (lang, node_id, key))


def check_example(root, schemas, issues):
    path = root / "example" / "workflows"
    files = sorted(path.glob("*.json")) if path.exists() else []
    if not files:
        issues.append("example/workflows 下没有工作流")
        return
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            spec = schemas.get(node.get("type"))
            if spec is None:
                continue
            names = [item.get("name") for item in node.get("inputs", [])]
            ids = [item["id"] for item in spec["inputs"]]
            if names != ids:
                issues.append(
                    "%s 中 %s 的 inputs 顺序不一致: %s != %s"
                    % (file.name, node["type"], names, ids)
                )
            widgets = [item["id"] for item in spec["inputs"] if item["type"] != "IMAGE"]
            values = node.get("widgets_values") or []
            if len(values) != len(widgets):
                issues.append(
                    "%s 中 %s 控件数量 %d != %d"
                    % (file.name, node["type"], len(values), len(widgets))
                )
            named = node.get("widgets_values_named") or {}
            if named and set(named) != set(widgets):
                issues.append(
                    "%s 中 %s widgets_values_named 键不一致" % (file.name, node["type"])
                )


def main():
    root = repo_root()
    schemas = parse_schemas(root)
    issues = []
    version = check_versions(root, issues)
    check_locales(root, schemas, issues)
    check_example(root, schemas, issues)

    print("root:", root)
    print("version:", version)
    print("nodes:", {k: len(v["inputs"]) for k, v in schemas.items()})
    if issues:
        print("\n发现 %d 个问题:" % len(issues))
        for item in issues:
            print(" -", item)
        return 1
    print("\nOK 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
