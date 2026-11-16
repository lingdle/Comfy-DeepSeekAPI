"""校验示例工作流结构：节点 id 唯一、连线双向一致、控件数量与 schema 匹配。

用法：python3 tools/validate_example.py
"""

import json
import sys

from schema_utils import parse_schemas, repo_root


def check_file(path, schemas):
    issues = []
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in data.get("nodes", [])}
    if len(nodes) != len(data.get("nodes", [])):
        issues.append("节点 id 重复")

    links = {}
    for link in data.get("links", []):
        if link[0] in links:
            issues.append("link id 重复: %s" % link[0])
        links[link[0]] = link

    for lid, src, src_slot, dst, dst_slot, ltype in data.get("links", []):
        if src not in nodes or dst not in nodes:
            issues.append("link %s 指向不存在的节点" % lid)
            continue
        source = nodes[src]
        target = nodes[dst]
        if src_slot >= len(source.get("outputs", [])):
            issues.append("link %s 源槽越界" % lid)
        else:
            out_type = source["outputs"][src_slot].get("type")
            if out_type != ltype:
                issues.append("link %s 类型与源输出不符" % lid)
        if dst_slot >= len(target.get("inputs", [])):
            issues.append("link %s 目标槽越界" % lid)
        else:
            in_type = target["inputs"][dst_slot].get("type")
            if in_type not in ("*", ltype):
                issues.append(
                    "link %s 类型与目标输入不符（%s vs %s）" % (lid, in_type, ltype)
                )
            if target["inputs"][dst_slot].get("link") != lid:
                issues.append("link %s 未写回目标输入" % lid)

    for node in data.get("nodes", []):
        for index, item in enumerate(node.get("inputs") or []):
            lid = item.get("link")
            if lid is None:
                continue
            link = links.get(lid)
            if link is None:
                issues.append("%s 的输入 %s 指向不存在的 link" % (node["type"], item.get("name")))
            elif link[3] != node["id"] or link[4] != index:
                issues.append("%s 的输入 %s 与 link 记录不一致" % (node["type"], item.get("name")))
        for item in node.get("outputs") or []:
            for lid in item.get("links") or []:
                if lid not in links:
                    issues.append("%s 的输出指向不存在的 link" % node["type"])
                elif links[lid][1] != node["id"]:
                    issues.append("%s 的输出 link %s 起点不符" % (node["type"], lid))

        spec = schemas.get(node.get("type"))
        if spec is None:
            # 内置节点（LoadImage / PreviewAny 等）不在本包的 schema 里，跳过
            continue
        ids = [item["id"] for item in spec["inputs"]]
        names = [item.get("name") for item in node.get("inputs", [])]
        if names != ids:
            issues.append("%s 的 inputs 与 schema 不一致" % node["type"])
        widgets = [item["id"] for item in spec["inputs"] if item["type"] != "IMAGE"]
        if len(node.get("widgets_values") or []) != len(widgets):
            issues.append("%s 的控件数量与 schema 不一致" % node["type"])

    return issues


def main():
    root = repo_root()
    schemas = parse_schemas(root)
    files = sorted((root / "example" / "workflows").glob("*.json"))
    failed = False
    for path in files:
        issues = check_file(path, schemas)
        if issues:
            failed = True
            print("FAIL", path.name)
            for item in issues:
                print("  -", item)
        else:
            print("OK  ", path.name)
    if not files:
        print("没有找到示例工作流")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
