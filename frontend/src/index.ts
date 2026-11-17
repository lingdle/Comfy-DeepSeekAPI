// @ts-ignore - ComfyUI 运行时提供 /scripts/app.js
import { app } from "../../scripts/app.js";
import { findWidget, getWidgetValue, hideWidget, parseJSON, setWidgetValue, viewURL } from "./api";
import { Editor, layerFromPayload } from "./editor";
import type { EditorInput } from "./editor";
import type { ExecLayer, ExecPayload, Layer } from "./types";

const NODE_TYPE = "LayerCompositor";
const WIDGET_NAME = "layout_json";

/**
 * 只运行本节点：新前端支持 partial execution，
 * 第三参传 { queueNodeIds: [id] }（旧签名也可以直接传 id 数组）。
 */
function runNow(node: any): "partial" | "full" | "none" {
  const anyApp: any = app;
  const id = String(node?.id ?? "");
  if (!id) return "none";

  const attempt = (invoke: () => any): boolean => {
    try {
      const result = invoke();
      if (result && typeof result.then === "function") {
        result.catch((error: any) => console.warn("[ICX] 排队失败", error));
      }
      return true;
    } catch (error) {
      console.warn("[ICX] 排队调用失败", error);
      return false;
    }
  };

  if (typeof anyApp?.queuePrompt === "function") {
    if (attempt(() => anyApp.queuePrompt(0, 1, { queueNodeIds: [id] }))) return "partial";
    if (attempt(() => anyApp.queuePrompt(0, 1, [id]))) return "partial";
    if (attempt(() => anyApp.queuePrompt(0, 1))) return "full";
  }

  const button = document.querySelector<HTMLButtonElement>(
    "#queue-button, [data-testid='queue-button'], .queue-button",
  );
  if (button) {
    button.click();
    return "full";
  }
  return "none";
}

function buildContainer(node: any) {
  const container = document.createElement("div");
  container.style.cssText =
    "display:flex;flex-direction:column;gap:6px;padding:6px;box-sizing:border-box;width:100%;";

  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;";
  const button = document.createElement("button");
  button.textContent = "打开合成器";
  button.style.cssText =
    "height:28px;padding:0 12px;border-radius:6px;border:1px solid #3a3a46;background:#2b6ee8;" +
    "color:#fff;font-size:12px;cursor:pointer;";
  const status = document.createElement("span");
  status.textContent = "先运行一次以载入图层";
  status.style.cssText = "font-size:11px;color:#8d97ab;";
  const runButton = document.createElement("button");
  runButton.textContent = "▶ 运行本节点";
  runButton.title = "只执行这个节点（不跑整张图）";
  runButton.style.cssText =
    "height:28px;padding:0 10px;border-radius:6px;border:1px solid #3a3a46;background:#24242c;" +
    "color:#dfe6f3;font-size:12px;cursor:pointer;";
  row.appendChild(button);
  row.appendChild(runButton);
  row.appendChild(status);
  container.appendChild(row);

  return { container, button, runButton, status };
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
      node._icx.status.textContent =
        queued === "partial"
          ? "布局已保存，正在运行本节点…"
          : queued === "full"
            ? "布局已保存，已排队整图（前端不支持单节点运行）…"
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
  const { container, button, runButton, status } = buildContainer(node);
  node._icx = { payload: null, editor: null, container, button, runButton, status };
  // 注意：widget type 不能叫 "compositor" —— 那是内置 CompositorWidget 的保留类型，
  // 撞名会让 ComfyUI 用一个空的官方预览器顶掉我们的 DOM widget。
  node.addDOMWidget("icx_preview", "deepseek_compositor_ui", container, { serialize: false });

  hideWidget(findWidget(node, WIDGET_NAME));

  button.onclick = () => {
    openEditor(node).catch((error) => {
      status.textContent = "打开失败：" + (error?.message ?? error);
      console.error("[LayerCompositor]", error);
    });
  };

  runButton.onclick = () => {
    const queued = runNow(node);
    status.textContent =
      queued === "partial"
        ? "正在运行本节点…"
        : queued === "full"
          ? "前端不支持单节点运行，已排队整图…"
          : "找不到运行入口：请手动点 Queue";
  };

  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function (canvas: any, options: any[]) {
    const result = originalMenu?.apply(this, arguments);
    options.push({
      content: "打开合成器",
      callback: () => {
        openEditor(node).catch((error: any) => {
          status.textContent = "打开失败：" + (error?.message ?? error);
          console.error("[LayerCompositor]", error);
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
    } else {
      const size = (payload?.canvas ?? []).join("×");
      status.textContent = payload?.stale?.[0]
        ? "输入已变化：已回退默认布局 · 画布 " + size
        : "已载入 " + count + " 层 · 画布 " + size;
    }
    if (!payload?.images?.length && payload?.errors?.length) {
      status.textContent = "预览生成失败：" + payload.errors[0];
    }
    return result;
  };
}

app.registerExtension({
  name: "DeepSeekAPI.LayerCompositor",
  nodeCreated(node: any) {
    const type = node?.comfyClass ?? node?.type;
    if (type !== NODE_TYPE) return;
    try {
      setupNode(node);
      console.log("[ICX] 合成器节点已挂载", node?.id);
    } catch (error) {
      console.error("[LayerCompositor] setup failed", error);
    }
  },
});
