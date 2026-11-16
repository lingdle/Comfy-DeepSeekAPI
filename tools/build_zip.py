"""打包成 Comfy Registry 可用的 zip。

用法：python3 tools/build_zip.py [输出目录]
默认输出到 <root>/dist/Comfy-DeepSeekAPI-v<版本>.zip，顶层目录为 Comfy-DeepSeekAPI/。
不依赖 ComfyUI。
"""

import sys
import zipfile
from pathlib import Path

from schema_utils import package_version, repo_root

EXCLUDE_DIRS = {"__pycache__", ".git", ".ruff_cache", "tests", "tools", "docs", "dist", ".github", ".vscode"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".zip"}
EXCLUDE_FILES = {"AGENTS.md"}


def main():
    root = repo_root()
    version = package_version(root)
    out_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("Comfy-DeepSeekAPI-v%s.zip" % version)

    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix in EXCLUDE_SUFFIX:
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if path == out:
            continue
        files.append(path)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = Path("Comfy-DeepSeekAPI") / path.relative_to(root)
            zf.write(path, arcname.as_posix())

    print("version:", version)
    print("zip:", out)
    print("size: %.1f KB" % (out.stat().st_size / 1024.0))
    print("files:", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
