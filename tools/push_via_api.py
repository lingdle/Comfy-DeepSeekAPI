"""当 github.com 的 git 端口不通时，用 GitHub REST API 提交当前 HEAD 的内容。

用法：
    python3 tools/push_via_api.py                 # 自动取 origin/main..HEAD 的改动文件
    python3 tools/push_via_api.py a.py b.json     # 手动指定文件

要求：仓库里有 origin 远端；~/.git-credentials 存有 PAT，或设置了 GITHUB_TOKEN。

原理：blobs -> tree(base_tree=远端 tree) -> commit -> PATCH ref。
最后校验远端 tree 是否等于本地 HEAD 的 tree，相等即内容零差异。

注意：用 API 提交后本地与远端是"同内容不同 SHA"，网络恢复后执行：
    git fetch origin && git reset --hard origin/main
"""

import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.github.com"


def git(*args):
    return subprocess.check_output(["git"] + list(args), cwd=str(ROOT), text=True).strip()


def remote_slug():
    url = git("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$", url)
    if not match:
        raise SystemExit("无法解析 origin: %s" % url)
    return match.group(1), match.group(2)


def token():
    env = os.environ.get("GITHUB_TOKEN")
    if env:
        return env
    cred = pathlib.Path.home().joinpath(".git-credentials")
    if cred.exists():
        match = re.match(r"https://[^:]+:([^@]+)@github\.com", cred.read_text().strip())
        if match:
            return match.group(1)
    raise SystemExit("找不到 token：设置 GITHUB_TOKEN 或检查 ~/.git-credentials")


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "token %s" % token())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "comfy-deepseekapi-push")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit("%s %s -> %s %s" % (method, path, exc.code, exc.read().decode()[:300]))


def changed_files():
    try:
        out = git("diff", "--name-only", "origin/main..HEAD")
    except subprocess.CalledProcessError:
        out = ""
    return [line for line in out.splitlines() if line.strip()]


def main():
    owner, repo = remote_slug()
    files = sys.argv[1:] or changed_files()
    if not files:
        print("没有待提交的文件（origin/main 与 HEAD 一致）")
        return 1

    head = call("GET", "/repos/%s/%s/git/ref/heads/main" % (owner, repo))["object"]["sha"]
    print("远端 head:", head[:7])

    entries = []
    for rel in files:
        raw = (ROOT / rel).read_bytes()
        blob = call(
            "POST",
            "/repos/%s/%s/git/blobs" % (owner, repo),
            {"content": base64.b64encode(raw).decode(), "encoding": "base64"},
        )
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("  blob", rel, len(raw), "bytes")

    base = call("GET", "/repos/%s/%s/git/commits/%s" % (owner, repo, head))
    tree = call(
        "POST",
        "/repos/%s/%s/git/trees" % (owner, repo),
        {"base_tree": base["tree"]["sha"], "tree": entries},
    )
    local_tree = git("rev-parse", "HEAD^{tree}")
    commit = call(
        "POST",
        "/repos/%s/%s/git/commits" % (owner, repo),
        {
            "message": git("log", "-1", "--pretty=%B"),
            "tree": tree["sha"],
            "parents": [head],
            "author": {"name": "lingdle", "email": "lingdle@users.noreply.github.com"},
        },
    )
    call("PATCH", "/repos/%s/%s/git/refs/heads/main" % (owner, repo), {"sha": commit["sha"], "force": False})

    print("commit:", commit["sha"][:7])
    if tree["sha"] == local_tree:
        print("TREE_MATCH 内容与本地 HEAD 一致")
    else:
        print("TREE_MISMATCH 远端 tree %s != 本地 %s" % (tree["sha"], local_tree))
        return 1
    print("网络恢复后请执行: git fetch origin && git reset --hard origin/main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
