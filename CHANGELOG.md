# 更新记录

当前版本：**1.0.7**（2026-11-15）

**1.0.7**（2026-11-15）

- 所有节点 tooltip 改为中英双语（输入、输出、节点描述，共 45 条）

**1.0.6**（2026-11-15）

- 收款码更新为最新两张原图（420×560，未裁剪）

**1.0.5**（2026-11-15）

- 收款码换回原图（不再裁剪），两张统一缩放为 420×525，保持原始排版

**1.0.4**（2026-11-15）

- 两个收款码统一裁剪为 600×600 正方形（二维码占画面约 3/4），README 中并排更整齐

**1.0.3**（2026-11-15）

- README：赞助区块改为支付宝 + 微信双收款码并排（中英两份都更新）

**1.0.2**（2026-11-15）

- README：英文部分也加了 Sponsor（收款码 + 鸣谢），中文部分保留「支持这个项目」

**1.0.1**（2026-11-15）

- README 增加「支持 / Sponsor」区块：支付宝收款码 + 请喝咖啡文案
- README 增加对 DeepSeek 的特别鸣谢

**1.0.0**（2026-11-15）

- 首个公开发布版本：模型 API（文本 + 图片 + 联网工具）、搜索 API（结构化语法控件）、额度 API（text + json）
- 附带一个完整示例工作流与缩略图

**0.6.10**（2026-11-15）

- 发布工作流模板放在仓库外的 publish/publish_action.yml（需在 GitHub 网页添加，或给 token 加 workflow 权限）
- .comfyignore 忽略 .github/

**0.6.9**（2026-11-15）

- README 增加示例区块：工作流截图 + JSON 文件链接（中英双语各一份）

**0.6.8**（2026-11-15）

- 示例工作流改为一个完整示例：Comfy-DeepSeek-API.json（模型 / 搜索 / 额度三个节点 + LoadImage + PreviewAny），附同名缩略图 Comfy-DeepSeek-API.jpg
- 删除此前 4 个示例工作流

**0.6.7**（2026-11-15）

- 填入真实仓库地址 https://github.com/lingdle/Comfy-DeepSeekAPI、PublisherId = lingdle、Icon / Banner raw 链接
- assets/ 增加 icon.svg 与 banner.svg

**0.6.6**（2026-11-15）

- 项目更名：ComfyUI-DeepSeekAPI -> Comfy-DeepSeekAPI（目录名、[project].name、DisplayName、README 全部同步）
- 安装包与仓库目录现在叫 Comfy-DeepSeekAPI；registry 安装 id 变为 Comfy-DeepSeekAPI

**0.6.5**（2026-11-15）

- README：英文版移到前面（国际友好），中文版在后

**0.6.4**（2026-11-15）

- README 精简为中英双语极简版：只保留「安装 + 使用」，去掉参数表、FAQ、费用、验收清单等细节
- 移除 README 用的截图资源（assets/）

**0.6.3**（2026-11-15）

- 打包元数据按 Registry 规范修正：license 改为 { file = "LICENSE" }，补 Documentation / Bug Tracker，Icon / Banner 预留注释
- 新增 .gitignore；发布清单与 icon / banner / 工作流模板放到 publish/

**0.6.2**（2026-11-15）

- 模型节点新增第五个输出 **json**：接口原始返回（choices / usage / annotations / server_tool_calls 全字段），与额度节点的 json 输出保持一致

**0.6.1**（2026-11-15）

- 额度节点输出简化为两个：text（一行汇总）+ json（接口原始返回）；不再单独拆 available/total/granted/topped_up/currency

**0.6.0**（2026-11-15）

- 新增第三个节点 **DeepSeek 额度 API**（GET /user/balance）：一行汇总文本 + available / total / granted / topped_up / currency 五个关键字段单独输出，支持 CNY/USD 选择
- client 增加通用 GET 请求与 balance() 方法

**0.5.3**（2026-11-15）

- 文档：README 只保留「安装 + 使用」；目录结构、自测命令、历史版本移到本文件

**0.5.2**（2026-11-15）

- 文档：新增「搜索词怎么填（完整示例）」——5 个真实场景的控件填写方式 + 拼好的 query + 字符数，并说明 128 上限的实际报错
- 代码未变

**0.5.1**（2026-11-15）

- 按官方语法逐条核对并修正：新增 exact_phrases 字段支持多个精确短语（`"a" "b"`）
- 容错：站点/排除词里已经带了 site:、-site:、- 前缀时会自动去掉，避免拼出 site:site: / --词
- 文档新增「与官方语法对照」表（8 个操作符逐条对齐 https://api-docs.deepseek.com/zh-cn/guides/search）

**0.5.0**（2026-11-15）

- 搜索节点把搜索语法拆成控件：site_include / site_exclude / exclude_words / exact_phrase（开关）/ lang / after / before，节点自动拼成 site:、-site:、lang:、after: 等语法，避免手写拼错
- 拼接结果做校验：超 128 字符、日期格式错误都会直接报错并给提示；实际发出的搜索词显示在 usage 里

**0.4.0**（2026-11-15）

- 模型节点新增**联网工具开关**：web_search（deepseek_web_search）与 read_url（deepseek_read_url），默认关闭，仅支持 deepseek-flash
- 模型节点新增第四个输出 **sources**（联网来源「标题 — URL」），usage 里显示联网次数与费用
- 搜索节点 text 输出改为**结构化 Markdown**（标题/统计/每条小标题+字段行），空结果给出改写建议

**0.3.3**（2026-11-14）

- 搜索节点：ori_question（原始问题）与 query（搜索词）移到最上面，并填入可直接运行的示例默认值

**0.3.2**（2026-11-14）

- 模型节点的默认提示词改为图像理解场景：system_prompt = 你是一个图像理解助手，user_prompt = 图片上是什么？

**0.3.1**（2026-11-14）

- 移除 DeepSeek 文本预览节点（多余，且实现有问题）
- 示例工作流改用 ComfyUI 自带的 **Save Text** 节点收尾

**0.3.0**（2026-11-14）

- 新增 4 个示例工作流（example_workflows/）
- 文档：补充 API Key 获取方式（https://platform.deepseek.com/api_keys），错误提示里也带上该链接

**0.2.0**（2026-11-14）

- 新增 **DeepSeek 搜索 API** 节点（POST /v1/tools/search）
- 模型节点：五个 image_1..image_5 输入合并为一个 images（batch 自动展开，按 max_images 截断）
- 模型节点：images 移到 system_prompt / user_prompt 之上

**0.1.0**

- V3 schema 单节点，聚焦 deepseek-flash
- 文本 + 图片、思考模式开关（默认关）
- 用量与费用估算、错误中文提示、429/5xx 自动重试、取消响应
