# 开发任务书：RGBA 图层编辑器节点（ComfyUI 自定义节点）

> 交付给开发 agent 的完整规格。目标：做一个自带 2D 画布编辑器的合成节点，交互布局对齐 ComfyUI 内置「创建分层图像 / 打开合成器」，但**代码全部自研，不复制 ComfyUI 前端源码**（其许可证为 GPL-3.0，且画布依赖 WebGL/three.js，不适合抄）。

- 目标环境：ComfyUI **0.45.3**，Windows，Python 3.13，PyTorch 2.12 + CUDA
- ComfyUI 安装目录：`D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`
- 输入目录：`D:\Comfy-Desktop\ComfyUI-Shared\input`；输出：`…\ComfyUI-Shared\output`
- 技术栈：后端 Python（torch + PIL）；前端原生 TS（Canvas2D + DOM），**不要引 Vue / three.js**

---

## 1. 用户故事

> 我做一张演播室合成图，有背景、主播、标字板三张带透明的 PNG。我想在 ComfyUI 里把它们连进一个节点，点一下「打开编辑器」，在一块画布上拖来拖去、拉大小，摆好后锁定，节点直接合并输出一张 RGBA 图。

## 2. 范围

### MVP（本次必须完成）

| # | 功能 |
|---|---|
| R1 | 节点接收 N 个 IMAGE 输入（先支持 8 路，全部可选） |
| R2 | 支持 4 通道 IMAGE（第 4 通道当 alpha）；3 通道按不透明处理 |
| R3 | 执行后在节点上渲染缩略图 +「打开编辑器」按钮 |
| R4 | 全屏编辑器：左栏图层列表、中间画布、右栏当前图层属性 |
| R5 | 画布内**拖拽移动**选中图层 |
| R6 | 八个控制点缩放，**默认锁定比例**（Shift 临时解锁） |
| R7 | 右栏可数字输入 X / Y / W / H、不透明度、显隐 |
| R8 |「锁定」= 退出编辑态，布局冻结 |
| R9 | 关闭编辑器自动把布局写回节点 widget |
| R10 | 再执行 → 按布局合成，输出 **IMAGE(4 通道) + MASK** |
| R11 | 上游输入变化 → 布局指纹失效 → 回退默认布局，不崩 |

### 明确不做（P2 以后）

旋转手柄、混合模式（先只做 normal）、对齐吸附、撤销重做、多选、图层重排、PSD 导出、autogrow 动态输入。

---

## 3. 节点接口

### 3.1 标识

- `class_type` / `NODE_CLASS_MAPPINGS` 键：`RGBACompositorNode`
- 显示名：`RGBA 图层合成`
- 分类：`image/compositing`

### 3.2 输入

| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `image_0` … `image_7` | IMAGE | 否 | — | 按索引从底到顶；允许中间空缺（空缺跳过） |
| `canvas_width` | INT | 是 | 0 | 0 = 用 `layout.canvas`，再没有就用第一张图的尺寸 |
| `canvas_height` | INT | 是 | 0 | 同上 |
| `layout_json` | STRING | 是 | 空串 | 布局存档（JSON 字符串），前端会把它藏起来不显示 |

> 8 路固定输入是为了避开 autogrow 的序列化坑（见 §9）。后续要动态路数，再换 V3 `io.Schema` + `COMFY_AUTOGROW_V3`，接口形状不变。

### 3.3 输出

| 名称 | 类型 | 说明 |
|---|---|---|
| `image` | IMAGE | **4 通道**（RGB + alpha），可直接接 `SplitImageWithAlpha` / `保存图像` |
| `mask` | MASK | 整幅画布的合成 alpha |

### 3.4 执行结果里回传的 UI 数据（编辑器靠它取图）

```python
return {
    "ui": {
        "layers": [{"filename": "rgba_layer_0_00001_.png", "subfolder": "", "type": "temp"}],
        "fingerprint": "<sha1>",
        "canvas": [2048, 1153],
        "stale": [False],
    },
    "result": (image_4ch, mask),
}
```

- 每层原图要**单独存一份带 alpha 的 PNG**到 `temp/`（3 通道的也转成 RGBA 存），供前端画布显示
- `stale` 为真时，前端提示「输入已变化，布局已回退」

---

## 4. 数据模型（`layout_json` 的内容）

```json
{
  "version": 1,
  "canvas": { "width": 2048, "height": 1153 },
  "locked": true,
  "fingerprint": "sha1:...",
  "layers": [
    {
      "id": "0",
      "name": "图层 1",
      "x": 0, "y": 0,
      "w": 2048, "h": 1153,
      "opacity": 1.0,
      "visible": true,
      "flip_h": false, "flip_v": false,
      "keep_aspect": true
    }
  ]
}
```

规则：

- `layers` 顺序 = 绘制顺序，**索引 0 在最底层**
- 坐标原点在画布左上角、像素单位；允许负数、允许超出画布（超出裁掉）
- `w/h` 是「显示尺寸」，与原图尺寸无关
- `keep_aspect` 是每层的缩放约束，默认 `true`；右栏复选框改它
- `locked` = 用户点了「锁定」
- `fingerprint` 由后端算，前端原样写回

**指纹算法**（后端唯一实现，前端只用返回值）：

```
fp = sha1( "|".join(f"{i}:{h}x{w}" for 每个非空输入，按索引) )
```

执行时：`layout.fingerprint == 当前 fp` → 用存档；否则按默认布局重算，并在 `ui.stale` 置真。

**默认布局**（无存档或过期时）：每层 contain 居中铺满画布，再按索引叠起来。

---

## 5. 后端合成算法

```
out = zeros(canvas_h, canvas_w, 4)
for layer in layers(按索引升序):
    if not visible or opacity <= 0: continue
    src = resize(layer_rgb, (w, h))      # 双线性；缩小 >2 倍时先用 area
    a   = layer_alpha * opacity          # alpha 取自第 4 通道，缺省全 1
    blit(out, src, a, x, y)              # 越界裁剪；逐像素 normal 混合
    out.a = a + out.a * (1 - a)
return out.rgb, out.a
```

要点：

- 用 `torch.nn.functional.interpolate`（`mode='bilinear'`，`align_corners=False`）
- 可选对 alpha 做 3×3 均值羽化，消除抠图硬边
- 全程在 GPU tensor 上做，别来回 numpy
- 输出 alpha 记得 clamp 到 [0,1]

---

## 6. 前端规格

### 6.1 注册与挂载

```ts
app.registerExtension({
  name: "RGBACompositor.Editor",
  async nodeCreated(node) {
    if (node.comfyClass !== "RGBACompositorNode") return;
    hideLayoutWidget(node);
    const el = document.createElement("div");
    node.addDOMWidget("compositor_ui", "preview", el, { serialize: false });
    mountPreview(el, node);
    node._rgbaState = { images: [], fp: null };
    const prev = node.onExecuted;
    node.onExecuted = function (out) { prev?.call(this, out); updateState(node, out); };
  }
});
```

- 隐藏 `layout_json`：找到同名 widget 后设 `widget.computeSize = () => [0, -4]`
- 「打开编辑器」在**没执行过**时置灰，tooltip 文案：「先运行一次以载入图层」（与内置语义一致）

### 6.2 编辑器布局（照搬内置）

```
┌──────────────────────────────────────────────────────────────┐
│ 合成器                                        恢复   关闭  ✕   │
├──────────┬────────────────────────────────────┬──────────────┤
│ 图层      │                                    │ 图层名        │
│ ┌──────┐ │                                    │ 位置  X  Y    │
│ │缩略图 │ │           画布（Canvas2D）          │ 尺寸  W  H    │
│ │图层 1 │ │                                    │ □ 锁定比例    │
│ └──────┘ │                                    │ 对齐 九宫格   │
│ ┌──────┐ │                                    │ 不透明度      │
│ │缩略图 │ │                                    │ 显隐          │
│ │图层 2 │ │                                    │              │
│ └──────┘ │                                    │ [锁定并关闭]  │
├──────────┴────────────────────────────────────┴──────────────┤
│ 选择  平移      65%   −  +  Fit                               │
└──────────────────────────────────────────────────────────────┘
```

- 左栏 220px：每项 = 缩略图 + 名称 + 眼睛图标 + 不透明度百分比；点击选中，选中项高亮
- 右栏 260px：属性表单，数字框支持直接输入与上下步进
- 中间画布自适应，透明区用棋盘格

### 6.3 画布交互

| 操作 | 行为 |
|---|---|
| 点击图层 | 选中（显示 8 个控制点 + 边框） |
| 按住图层拖动 | 移动，实时更新 X/Y |
| 拖角控制点 | 等比缩放（`keep_aspect=true`）；按住 **Shift** 临时解锁 |
| 拖边控制点 | 只改单边（`keep_aspect=true` 时另一维按比例跟随） |
| 滚轮 | 以光标为中心缩放视图（25%~400%） |
| 空格+拖 / 中键拖 | 平移视图 |
| 双击空白 | 取消选中 |
| Esc | 关闭编辑器（等同点关闭，会保存） |

缩放时**以对角为锚点**（拖右下角 → 左上角不动）。`pointerup` 时才写回状态，过程中只改本地。

### 6.4 状态与保存

- 打开时：用 `/view?filename=...&type=temp` 载入各层图，并读已有的 `layout_json`（有就按它摆）
- 编辑过程只改内存状态
- **关闭时**（关闭按钮 / Esc / 锁定并关闭）：写 `layout_json`，再 `node.graph.setDirtyCanvas(true, true)`
- 顶部「恢复」= 丢弃本次改动，回到打开时的状态
- 不做实时自动保存（内置是自动保存；我们取「关闭即保存」，更好实现也更可控）

---

## 7. 目录结构

```
comfy-rgba-compositor/
├── __init__.py          # NODE_CLASS_MAPPINGS + WEB_DIRECTORY = "./web"
├── nodes.py             # RGBACompositorNode（IO 声明 + execute）
├── composite.py         # 合成与缩放算法（纯函数，便于单测）
├── fingerprint.py       # 指纹计算
├── web/main.js          # 前端打包产物（ComfyUI 自动加载）
├── frontend/src/        # TS 源码
│   ├── index.ts         # registerExtension
│   ├── editor.ts        # 全屏编辑器
│   ├── canvas.ts        # 渲染 + 交互
│   └── types.ts
├── tests/test_composite.py
├── tests/test_fingerprint.py
└── example_workflows/rgba_compositor.json
```

`__init__.py` 骨架：

```python
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
```

---

## 8. 验收标准（逐条可测）

1. 拖入 3 张带透明 PNG（2048×1153 / 1671×941 / 2930×2930）→ 节点只出现 3 个已连的 image 口，其余空着不报错
2. 未执行时「打开编辑器」置灰；执行一次后可点，节点上出现合成缩略图
3. 打开编辑器：左栏 3 个图层（顺序与 image_0..2 一致），右栏显示第一个图层属性
4. 拖动第 2 层 → 松手，右栏 X/Y 同步更新
5. 拖右下角 → W/H 同比例变化；按住 Shift 拖 → 只有一边变
6. 关闭编辑器 → `layout_json` 里有合法 JSON，`locked: true`
7. 再运行 → 输出 2048×1153；接 `SplitImageWithAlpha` + `保存图像`，得 RGBA PNG 且 alpha 非全白
8. 换掉 image_1 → 再运行 → 出现「布局已过期」，画面按默认布局重排且不报错
9. 保存工作流 → 重新加载 → 打开编辑器，位置与关闭时一致
10. 后端单测：两图合成与手算一致；越界裁剪不越界；3 通道按不透明处理

---

## 9. 已知坑（务必看）

1. **`IMAGE` 恒为 3 通道**。4 通道是约定俗成（内核 `JoinImageWithAlpha` 产出、`SplitImageWithAlpha` 消费）。读输入时判 `tensor.shape[-1] == 4`，否则 alpha 全 1；输出给 4 通道。
2. **`layout_json` 要能扛住任意字符串**（用户可能手改坏）。解析失败 → 当空布局处理，别抛异常。
3. **别给 widget 取名叫 `compositor`**。内置编辑器按名字找它（`setNodeWidgetValue(node, 'compositor', ...)`），撞名会抢值。用 `layout_json`。
4. **DOM widget 要 `serialize: false`**，否则工作流里会多存一份 DOM 状态。
5. **图片地址**：后端 `ui` 给 `type: "temp"`，前端拼 `/view?filename=...&subfolder=...&type=temp`；别用 output（会被 SaveImage 覆盖）。
6. **热重载**：改 `web/main.js` 刷新页面即可；改 Python 必须重启 ComfyUI。
7. **不要把 ComfyUI_frontend 的源码拷进来**（GPL-3.0）。只照搬布局与交互，代码自己写。

---

## 10. 参考

- 交互与字段基准：ComfyUI 0.45.3 里 `创建分层图像` 节点 → 运行后点「打开合成器」
- 已有第三方实现可参考 DOM widget + canvas 的接法：`ComfyUI_RC_Image_Compositor` 的 `RC Interactive Canvas`
- 官方文档：https://docs.comfy.org/zh/interface/layer-editor
