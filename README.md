# Comfy-DeepSeekAPI

English | [中文](#中文)

## Install

1. Copy the Comfy-DeepSeekAPI folder into ComfyUI/custom_nodes/
2. Set the environment variable DEEPSEEK_API_KEY (create one at https://platform.deepseek.com/api_keys)
3. Restart ComfyUI

![Adding DEEPSEEK_API_KEY in the instance's environment variables](assets/setup-env.png)

Requires ComfyUI v0.4.0+ (V3 nodes, comfy_api.latest, with io.Autogrow).

Node titles, descriptions and tooltips follow ComfyUI's interface language (English / 中文).

## Usage

Three nodes under Add Node → DeepSeekAPI:

| Node | What it does | Outputs |
|---|---|---|
| DeepSeek Model API | Chat + image understanding (multi-slot image_slots or images batch, max_images caps how many are sent) + optional web tools | text / sources / json |
| DeepSeek Search API | Web search; the query syntax is built from the filter widgets | text / json |
| DeepSeek Balance API | Account balance | text / json |

Defaults favor cost and latency (thinking off, low detail, 5 images), but output length is not throttled: max_tokens defaults to the API ceiling 384K (393216). Images are sent at their original size — only images with a side over 4096 px are downscaled, and the API resizes large images to ~1300×1300 anyway.

Both image inputs can be used at once: click + on 多图插槽 (image_slots) to add slots, and/or feed a batch into images. Slots are sent first, everything is merged into one request and capped at max_images.

## Example

![Comfy-DeepSeek-API workflow](example_workflows/Comfy-DeepSeek-API.jpg)

Workflow file: [example_workflows/Comfy-DeepSeek-API.json](example_workflows/Comfy-DeepSeek-API.json)

Open it from Workflow → Browse Templates, or drag the JSON file onto the canvas.

## Sponsor

If this plugin saves you time, buy me a coffee ☕

| Alipay | WeChat Pay |
|---|---|
| ![Alipay QR code](assets/donate-alipay.jpg) | ![WeChat Pay QR code](assets/donate-wechat.jpg) |

Special thanks to **DeepSeek** for the stable and easy-to-use API.

---

## 中文

### 安装

1. 把 Comfy-DeepSeekAPI 文件夹放进 ComfyUI/custom_nodes/
2. 设置环境变量 DEEPSEEK_API_KEY（在 https://platform.deepseek.com/api_keys 创建）
3. 重启 ComfyUI

![在实例的环境变量中添加 DEEPSEEK_API_KEY](assets/setup-env.png)

需要 ComfyUI v0.4.0 及以上（V3 节点，comfy_api.latest，含 io.Autogrow）。

节点标题、描述与 tooltip 跟随 ComfyUI 的界面语言（中文 / English）。

### 使用

三个节点，都在 Add Node → DeepSeekAPI 下：

| 节点 | 作用 | 输出 |
|---|---|---|
| DeepSeek 模型 API | 文本对话 + 图片识别（多图插槽 image_slots 或 images batch，张数由 max_images 控制）+ 可选联网 | text / sources / json |
| DeepSeek 搜索 API | 网页搜索，语法由筛选控件自动拼 | text / json |
| DeepSeek 额度 API | 查询账户余额 | text / json |

默认参数偏省钱、快（思考关闭、低精度、默认发 5 张），但**不限制输出长度**：max_tokens 默认取接口上限 384K（393216）。图片按原尺寸发送，只有长边超过 4096 px 才兜底缩小；服务端本来就会把大图缩到约 1300×1300。

两路图片可同时用：在「多图插槽」点 + 加插槽，和/或给 images 接一个 batch；插槽里的图排在前面，合并成一次请求，总张数受 max_images 限制。

### 示例

![Comfy-DeepSeek-API 工作流](example_workflows/Comfy-DeepSeek-API.jpg)

工作流文件：[example_workflows/Comfy-DeepSeek-API.json](example_workflows/Comfy-DeepSeek-API.json)

可从 Workflow → Browse Templates 打开，或直接把 JSON 拖进画布。

### 支持这个项目

如果它帮你省了时间，欢迎请我喝杯咖啡 ☕

| 支付宝 | 微信支付 |
|---|---|
| ![支付宝收款码](assets/donate-alipay.jpg) | ![微信收款码](assets/donate-wechat.jpg) |

特别鸣谢 **DeepSeek** 提供稳定、好用的 API 服务。

