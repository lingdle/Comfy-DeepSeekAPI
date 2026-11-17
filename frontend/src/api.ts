// @ts-ignore - ComfyUI 运行时提供 /scripts/api.js
import { api } from "../../scripts/api.js";
import type { ExecLayer } from "./types";

export function viewURL(entry: ExecLayer): string {
  const params = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder ?? "",
    type: entry.type ?? "temp",
  });
  const path = "/view?" + params.toString();
  const anyApi = api as any;
  if (anyApi && typeof anyApi.apiURL === "function") return anyApi.apiURL(path);
  return path;
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败: " + src));
    image.src = src;
  });
}

export function findWidget(node: any, name: string) {
  const widgets = node?.widgets ?? [];
  return widgets.find((widget: any) => widget.name === name) ?? null;
}

export function getWidgetValue(node: any, name: string): string {
  const widget = findWidget(node, name);
  return widget && typeof widget.value === "string" ? widget.value : "";
}

export function setWidgetValue(node: any, name: string, value: string) {
  const widget = findWidget(node, name);
  if (!widget) return;
  widget.value = value;
  node?.setDirtyCanvas?.(true, true);
}

export function hideWidget(widget: any) {
  if (!widget) return;
  // 只收起高度：改 type 会影响 LiteGraph 的 widget 序列化
  widget.computeSize = () => [0, -4];
  widget.hidden = true;
}

export function parseJSON(text: string): any {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
}
