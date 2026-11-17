// @ts-ignore - ComfyUI 运行时提供 /scripts/api.js
import { api } from "../../scripts/api.js";
import type { ExecLayer } from "./types";

export function viewURLs(entry: ExecLayer): string[] {
  const params = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder ?? "",
    type: entry.type ?? "temp",
  });
  const plain = "/view?" + params.toString();
  const urls: string[] = [];
  const anyApi = api as any;
  if (anyApi && typeof anyApi.apiURL === "function") {
    try {
      const resolved = anyApi.apiURL(plain);
      if (typeof resolved === "string" && resolved && resolved !== plain) urls.push(resolved);
    } catch (_error) {
      /* 走兜底 */
    }
  }
  urls.push(plain);
  return urls;
}

export function viewURL(entry: ExecLayer): string {
  const urls = viewURLs(entry);
  return urls[urls.length - 1];
}

/** 依次尝试候选地址，全失败再打日志（apiURL 在某些版本会带 /api 前缀，导致 404）。 */
export function applyToImage(img: HTMLImageElement, entry: ExecLayer) {
  const urls = viewURLs(entry);
  let index = 0;
  img.onerror = () => {
    index += 1;
    if (index >= urls.length) {
      console.warn("[ICX] 图片加载失败", entry, urls);
      img.onerror = null;
      return;
    }
    img.src = urls[index];
  };
  img.onload = () => {
    img.onerror = null;
  };
  img.src = urls[0];
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
