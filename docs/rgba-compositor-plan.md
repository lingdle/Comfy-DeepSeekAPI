# 方案研究：做一个「RGBA 图层编辑器」自定义节点

> 目标：autogrow 输入 N 张 RGBA 图 → 打开一个像「创建分层图像 / 打开合成器」那样的画布编辑器 → 调位置/大小/旋转/不透明度/混合 → 锁定 → 合并输出一张 RGBA 图。
> 本文只做可行性研究与架构设计，不含实现。

## 0. 结论先说

1. **可行**，而且有现成先例：第三方包 `ComfyUI_RC_Image_Compositor` 的 `RC Interactive Canvas` 就是"节点内嵌画布 + 拖动缩放旋转"。
2. **但内置那个编辑器复用不了。** 它是全局对话框（key = `global-layer-editor`），没有对外的打开 API。我实测了 `app.extensionManager`：31 个 `dialog.showXxx` 方法里没有任何 layer / compositor 入口，`extensionManager.layerEditor` 也是 `undefined`。
3. 所以只有三条路：**A 全自研编辑器** / **B 黑科技逆向调用**（不推荐） / **C 展开式复用内置链**。
4. 建议：**先用 C 验证需求（半天到一天），确认"要的就是这个手感"再投入 A（一周级）**。

---

## 1. 内置那套是怎么工作的（能抄的部分）

### 后端侧

| 节点 | 作用 |
|---|---|
| `AddLayer` | image + mask + 上一层的 `layers` → 新 `LAYERS`（单链，一层一层串） |
| `ImageCompositor`（创建分层图像） | `layers` + `compositor` → IMAGE + MASK |

关键设计：`ImageCompositor` 有一个 **socketless 输入** `compositor`（类型 `COMPOSITOR`，默认 `{}`）。

- 它是**编辑器的存档位**：编辑器把整份构图（每层的 x/y/w/h/旋转/透明度/混合模式/锁定状态、画布尺寸、背景）序列化成 JSON 存进这个 widget
- 执行时：**存档的输入指纹和当前输入匹配 → 直接用存档渲染**；不匹配 → 回退用各 `AddLayer` 的参数渲染，并把存档标记为过期
- 这个"指纹 + 过期回退"机制必须抄，否则用户一改上游就出鬼图

### 前端侧

- 编辑器是一个**全局对话框**，dialog key = `global-layer-editor`（从 `layerEditorDialogKey-*.js` 里读出来的）
- 节点上挂了一个 Vue DOM widget：没跑过时显示「运行工作流以生成合成图像」，跑过之后变成「打开合成器」按钮
- 官方文档明说：**这条路要求工作流至少运行过一次**，因为编辑器展示的图来自**执行结果**，不是直接读上游节点

> 编辑器 = "取出上一次执行得到的各层图像 + 一份 JSON 布局" 的所见即所得界面。

---

## 2. 三条技术路线

### 路线 A：全自研（后端节点 + 前端画布编辑器）

```
[autogrow: image_0..image_n] ──┐
                              ├─→ RGBACompositor ──→ IMAGE(4ch) + MASK
[compositor: {JSON 存档}] ────┘
        ▲
        │ 读写
  [自定义 Vue 画布对话框]
```

- 后端：收 autogrow 的图像 → 按 JSON 布局合成 → 输出 RGBA
- 前端：`app.registerExtension` 注册节点；给节点加按钮 widget；点击用 `dialog.showExtensionDialog` 打开自己的 Vue 画布；Pointer 事件做拖动/缩放/旋转；确认后把 JSON 写回 `compositor` widget
- 像素从哪来：节点执行时把每层 PNG 存到 `temp/`，通过 `ui` 返回文件列表；前端用 `/view?type=temp` 取图（和 PreviewImage 一个套路）

**工作量**：后端 200~300 行；前端 800~1500 行（画布交互、标尺、对齐吸附、撤销重做）。
**风险**：前端 API 跨版本会变；画布手感要打磨。
**优势**：体验完全可控，能做"锁定/解锁、双击进组、导出 PSD"。

### 路线 B：逆向调用内置编辑器

理论上可以 `import` 那个 chunk，或直接往 dialog store 里塞 `global-layer-editor`。

**不推荐**：chunk 名带 hash（`layerEditorDialogKey-nzJj57es.js`），每次升级 ComfyUI 全变；它内部还假定节点类型是 `ImageCompositor`、输出是 `LAYERS`。等于埋一颗每次升级都响的雷。

### 路线 C：展开式（把内置链当"运行时"用）

一个节点收 autogrow 的 N 张图，然后：

- **C1 运行时展开**：`execute` 里用 `GraphBuilder` 动态生成 N 个 `AddLayer` + 1 个 `ImageCompositor`，复用内置合成逻辑。**但**动态生成的节点不在画布上，用户点不到「打开合成器」。
- **C2 点击展开到画布**：节点上放「展开为图层链」按钮，前端按当前输入个数，在画布上真实创建 N 个 `AddLayer` + 1 个 `ImageCompositor` 并连好线。之后用的就是**原生编辑器和原生节点**。

**C2 的价值**：几乎不写编辑器（省掉 1000 行前端），代价是画布上多出 N+1 个节点（可一键框成子图）。
**工作量**：1 天以内。

---

## 3. 对比

| | A 全自研 | B 逆向复用 | C2 展开到画布 |
|---|---|---|---|
| 用户看到的节点数 | 1 | 1 | N+2（可包成子图） |
| 编辑器手感 | 自己打磨 | 原生 | 原生 |
| 升级兼容性 | 中（前端 API） | **极差** | **好**（只用公开 API） |
| 工作量 | 1~2 周 | 2 天但随时报废 | 半天~1 天 |
| 能否"锁定后合并成一个 RGBA" | ✅ | ✗（受限于内置输出） | ✅（末尾接 `SplitImageWithAlpha` 或自研合并节点） |

---

## 4. 如果走 A，关键设计

### 4.1 RGBA 怎么传（最关键的决策）

ComfyUI 的 `IMAGE` 恒为 3 通道（硬约定）。三个选择：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **4 通道 IMAGE** | 复用 `JoinImageWithAlpha` 的约定，`image[:,:,:,3]` 当 alpha | 和内核 `SplitImageWithAlpha` 互通，零新类型 | 大部分节点会静默丢掉第 4 通道 |
| **自定义类型 `RGBA`** | `{image, mask}` | 语义明确，不会误用 | 只有自己的节点能接，生态外全断 |
| **IMAGE + MASK 双 autogrow** | `images.image_0..n` + `masks.mask_0..n` 按下标配对 | 全用标准类型 | 连线翻倍，容易接错 |

**建议**：主用 **4 通道 IMAGE**（内核既有约定），再加容错：**输入若只有 3 通道就当不透明**。这样既能和现有工作流搭，又不用发明新类型。

### 4.2 autogrow 的坑

- schema 是 `COMFY_AUTOGROW_V3` + `template` + `prefix` + `min/max`，`ComfyMathExpression` 和 Quiver 节点都在用，可用
- **但它序列化进 API prompt 是点号扁平化的**：`values.a`、`inputs.input0`。我们节点收到的是 `{"image_0": [...], "image_1": [...]}` 这种形状，后端要按前缀聚合成有序列表
- 前端 `widgets_values` 里 autogrow 怎么存，要在真机上验一遍（最容易出错的地方）

### 4.3 数据模型（抄内置）

```json
{
  "version": 1,
  "canvas": { "width": 2048, "height": 1153 },
  "locked": true,
  "fingerprint": "<上游输入的 hash>",
  "layers": [
    { "index": 0, "name": "背景", "x": 0, "y": 0, "w": 2048, "h": 1153,
      "rotation": 0, "opacity": 1, "blend": "normal", "visible": true, "locked": false }
  ]
}
```

- `locked`：锁定后编辑器只读，防止误拖
- `fingerprint`：记录"当时输入的张数/尺寸"的 hash，执行时比对，不匹配就回退 + 标记过期
- 混合模式直接对齐内置的 26 种，将来能互相迁移

### 4.4 状态流

```
① 未执行 → 节点显示「先运行一次以载入图层」
② 执行 → 每层 PNG 落到 temp/，ui 返回 [{filename, w, h}, ...]，前端缓存
③ 点「打开编辑器」→ 对话框加载「缓存图像 + compositor JSON」
④ 拖动/缩放 → 只改前端状态（不进 graph）
⑤ 点「锁定并保存」→ 写回 compositor widget（含 locked: true + fingerprint）
⑥ 再执行 → 后端读到 locked 存档 → 按 JSON 合并 → 输出 RGBA
```

### 4.5 输出

- `IMAGE`：4 通道（RGB + alpha），可直接接 `SplitImageWithAlpha`、`保存图像`
- `MASK`：整幅画布的合成 alpha（内置 `ImageCompositor` 也是这么给的）

---

## 5. 已核实 / 待核实

已核实（在你本机 0.45.3 上实测）：

- ✅ `app.extensionManager` 没有 layerEditor / compositor 入口（31 个 dialog 方法里没有）
- ✅ 但存在 `dialog.showExtensionDialog` —— 自研弹窗有官方通道
- ✅ `COMFY_AUTOGROW_V3` 存在，`ComfyMathExpression`、Quiver 节点都在用
- ✅ `IMAGE` 恒 3 通道；`JoinImageWithAlpha` 造 4 通道；`SplitImageWithAlpha` 拆回
- ✅ `ImageCompositor` 的 `compositor` 是 socketless `COMPOSITOR` 输入，默认 `{}`
- ✅ 内置编辑器 dialog key = `global-layer-editor`，且"必须先跑一次"

待核实（真要开工时按顺序验）：

1. autogrow 输入在 `widgets_values` 里的序列化格式（决定保存/加载工作流会不会丢层）
2. `dialog.showExtensionDialog` 的确切签名（能否传自定义 Vue 组件 + props + 回调）
3. 节点内能不能直接放一个 `<canvas>` DOM widget（能的话就省掉整窗弹窗）
4. `ui` 里指向 `temp/` 的图片在前端怎么取（`/view?type=temp` 是否直连）

---

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 前端 API 跨版本变动 | 编辑器突然打不开 | 只用 `registerExtension` + `dialog` + DOM widget 这类稳定面，别碰内部 store |
| autogrow 序列化不稳 | 保存工作流丢层 | 先做"固定 8 个输入"的版本，稳定后再上 autogrow |
| 4 通道 IMAGE 被别的节点截断 | 下游丢透明 | 文档写死"本节点输出要接 `SplitImageWithAlpha` 或保存节点" |
| 画布手感差 | 用户宁愿回 PS | 先抄内置交互（八个控制点、角标旋转、九宫格对齐） |
| 与内置 `ImageCompositor` 重复 | 维护两套 | 长期看，C2 够用就不要做 A |

---

## 7. 建议的推进顺序

1. **今天**：用 C2 思路手工验证 —— 手画 3 个 `AddLayer` + 1 个 `ImageCompositor`，看"跑一次 → 打开合成器 → 拖动 → 锁定"这套流程够不够用
2. **够用** → 只做"autogrow 展开按钮"（半天），不做节点
3. **不够用** → 做 A，第一版**固定 8 个输入**，只做「拖动 + 缩放 + 锁定」
4. autogrow、旋转、混合模式、PSD 导出放第二版

---

## 8. 深挖：内置编辑器「能不能复用 / 能不能抄」

> 结论修正与补充（读了 ComfyUI_frontend 源码之后）

### 8.1 复用：没有口子，但比"完全没口子"多一点点

源码里只有两条打开路径：

| 入口 | 代码 | 模式 |
|---|---|---|
| 命令 `Comfy.LayerEditor.OpenLayerEditor`（右键/命令面板 "Open Layer Editor for Selected Node"） | `useLayerEditor().openLayerEditor(node)` | **`images` 模式** |
| 节点上的「打开合成器」按钮 | `WidgetCompositor.vue` → `useCompositorEditor()` | **`compositor` 模式**（可回写） |

`openLayerEditor` 的实现里只有这一句：

```ts
useDialogStore().showDialog({
  key: LAYER_EDITOR_DIALOG_KEY,
  headerComponent: LayerEditorDialogHeader,
  component: LayerEditorDialogContent,
  props: { node },          // ← 没有 mode
  dialogComponentProps: layerEditorDialogProps
})
```

它只要求**节点有 ≥2 张输出图**（`getNodeImageUrls(node).length >= 2`），任何节点都能开 —— 但默认 `mode = 'images'`，只能导出 PSD，**不会回写**。

回写要 `mode: 'compositor'`，而 `mode` 是 `LayerEditorContent.vue` 的 prop，**只有** `WidgetCompositor.vue` 那条内部链路会传。所以：第三方扩展拿不到"可回写的编辑器"。

### 8.2 但是！写回协议是「按 widget 名字」的

`compositorWidgets.ts` 里：

```ts
const COMPOSITOR_WIDGET = 'compositor'
export function setCompositorWidgetValue(node, value) {
  setNodeWidgetValue(node, COMPOSITOR_WIDGET, value)
}
```

**没有判断节点类型**。也就是说设计上"任何带 `compositor` widget 的节点"都能承载这份存档 —— 这是一个"差点就能复用"的缝。缺的只是一个公开的 `openCompositor(node)`。

### 8.3 抄：可以，但比看起来贵

编辑器源码是分层的：

| 层 | 位置 | 能否直接用 |
|---|---|---|
| 编辑器内核（场景图/图层模型/持久化） | `packages/layer-editor` | npm **未发布**，只能 vendor |
| 编辑器 UI（Vue 组件） | `packages/layer-editor-ui` | 同上 |
| 节点集成（按钮 widget、会话、自动保存、PSD） | `src/renderer/extensions/layerEditor/*` | 内部 alias `@/...`，你的扩展 bundle 不认 |
| 设计系统（Button 等） | `@comfyorg/design-system` | ✅ 已上 npm（MIT） |

三道坎：

1. **许可证**：ComfyUI_frontend 是 **GPL-3.0**（仓库 license 字段确认）。抄进你的节点，分发时你的节点也必须 GPL-3.0 开源。自己用无所谓，要发布就是硬约束。
2. **不是 npm 包**：`@comfyorg/layer-editor` / `layer-editor-ui` 在 npm 上都是 404，`npm install` 装不到，只能拷源码 + 自己配一套打包。
3. **编辑器画布是 WebGL 的**：官方文档写明"导出需要浏览器支持 WebGL；WebGL 不可用时画布无法渲染"。它跑在 three.js 场景上（前端主包里有 `vendor-three`），所以"抄编辑器"= 连渲染管线、坐标变换、手柄拾取一起抄，不是一个 Vue 组件那么简单。

### 8.4 所以实际可选项

| 做法 | 可行性 | 代价 |
|---|---|---|
| 直接 `showDialog` 复用内置编辑器并回写 | ✗ | 需要内部组件引用 + `mode`，无公开 API |
| Fork `layer-editor` 两个包 vendor 进来 | ✓ 但很重 | GPL-3.0 + 自建打包 + 跟进上游 |
| 自己写 2D canvas（推荐） | ✓ | 300~500 行，覆盖拖动/缩放/旋转/锁定足够 |
| C2 展开成原生 AddLayer 链 | ✓ | 不用写编辑器，但画布上多节点 |

**给自己写 2D 版的理由**：内置编辑器是"类 PSD 通用编辑器"（WebGL 场景 + 混合模式 + PSD 导出），而我们要的只是"把 N 张图摆好、锁定、合并"。2D canvas + Pointer 事件完全够，还能反过来保住 GPL 之外的选择自由。
