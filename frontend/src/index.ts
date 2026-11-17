// @ts-ignore - ComfyUI 运行时提供 /scripts/app.js
import { app } from "../../scripts/app.js";
import { findWidget, getWidgetValue, hideWidget, parseJSON, setWidgetValue, viewURL } from "./api";
import { Editor, layerFromPayload } from "./editor";
import type { EditorInput } from "./editor";
import type { ExecLayer, ExecPayload, Layer } from "./types";

const NODE_TYPE = "ImageCompositorHelper";
const WIDGET_NAME = "layout_json";

/** 让 ComfyUI 立刻跑一次（保存布局后自动合成）。 */
function runNow(node: any): boolean {
  const anyApp: any = app;
  try {
    if (typeof anyApp?.queuePrompt === "function") {
      anyApp.queuePrompt(0, 1);
      return true;
    }
  } catch (error) {
    console.warn("[ICX] queuePrompt 调用失败", error);
  }
  const button = document.querySelector<HTMLButtonElement>(
    "#queue-button, [data-testid='queue-button'], .queue-button",
  );
  if (button) {
    button.click();
    return true;
  }
  return false;
}

function buildContainer(node: any) {
  const container = document.createElement("div");
  container.style.cssText =
    "display:flex;flex-direction:column;gap:6px;padding:6px;box-sizing:border-box;width:100%;";

  const preview = document.createElement("img");
  preview.style.cssText =
    "width:100%;max-height:220px;object-fit:contain;border-radius:6px;background:#17171b;display:none;";
  container.appendChild(preview);

  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:8px;align-items:center;";
  const button = document.createElement("button");
  button.textContent = "打开合成器";
  button.style.cssText =
    "height:28px;padding:0 12px;border-radius:6px;border:1px solid #3a3a46;background:#2b6ee8;" +
    "color:#fff;font-size:12px;cursor:pointer;";
  const status = document.createElement("span");
  status.textContent = "先运行一次以载入图层";
  status.style.cssText = "font-size:11px;color:#8d97ab;";
  row.appendChild(button);
  row.appendChild(status);
  container.appendChild(row);

  return { container, preview, button, status };
}

async function loadLayers(node: any): Promise<EditorInput | null> {
  const payload: ExecPayload | null = node._icx?.payload ?? null;
  if (!payload || !payload.layers || !payload.layers.length) return null;

  const fromWidget = parseJSON(getWidgetValue(node, WIDGET_NAME));
  const saved = fromWidget?.layers?.length ? fromWidget : payload.layout;
  const savedLayers = Array.isArray(saved?.layers) ? saved.layers : [];

  const layers: Layer[] = [];
  for (let index = 0; index < payload.layers.length; index += 1) {
    const entry = payload.layers[index] as ExecLayer;
    const position = entry.index ?? index;
    const savedLayer = savedLayers.find((item: any) => Number(item?.index) === position) ?? savedLayers[position];
    const layer = await layerFromPayload(entry, savedLayer, position);
    layer.thumb = viewURL(entry);
    layers.push(layer);
  }

  const canvas = Array.isArray(payload.canvas)
    ? { width: Number(payload.canvas[0]) || 1024, height: Number(payload.canvas[1]) || 1024 }
    : { width: 1024, height: 1024 };

  return {
    canvas,
    layers,
    fingerprint: String(payload.fingerprint ?? ""),
    stale: Boolean(payload.stale?.[0]),
  };
}

async function openEditor(node: any) {
  if (node._icx?.editor) return;
  const payload = node._icx?.payload;
  if (!payload) {
    node._icx.status.textContent = "还没有执行结果：先点 Run 跑一次";
    console.warn("[ICX] 没有执行结果，先运行一次工作流");
    return;
  }
  const state = await loadLayers(node);
  if (!state) {
    node._icx.status.textContent = "图层数据为空：检查节点输出或浏览器控制台";
    console.warn("[ICX] payload 里没有 layers", payload);
    return;
  }
  if (!state.layers.length) {
    node._icx.status.textContent = "图层预览没生成：看 ComfyUI 控制台日志";
    console.warn("[ICX] layers 为空，可能是预览图保存失败", payload?.errors);
    return;
  }

  const editor = new Editor(state, {
    save: (layout: any, run: boolean) => {
      setWidgetValue(node, WIDGET_NAME, JSON.stringify(layout));
      if (!run) {
        node._icx.status.textContent = "布局已保存：再运行一次即可合成";
        return;
      }
      const queued = runNow(node);
      node._icx.status.textContent = queued
        ? "布局已保存，正在运行…"
        : "布局已保存：请点 Run 运行";
    },
    reload: async () => {
      const fresh = await loadLayers(node);
      if (fresh) node._icx.status.textContent = "已重新加载 " + fresh.layers.length + " 层";
      return fresh;
    },
    close: () => {
      node._icx.editor = null;
    },
  });
  node._icx.editor = editor;
}

function setupNode(node: any) {
  if (node._icx) return;
  const { container, preview, button, status } = buildContainer(node);
  node._icx = { payload: null, editor: null, container, preview, button, status };
  // 注意：widget type 不能叫 "compositor" —— 那是内置 CompositorWidget 的保留类型，
  // 撞名会让 ComfyUI 用一个空的官方预览器顶掉我们的 DOM widget。
  node.addDOMWidget("icx_preview", "deepseek_compositor_ui", container, { serialize: false });

  hideWidget(findWidget(node, WIDGET_NAME));

  button.onclick = () => {
    openEditor(node).catch((error) => {
      status.textContent = "打开失败：" + (error?.message ?? error);
      console.error("[ImageCompositorHelper]", error);
    });
  };

  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function (canvas: any, options: any[]) {
    const result = originalMenu?.apply(this, arguments);
    options.push({
      content: "打开图层合成器",
      callback: () => {
        openEditor(node).catch((error: any) => {
          status.textContent = "打开失败：" + (error?.message ?? error);
          console.error("[ImageCompositorHelper]", error);
        });
      },
    });
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function (output: any) {
    const result = originalExecuted?.apply(this, arguments);
    const payload = output as ExecPayload;
    node._icx.payload = payload;
    console.log("[ICX] 执行结果", payload);
    const count = payload?.layers?.length ?? 0;
    const failed = payload?.errors?.length ?? 0;
    if (!count) {
      status.textContent = failed
        ? "图层预览保存失败：" + payload.errors![0]
        : "没有收到图层数据（见控制台）";
    } else if (payload?.stale?.[0]) {
      status.textContent = "输入已变化：布局已回退默认，打开可重新摆";
    } else {
      status.textContent = "已载入 " + count + " 层 · 画布 " + (payload?.canvas ?? []).join("×");
    }
    if (payload?.preview) {
      preview.src = viewURL(payload.preview as ExecLayer);
      preview.style.display = "block";
    }
    return result;
  };
}

app.registerExtension({
  name: "DeepSeekAPI.ImageCompositorHelper",
  nodeCreated(node: any) {
    const type = node?.comfyClass ?? node?.type;
    if (type !== NODE_TYPE) return;
    try {
      setupNode(node);
      console.log("[ICX] 合成器节点已挂载", node?.id);
    } catch (error) {
      console.error("[ImageCompositorHelper] setup failed", error);
    }
  },
});
