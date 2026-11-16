# AGENTS

本仓库是 ComfyUI 自定义节点包 Comfy-DeepSeekAPI（封装 DeepSeek API：模型 / 搜索 / 额度）。

**动手前先读 [docs/collaboration.md](docs/collaboration.md)（协作方式）**：开发约定、工具用法、交付格式、沟通习惯都在里面。

常用命令（在仓库根目录执行）：

    python3 tests/run_tests.py          # 单元测试，必须全绿
    python3 tools/audit.py              # 版本 / 多语言 / 示例 与 schema 一致性
    python3 tools/validate_example.py   # 示例工作流结构校验
    python3 tools/build_zip.py          # 打包到 dist/

发布由维护者执行（comfy node publish），发布前必须递增 pyproject 与 __init__ 的版本号。
