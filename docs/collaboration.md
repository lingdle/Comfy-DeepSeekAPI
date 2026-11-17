# 协作方式

> 这份文档写给接手本仓库的开发者/Agent：怎么改、怎么验、怎么交付。
> 具体做什么由维护者提需求，这里不预设功能。

---

## 1. 仓库结构

| 路径 | 内容 |
|---|---|
| nodes.py / nodes_search.py / nodes_balance.py / nodes_svg.py | 四个节点的 V3 schema 与 execute |
| core/ | HTTP 客户端、配置解析、错误映射、定价、图像编码、搜索语法拼装 |
| locales/zh, locales/en | nodeDefs.json：节点标题、描述、输入 tooltip 的本地化 |
| example/workflows/ | 示例工作流（json）+ 同名缩略图（jpg） |
| example/cases/ | 案例：配合节点使用的提示词与说明（ASCII 文件名） |
| assets/ | 图标、横幅、赞助码 |
| tests/run_tests.py | 单元测试（桩件模拟 ComfyUI，不联网） |
| tools/ | 开发工具：审计、示例校验、打包、API 兜底推送 |
| docs/ | 本文件 |

发布到 Registry 的 zip 会排除 tests/、tools/、docs/、.github/、dist/、.ruff_cache/、AGENTS.md（见 .comfyignore / tools/build_zip.py）。

---

## 2. 工具集

都在仓库根目录执行，纯标准库，不需要 ComfyUI：

| 命令 | 作用 | 什么时候用 |
|---|---|---|
| python3 tests/run_tests.py | 单元测试（含 schema 顺序、i18n 覆盖、折叠集合、示例一致性） | 每次改完代码 |
| python3 tools/audit.py | 版本 / 多语言 / 示例 与 schema 的一致性审计 | 每次交付前 |
| python3 tools/validate_example.py | 示例工作流结构：节点 id、link 双向、控件数量 | 改过示例或字段顺序后 |
| python3 tools/build_zip.py | 打包到 dist/Comfy-DeepSeekAPI-v版本.zip | 准备发布时 |
| python3 tools/push_via_api.py | github.com 的 git 端口不通时，用 REST API 提交 | 网络异常时兜底 |

判断网络：curl -m 8 https://github.com；不通再走 API 兜底，并先看看 api.github.com 是否正常。

---

## 3. 开发流程

1. **先读代码**，确认现状和影响面，不凭记忆改。
2. **改最小必要范围**，保持现有风格。
3. 跑 tests/run_tests.py，必须全绿；有新增逻辑就补测试。
4. 跑 tools/audit.py 与 tools/validate_example.py，必须无问题。
5. 版本号递增（pyproject.toml 与 __init__.py 同步），更新 CHANGELOG。
6. 打包、提交、推送；推送后回读远端内容确认。

---

## 4. 全链路同步清单

一处定义会被多个衍生文件引用。改字段名、顺序、默认值时，按顺序全部确认：

1. 节点源码：nodes*.py（字段定义、默认值、tooltip、advanced 标记）
2. locales/zh/nodeDefs.json 与 locales/en/nodeDefs.json（键名、name、tooltip、顺序）
3. example/workflows/*.json（inputs 顺序、widgets_values、widgets_values_named；**换位置还要重算 links 的目标槽位**）
4. tests/run_tests.py（顺序、默认值、折叠集合、载荷断言）
5. README.md（只有入口或步骤变化时才改）
6. 版本与 CHANGELOG

tools/audit.py 与测试会拦截其中大部分遗漏，但不要依赖它们兜底。

---

## 5. 技术约定

### 5.1 节点 API

- 只用 V3 schema：io.ComfyNode + define_schema + classmethod execute + comfy_entrypoint。
- 不要同时导出 NODE_CLASS_MAPPINGS：加载器是 if/elif，V1 会覆盖 V3。
- 输出 io.NodeOutput(...)，用 try/except TypeError 兜底不支持 ui 参数的旧版本。

### 5.2 面板字段

- 输入顺序就是面板顺序；新输入优先追加末尾。
- 不常用参数用 advanced=True 收进折叠区。
- 可见字段集合由测试锁定，调整时必须同步测试。

### 5.3 国际化

- 源码里只放中文；英文放 locales/en，中文放 locales/zh。
- locales 的输入项必须满足 name 等于输入 id（曾因漏改导致面板显示旧字段名）。
- placeholder 不受 i18n 支持，保持"中文 / English"双写。
- 前端解析优先级：locales > 后端值 > 内置快照。

### 5.4 默认值

省钱、快、开箱可用：deepseek-flash、thinking=close、max_tokens=1024、图片长边 1024、搜索 count=5、lang=zh,en。

### 5.5 兼容与版本

- 改变控件顺序会让旧工作流失效，交付时必须提示"删掉旧节点重拖"。
- Registry 版本不可变：已发布的版本号不能复用，每次发布都要递增。
- 版本号三处保持一致：pyproject.toml、__init__.py、CHANGELOG 首行。

---

## 6. 交付格式

固定四段，缺一不可：

    ## 改了什么
    | 项 | 旧 | 新 |

    ## 连带同步
    | 文件 | 处理 |

    ## 核对
    - 测试结果（数量 + 通过/失败）
    - 审计与示例校验结果
    - 远端内容回读确认

    ## 你这边
    需要执行的命令 + 是否重启/重装 + 不兼容提醒

只写"已完成/已推送"不算交付。

---

## 7. 沟通习惯

| 项 | 要求 |
|---|---|
| 语言 | 中文，技术名词保留英文 |
| 结构 | 先结论后细节，表格优先 |
| 长度 | 能三行说清不写十行；不复述需求、不写过程叙事 |
| 命令 | 给可直接粘贴的完整命令，路径写全 |
| 不确定 | 一次问清，给 2-3 个选项并标推荐项 |
| 出错 | 先说根因，再说修复，不甩锅给环境 |

---

## 8. 常见错误（前车之鉴）

| 错误 | 后果 | 对策 |
|---|---|---|
| 改名只改键、没改 name 字段 | 面板标签仍是旧字段名 | 改完 grep 全仓库，audit 会拦 |
| 示例工作流没重建 | 控件错位、连线指错槽 | 用 tools/validate_example.py 校验 |
| 只看命令返回成功就交付 | 用户拿到的是坏版本 | 回读远端内容，按四段格式报告 |
| 擅自裁剪/压缩用户素材 | 需要返工 | 改素材前先确认 |
| 加用户没要求的功能 | 被打回重做 | 严格按需求范围 |
| 发布前没 git pull | 报版本已存在 | 发布前先拉最新 |

