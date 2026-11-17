import { applyToImage, loadImage, viewURL } from "./api";
import { render } from "./canvas";
import {
  boundingBox,
  cursorForHandle,
  hitHandle,
  hitLayer,
  intersects,
  resizeLayer,
  snapBox,
  snapResize,
  toCanvas,
} from "./geometry";
import type { CanvasSize, DragMode, ExecLayer, Guide, HandleId, Layer, Snapshot, View } from "./types";

export interface EditorInput {
  canvas: CanvasSize;
  layers: Layer[];
  fingerprint: string;
  stale: boolean;
}

export interface EditorCallbacks {
  save: (layout: any, run: boolean) => void;
  reload: () => Promise<EditorInput | null>;
  close: () => void;
}

const STYLE_ID = "icx-style";
const MIN_SCALE = 0.05;
const MAX_SCALE = 8;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function injectStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = el("style");
  style.id = STYLE_ID;
  style.textContent = `
  .icx-overlay { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center;
    background: rgba(6,8,14,.72); backdrop-filter: blur(2px); font-family: system-ui, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
  .icx-panel { width: 100vw; height: 100vh; display: grid; grid-template-rows: 46px 1fr 44px;
    grid-template-columns: 232px 1fr 272px; background: #1b1b21; color: #e6ebf5; border: 0; border-radius: 0; overflow: hidden; }
  .icx-head { grid-column: 1 / -1; display: flex; align-items: center; gap: 10px; padding: 0 14px; border-bottom: 1px solid #2c2c36; }
  .icx-title { font-size: 14px; font-weight: 600; }
  .icx-hint { font-size: 12px; color: #8d97ab; }
  .icx-hint.warn { color: #ffb86b; }
  .icx-spacer { flex: 1; }
  .icx-btn { height: 28px; padding: 0 12px; border-radius: 7px; border: 1px solid #3a3a46; background: #24242c; color: #dfe6f3;
    font-size: 12px; cursor: pointer; }
  .icx-btn:hover { background: #2d2d38; }
  .icx-btn:disabled { opacity: .4; cursor: default; background: #24242c; }
  .icx-btn.primary { background: #2b6ee8; border-color: #2b6ee8; color: #fff; }
  .icx-btn.primary:hover { background: #3a7df5; }
  .icx-layers { border-right: 1px solid #2c2c36; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
  .icx-row { display: grid; grid-template-columns: 18px 46px 1fr; gap: 8px; align-items: center; padding: 6px; border-radius: 8px;
    border: 1px solid transparent; cursor: grab; user-select: none; }
  .icx-row.dragging { opacity: .55; cursor: grabbing; }
  .icx-row.drop-before { border-top-color: #2b6ee8; }
  .icx-row.drop-after { border-bottom-color: #2b6ee8; }
  .icx-grip { color: #6b7688; font-size: 12px; letter-spacing: -2px; cursor: grab; }
  .icx-row:hover { background: #24242c; }
  .icx-row.sel { border-color: #2b6ee8; background: #1f2a3d; }
  .icx-thumb { width: 46px; height: 36px; border-radius: 5px; background: #17171c; object-fit: contain; }
  .icx-row-name { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .icx-row-sub { font-size: 11px; color: #8d97ab; }
  .icx-row-tools { display: flex; gap: 2px; }
  .icx-mini { width: 20px; height: 20px; border-radius: 4px; border: 1px solid #3a3a46; background: #24242c; color: #cfd8e6;
    font-size: 11px; line-height: 1; cursor: pointer; padding: 0; }
  .icx-mini:hover { background: #33333d; }
  .icx-stage { position: relative; overflow: hidden; background: #17171b; }
  .icx-stage canvas { display: block; width: 100%; height: 100%; }
  .icx-props { border-left: 1px solid #2c2c36; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
  .icx-field { display: grid; grid-template-columns: 64px 1fr; align-items: center; gap: 8px; font-size: 12px; color: #9aa7bd; }
  .icx-field input[type=text], .icx-field input[type=number] { width: 100%; height: 26px; border-radius: 6px; border: 1px solid #3a3a46;
    background: #15151a; color: #e6ebf5; padding: 0 8px; font-size: 12px; }
  .icx-pair { display: flex; gap: 8px; }
  .icx-sub { font-size: 11px; color: #7f8ba0; }
  .icx-foot { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; padding: 0 14px; border-top: 1px solid #2c2c36; }
  .icx-foot-side { display: flex; align-items: center; gap: 8px; }
  .icx-empty { color: #7f8ba0; font-size: 12px; padding: 10px 6px; }
  `;
  document.head.appendChild(style);
}

export class Editor {
  private root: HTMLDivElement;
  private stage!: HTMLDivElement;
  private canvasEl!: HTMLCanvasElement;
  private ctx!: CanvasRenderingContext2D;
  private listEl!: HTMLDivElement;
  private propsEl!: HTMLDivElement;
  private hintEl!: HTMLSpanElement;
  private zoomEl!: HTMLSpanElement;
  private undoBtn!: HTMLButtonElement;
  private redoBtn!: HTMLButtonElement;

  private canvas: CanvasSize;
  private layers: Layer[];
  private selection = new Set<string>();
  private view: View = { scale: 1, tx: 0, ty: 0 };
  private guides: Guide[] = [];
  private drag: DragMode = { kind: "none" };
  private reorder: { id: string; startY: number; active: boolean } | null = null;
  private spaceDown = false;
  private history: Snapshot[] = [];
  private historyIndex = -1;
  private fingerprint: string;
  private stale: boolean;
  private dirty = false;
  private raf = 0;
  private closed = false;
  private callbacks: EditorCallbacks;
  private onKeyDownBound = (event: KeyboardEvent) => this.onKeyDown(event);

  constructor(input: EditorInput, callbacks: EditorCallbacks) {
    injectStyle();
    this.canvas = { ...input.canvas };
    this.layers = input.layers;
    this.fingerprint = input.fingerprint;
    this.stale = input.stale;
    this.callbacks = callbacks;

    this.root = el("div", "icx-overlay");
    const panel = el("div", "icx-panel");
    panel.appendChild(this.buildHeader());
    this.listEl = el("div", "icx-layers");
    this.stage = el("div", "icx-stage");
    this.canvasEl = el("canvas");
    this.stage.appendChild(this.canvasEl);
    this.propsEl = el("div", "icx-props");
    panel.appendChild(this.listEl);
    panel.appendChild(this.stage);
    panel.appendChild(this.propsEl);
    panel.appendChild(this.buildFooter());
    this.root.appendChild(panel);
    document.body.appendChild(this.root);
    // 聚焦到编辑器本身：否则 Ctrl+Z 会被 ComfyUI 画布的全局快捷键接走
    this.root.tabIndex = -1;
    this.root.style.outline = "none";
    this.root.addEventListener("pointerdown", (event) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
      this.root.focus({ preventScroll: true });
    });
    this.root.focus({ preventScroll: true });
    this.ctx = this.canvasEl.getContext("2d") as CanvasRenderingContext2D;

    this.bindEvents();
    this.pushHistory();
    this.fitView();
    this.resize();
    this.refreshUI();
    this.loop();
  }

  private buildHeader() {
    const head = el("div", "icx-head");
    head.appendChild(el("span", "icx-title", "图层合成器"));
    this.hintEl = el("span", "icx-hint", this.stale ? "输入已变化，已回退默认布局" : "拖动摆位 · 角点缩放 · Shift 解锁比例 · Ctrl+Z 撤销");
    if (this.stale) this.hintEl.classList.add("warn");
    head.appendChild(this.hintEl);
    head.appendChild(el("span", "icx-spacer"));
    head.appendChild(el("span", "icx-sub", "滚轮缩放 · 空格/中键平移 · 方向键微调 · Esc 保存并关闭"));
    return head;
  }

  private buildFooter() {
    const foot = el("div", "icx-foot");

    const left = el("div", "icx-foot-side");
    const fit = el("button", "icx-mini", "Fit");
    fit.style.width = "36px";
    fit.title = "缩放到适合窗口";
    fit.onclick = () => {
      this.fitView();
      this.requestRender();
    };
    left.appendChild(fit);
    const zoomOut = el("button", "icx-mini", "−");
    zoomOut.onclick = () => this.zoomBy(1 / 1.2);
    left.appendChild(zoomOut);
    this.zoomEl = el("span", "icx-sub", "100%");
    left.appendChild(this.zoomEl);
    const zoomIn = el("button", "icx-mini", "+");
    zoomIn.onclick = () => this.zoomBy(1.2);
    left.appendChild(zoomIn);
    foot.appendChild(left);

    foot.appendChild(el("span", "icx-spacer"));

    const right = el("div", "icx-foot-side");

    this.undoBtn = el("button", "icx-btn", "↶ 撤销");
    this.undoBtn.title = "撤销（Ctrl+Z）";
    this.undoBtn.onclick = () => this.undo();
    right.appendChild(this.undoBtn);

    this.redoBtn = el("button", "icx-btn", "↷ 重做");
    this.redoBtn.title = "重做（Ctrl+Shift+Z / Ctrl+Y）";
    this.redoBtn.onclick = () => this.redo();
    right.appendChild(this.redoBtn);

    const reload = el("button", "icx-btn", "重新加载输入");
    reload.onclick = () => this.reload();
    right.appendChild(reload);

    const reset = el("button", "icx-btn", "恢复");
    reset.onclick = () => this.restore();
    right.appendChild(reset);

    const close = el("button", "icx-btn", "关闭");
    close.onclick = () => this.close(false);
    right.appendChild(close);

    const save = el("button", "icx-btn primary", "锁定并保存并运行");
    save.title = "保存布局并立即运行本节点";
    save.onclick = () => this.close(true, true);
    right.appendChild(save);

    foot.appendChild(right);
    return foot;
  }

  private bindEvents() {
    this.canvasEl.addEventListener("pointerdown", (event) => this.onPointerDown(event));
    this.canvasEl.addEventListener("pointermove", (event) => this.onPointerMove(event));
    window.addEventListener("pointerup", (event) => this.onPointerUp(event));
    this.canvasEl.addEventListener("wheel", (event) => this.onWheel(event), { passive: false });
    this.canvasEl.addEventListener("contextmenu", (event) => event.preventDefault());
    window.addEventListener("keydown", this.onKeyDownBound, true);
    window.addEventListener("keyup", (event) => {
      if (event.code === "Space") this.spaceDown = false;
    });
    window.addEventListener("resize", () => this.resize());
  }

  private onKeyDown(event: KeyboardEvent) {
    if (this.closed) return;
    const target = event.target as HTMLElement | null;
    if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    const swallow = (action: () => void) => {
      event.preventDefault();
      // 阻止继续冒泡到 ComfyUI 画布的全局快捷键
      event.stopPropagation();
      event.stopImmediatePropagation();
      action();
    };

    if (event.key === "Escape") {
      swallow(() => this.close(true));
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      swallow(() => (event.shiftKey ? this.redo() : this.undo()));
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      swallow(() => this.redo());
      return;
    }
    if (event.code === "Space") {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      this.spaceDown = true;
      return;
    }
    const step = event.shiftKey ? 10 : 1;
    const nudge: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
    };
    if (nudge[event.key] && this.selection.size) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      const [dx, dy] = nudge[event.key];
      for (const layer of this.selected()) {
        layer.x += dx;
        layer.y += dy;
      }
      this.commit();
    }
  }

  private selected(): Layer[] {
    return this.layers.filter((layer) => this.selection.has(layer.id));
  }

  private pointer(event: PointerEvent) {
    const rect = this.canvasEl.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    return { screenX, screenY, ...toCanvas(this.view, screenX, screenY) };
  }

  private onPointerDown(event: PointerEvent) {
    if (this.closed) return;
    this.canvasEl.setPointerCapture(event.pointerId);
    const point = this.pointer(event);

    if (this.spaceDown || event.button === 1) {
      this.drag = { kind: "pan", tx: this.view.tx, ty: this.view.ty, px: event.clientX, py: event.clientY };
      this.canvasEl.style.cursor = "grabbing";
      return;
    }
    if (event.button !== 0) return;

    const primary = this.selected()[0];
    if (primary) {
      const handle = hitHandle(primary, point.x, point.y, this.view.scale);
      if (handle === "rotate") {
        const center = { x: primary.x + primary.w / 2, y: primary.y + primary.h / 2 };
        this.drag = {
          kind: "rotate",
          startAngle: (Math.atan2(point.y - center.y, point.x - center.x) * 180) / Math.PI,
          origin: new Map(this.selected().map((layer) => [layer.id, layer.rotation])),
        };
        this.canvasEl.style.cursor = cursorForHandle("rotate", 0);
        return;
      }
      if (handle) {
        this.drag = {
          kind: "resize",
          handle,
          origin: new Map(this.selected().map((layer) => [layer.id, { ...layer }])),
        };
        this.canvasEl.style.cursor = cursorForHandle(handle, primary.rotation);
        return;
      }
    }

    const ordered = [...this.layers].sort((a, b) => b.z - a.z);
    const hit = ordered.find((layer) => layer.visible && hitLayer(layer, point.x, point.y));
    if (hit) {
      if (event.shiftKey) {
        if (this.selection.has(hit.id)) this.selection.delete(hit.id);
        else this.selection.add(hit.id);
      } else if (!this.selection.has(hit.id)) {
        this.selection.clear();
        this.selection.add(hit.id);
      }
      this.drag = {
        kind: "move",
        startX: point.x,
        startY: point.y,
        origin: new Map(this.selected().map((layer) => [layer.id, { x: layer.x, y: layer.y }])),
      };
      this.canvasEl.style.cursor = "move";
      this.refreshUI();
      this.requestRender();
      return;
    }

    this.selection.clear();
    this.drag = { kind: "marquee", x0: point.x, y0: point.y, x1: point.x, y1: point.y };
    this.refreshUI();
    this.requestRender();
  }

  private updateCursor(event: PointerEvent) {
    const point = this.pointer(event);
    let cursor = "default";
    if (this.spaceDown) {
      cursor = "grab";
    } else {
      const primary = this.selected()[0];
      if (primary) {
        const handle = hitHandle(primary, point.x, point.y, this.view.scale);
        if (handle) cursor = cursorForHandle(handle, primary.rotation);
      }
      if (cursor === "default") {
        const ordered = [...this.layers].sort((a, b) => b.z - a.z);
        const hit = ordered.find((layer) => layer.visible && hitLayer(layer, point.x, point.y));
        if (hit) cursor = "move";
      }
    }
    if (this.canvasEl.style.cursor !== cursor) this.canvasEl.style.cursor = cursor;
  }

  private onPointerMove(event: PointerEvent) {
    if (this.closed) return;
    if (this.drag.kind === "none") {
      this.updateCursor(event);
      return;
    }
    const point = this.pointer(event);

    if (this.drag.kind === "pan") {
      this.view.tx = this.drag.tx + (event.clientX - this.drag.px);
      this.view.ty = this.drag.ty + (event.clientY - this.drag.py);
      this.requestRender();
      return;
    }

    if (this.drag.kind === "move") {
      let dx = point.x - this.drag.startX;
      let dy = point.y - this.drag.startY;
      const moving = this.selected();
      const box = boundingBox(moving.map((layer) => ({ ...layer, x: layer.x + dx, y: layer.y + dy })));
      const others = this.layers.filter((layer) => !this.selection.has(layer.id));
      const snap = snapBox(box, others, this.canvas, this.view.scale);
      dx += snap.dx;
      dy += snap.dy;
      this.guides = snap.guides;
      for (const layer of moving) {
        const origin = this.drag.origin.get(layer.id);
        if (!origin) continue;
        layer.x = Math.round(origin.x + dx);
        layer.y = Math.round(origin.y + dy);
      }
      this.syncInputs();
      this.requestRender();
      return;
    }

    if (this.drag.kind === "resize") {
      for (const layer of this.selected()) {
        const origin = this.drag.origin.get(layer.id);
        if (!origin) continue;
        const lockAspect = event.shiftKey ? !origin.keep_aspect : origin.keep_aspect;
        Object.assign(layer, resizeLayer(origin, this.drag.handle, point.x, point.y, lockAspect));
      }
      // 单层缩放时吸附到画布/其他图层的边线（旋转过的图层不吸附，避免手感错乱）
      if (this.selection.size === 1) {
        const layer = this.selected()[0];
        const others = this.layers.filter((item) => !this.selection.has(item.id));
        const snapped = snapResize(layer, this.drag.handle, others, this.canvas, this.view.scale);
        layer.x = snapped.x;
        layer.y = snapped.y;
        layer.w = snapped.w;
        layer.h = snapped.h;
        this.guides = snapped.guides;
      } else {
        this.guides = [];
      }
      this.syncInputs();
      this.requestRender();
      return;
    }

    if (this.drag.kind === "rotate") {
      for (const layer of this.selected()) {
        const base = this.drag.origin.get(layer.id) ?? 0;
        const center = { x: layer.x + layer.w / 2, y: layer.y + layer.h / 2 };
        const angle = (Math.atan2(point.y - center.y, point.x - center.x) * 180) / Math.PI;
        let rotation = base + (angle - this.drag.startAngle);
        if (event.shiftKey) rotation = Math.round(rotation / 15) * 15;
        layer.rotation = Math.round(((rotation % 360) + 360) % 360 * 10) / 10;
      }
      this.syncInputs();
      this.requestRender();
      return;
    }

    if (this.drag.kind === "marquee") {
      this.drag.x1 = point.x;
      this.drag.y1 = point.y;
      const box = {
        x: Math.min(this.drag.x0, this.drag.x1),
        y: Math.min(this.drag.y0, this.drag.y1),
        w: Math.abs(this.drag.x1 - this.drag.x0),
        h: Math.abs(this.drag.y1 - this.drag.y0),
      };
      this.selection.clear();
      for (const layer of this.layers) {
        const bb = boundingBox([layer]);
        if (intersects(box, bb)) this.selection.add(layer.id);
      }
      this.refreshUI();
      this.requestRender();
    }
  }

  private onPointerUp(_event: PointerEvent) {
    if (this.closed) return;
    if (this.drag.kind === "marquee" || this.drag.kind === "move" || this.drag.kind === "resize" || this.drag.kind === "rotate") {
      this.commit();
    }
    this.drag = { kind: "none" };
    this.guides = [];
    this.canvasEl.style.cursor = "";
    this.requestRender();
  }

  private onWheel(event: WheelEvent) {
    if (this.closed) return;
    event.preventDefault();
    const rect = this.canvasEl.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
    this.zoomAt(screenX, screenY, factor);
  }

  private zoomAt(screenX: number, screenY: number, factor: number) {
    const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, this.view.scale * factor));
    if (next === this.view.scale) return;
    const before = toCanvas(this.view, screenX, screenY);
    this.view.scale = next;
    this.view.tx = screenX - before.x * next;
    this.view.ty = screenY - before.y * next;
    this.updateZoomLabel();
    this.requestRender();
  }

  private zoomBy(factor: number) {
    const rect = this.canvasEl.getBoundingClientRect();
    this.zoomAt(rect.width / 2, rect.height / 2, factor);
  }

  private fitView() {
    const rect = this.canvasEl.getBoundingClientRect();
    const width = Math.max(40, rect.width);
    const height = Math.max(40, rect.height);
    const pad = 48;
    const scale = Math.max(MIN_SCALE, Math.min((width - pad) / this.canvas.width, (height - pad) / this.canvas.height));
    this.view.scale = scale;
    this.view.tx = (width - this.canvas.width * scale) / 2;
    this.view.ty = (height - this.canvas.height * scale) / 2;
    this.updateZoomLabel();
  }

  private updateZoomLabel() {
    if (this.zoomEl) this.zoomEl.textContent = Math.round(this.view.scale * 100) + "%";
  }

  private resize() {
    const rect = this.stage.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvasEl.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvasEl.height = Math.max(1, Math.round(rect.height * dpr));
    this.requestRender();
  }

  private requestRender() {
    this.dirty = true;
  }

  private loop = () => {
    if (this.closed) return;
    if (this.dirty) {
      this.dirty = false;
      const rect = this.canvasEl.getBoundingClientRect();
      render(this.ctx, {
        canvas: this.canvas,
        layers: this.layers,
        view: this.view,
        selection: this.selection,
        guides: this.guides,
        marquee: this.drag.kind === "marquee" ? this.drag : null,
      }, rect.width, rect.height);
    }
    this.raf = requestAnimationFrame(this.loop);
  };

  private pushHistory(initial = false) {
    const snapshot: Snapshot = {
      canvas: { ...this.canvas },
      layers: this.layers.map((layer) => ({ ...layer })),
    };
    if (!initial && this.historyIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.historyIndex + 1);
    }
    this.history.push(snapshot);
    if (this.history.length > 60) this.history.shift();
    this.historyIndex = this.history.length - 1;
  }

  private commit() {
    this.pushHistory();
    this.refreshUI();
    this.requestRender();
  }

  private undo() {
    if (this.historyIndex <= 0) return;
    this.historyIndex -= 1;
    this.restoreSnapshot(this.history[this.historyIndex]);
  }

  private redo() {
    if (this.historyIndex >= this.history.length - 1) return;
    this.historyIndex += 1;
    this.restoreSnapshot(this.history[this.historyIndex]);
  }

  private restoreSnapshot(snapshot: Snapshot) {
    const images = new Map(this.layers.map((layer) => [layer.id, layer.img]));
    const thumbs = new Map(this.layers.map((layer) => [layer.id, layer.thumb]));
    this.layers = snapshot.layers.map((layer) => ({ ...layer, img: images.get(layer.id), thumb: thumbs.get(layer.id) }));
    const ids = new Set(this.layers.map((layer) => layer.id));
    for (const id of [...this.selection]) if (!ids.has(id)) this.selection.delete(id);
    this.refreshUI();
    this.requestRender();
  }

  private restore() {
    const open = this.history[0];
    if (!open) return;
    this.restoreSnapshot(open);
    this.history = [this.history[0]];
    this.historyIndex = 0;
  }

  private updateHistoryButtons() {
    if (this.undoBtn) this.undoBtn.disabled = this.historyIndex <= 0;
    if (this.redoBtn) this.redoBtn.disabled = this.historyIndex >= this.history.length - 1;
  }

  private refreshUI() {
    this.updateHistoryButtons();
    this.renderList();
    this.renderProps();
    if (this.hintEl) {
      this.hintEl.textContent = this.selection.size > 1
        ? "已选 " + this.selection.size + " 层：拖动整体移动 · Shift 点选增减"
        : "拖动摆位 · 角点缩放 · Shift 解锁比例 · Ctrl+Z 撤销";
    }
    this.updateZoomLabel();
  }

  private renderList() {
    this.listEl.innerHTML = "";
    const ordered = [...this.layers].sort((a, b) => b.z - a.z);
    for (const layer of ordered) {
      const row = el("div", "icx-row" + (this.selection.has(layer.id) ? " sel" : ""));
      row.dataset.layerId = layer.id;

      const grip = el("span", "icx-grip", "⣿");
      grip.title = "拖拽调整层级";
      row.appendChild(grip);

      const thumb = el("img", "icx-thumb");
      if (layer.source) applyToImage(thumb, layer.source);
      else if (layer.thumb) thumb.src = layer.thumb;
      thumb.title = layer.visible ? "点击切换显隐" : "已隐藏，点击显示";
      thumb.style.opacity = layer.visible ? "1" : "0.35";
      thumb.onclick = (event) => {
        event.stopPropagation();
        layer.visible = !layer.visible;
        this.commit();
      };
      row.appendChild(thumb);

      const meta = el("div");
      meta.appendChild(el("div", "icx-row-name", layer.name));
      meta.appendChild(el("div", "icx-row-sub", Math.round(layer.w) + "×" + Math.round(layer.h) + " · " + Math.round(layer.opacity * 100) + "%"));
      row.appendChild(meta);

      row.onpointerdown = (event) => this.beginReorder(event, layer);
      row.onclick = (event) => {
        if (event.shiftKey) {
          if (this.selection.has(layer.id)) this.selection.delete(layer.id);
          else this.selection.add(layer.id);
        } else {
          this.selection.clear();
          this.selection.add(layer.id);
        }
        this.refreshUI();
        this.requestRender();
      };
      this.listEl.appendChild(row);
    }
    if (!ordered.length) this.listEl.appendChild(el("div", "icx-empty", "没有图层"));
  }

  private beginReorder(event: PointerEvent, layer: Layer) {
    if (event.button !== 0) return;
    this.reorder = { id: layer.id, startY: event.clientY, active: false };

    const onMove = (moveEvent: PointerEvent) => {
      if (!this.reorder) return;
      if (!this.reorder.active && Math.abs(moveEvent.clientY - this.reorder.startY) < 4) return;
      this.reorder.active = true;
      document.body.style.cursor = "grabbing";
      const dragged = this.listEl.querySelector<HTMLElement>(
        '.icx-row[data-layer-id="' + this.reorder.id + '"]',
      );
      dragged?.classList.add("dragging");
      this.markDropTarget(moveEvent.clientY);
    };
    const onUp = (upEvent: PointerEvent) => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.cursor = "";
      const wasActive = this.reorder?.active ?? false;
      this.reorder = null;
      this.clearDropMarks();
      if (!wasActive) return;
      const row = this.rowAt(upEvent.clientY);
      if (row !== null) this.moveLayerToRow(layer.id, row);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  private rows(): HTMLElement[] {
    return Array.from(this.listEl.querySelectorAll<HTMLElement>(".icx-row"));
  }

  private rowAt(y: number): number | null {
    const rows = this.rows();
    if (!rows.length) return null;
    for (let index = 0; index < rows.length; index += 1) {
      const rect = rows[index].getBoundingClientRect();
      if (y < rect.top + rect.height / 2) return index;
    }
    return rows.length;
  }

  private markDropTarget(y: number) {
    this.clearDropMarks();
    const rows = this.rows();
    const target = this.rowAt(y);
    if (target === null || !rows.length) return;
    const row = rows[Math.min(target, rows.length - 1)];
    row.classList.add(target >= rows.length ? "drop-after" : "drop-before");
  }

  private clearDropMarks() {
    for (const row of this.rows()) row.classList.remove("drop-before", "drop-after", "dragging");
  }

  /** 列表是自顶向下（z 大在上），拖到第 row 个位置 = 放到对应 z。 */
  private moveLayerToRow(layerId: string, row: number) {
    const ordered = [...this.layers].sort((a, b) => a.z - b.z);
    const count = ordered.length;
    if (count < 2) return;
    const from = ordered.findIndex((item) => item.id === layerId);
    if (from < 0) return;

    let targetZ = count - 1 - row;
    targetZ = Math.max(0, Math.min(count - 1, targetZ));
    if (targetZ === from) return;

    const [moved] = ordered.splice(from, 1);
    ordered.splice(targetZ, 0, moved);
    ordered.forEach((item, index) => {
      item.z = index;
    });
    this.commit();
  }

  private renderProps() {
    this.propsEl.innerHTML = "";
    const selected = this.selected();
    if (!selected.length) {
      this.propsEl.appendChild(el("div", "icx-empty", "未选中图层：点画布或左栏选择"));
      return;
    }
    const layer = selected[0];
    const isMulti = selected.length > 1;

    this.propsEl.appendChild(el("div", "icx-sub", isMulti ? "已选 " + selected.length + " 层（编辑第一层）" : "图层属性"));

    const nameField = el("label", "icx-field");
    nameField.appendChild(el("span", "", "名称"));
    const nameInput = el("input");
    nameInput.type = "text";
    nameInput.value = layer.name;
    nameInput.onchange = () => {
      layer.name = nameInput.value || layer.name;
      this.commit();
    };
    nameField.appendChild(nameInput);
    this.propsEl.appendChild(nameField);

    const numberRow = (label: string, key: keyof Layer, step = 1) => {
      const wrap = el("label", "icx-field");
      wrap.appendChild(el("span", "", label));
      const input = el("input");
      input.type = "number";
      input.step = String(step);
      input.dataset.key = String(key);
      input.value = String(Math.round((layer[key] as number) * 10) / 10);
      input.onchange = () => {
        const value = Number(input.value);
        if (!Number.isFinite(value)) return;
        for (const item of this.selected()) (item[key] as number) = key === "w" || key === "h" ? Math.max(8, value) : value;
        this.commit();
      };
      wrap.appendChild(input);
      this.propsEl.appendChild(wrap);
      return input;
    };

    const xy = el("div", "icx-pair");
    this.propsEl.appendChild(xy);
    const posRow = el("div", "icx-field");
    posRow.appendChild(el("span", "", "位置 X/Y"));
    const xInput = el("input");
    xInput.type = "number";
    xInput.dataset.key = "x";
    xInput.value = String(Math.round(layer.x));
    const yInput = el("input");
    yInput.type = "number";
    yInput.dataset.key = "y";
    yInput.value = String(Math.round(layer.y));
    const posWrap = el("div", "icx-pair");
    posWrap.appendChild(xInput);
    posWrap.appendChild(yInput);
    posRow.appendChild(posWrap);
    xInput.onchange = () => {
      const value = Number(xInput.value);
      if (!Number.isFinite(value)) return;
      for (const item of this.selected()) item.x = value;
      this.commit();
    };
    yInput.onchange = () => {
      const value = Number(yInput.value);
      if (!Number.isFinite(value)) return;
      for (const item of this.selected()) item.y = value;
      this.commit();
    };
    this.propsEl.appendChild(posRow);

    const sizeRow = el("div", "icx-field");
    sizeRow.appendChild(el("span", "", "尺寸 W/H"));
    const wInput = el("input");
    wInput.type = "number";
    wInput.min = "8";
    wInput.value = String(Math.round(layer.w));
    const hInput = el("input");
    hInput.type = "number";
    hInput.min = "8";
    hInput.value = String(Math.round(layer.h));
    const sizeWrap = el("div", "icx-pair");
    sizeWrap.appendChild(wInput);
    sizeWrap.appendChild(hInput);
    sizeRow.appendChild(sizeWrap);
    wInput.onchange = () => {
      const value = Math.max(8, Number(wInput.value));
      if (!Number.isFinite(value)) return;
      for (const item of this.selected()) {
        const ratio = item.h / item.w;
        item.w = value;
        if (item.keep_aspect) item.h = Math.round(value * ratio);
      }
      this.commit();
    };
    hInput.onchange = () => {
      const value = Math.max(8, Number(hInput.value));
      if (!Number.isFinite(value)) return;
      for (const item of this.selected()) {
        const ratio = item.w / item.h;
        item.h = value;
        if (item.keep_aspect) item.w = Math.round(value * ratio);
      }
      this.commit();
    };
    this.propsEl.appendChild(sizeRow);

    numberRow("层级 Z", "z");
    numberRow("旋转 °", "rotation", 1);

    const aspect = el("label", "icx-field");
    aspect.appendChild(el("span", "", "锁定比例"));
    const aspectBox = el("input");
    aspectBox.type = "checkbox";
    aspectBox.checked = layer.keep_aspect;
    aspectBox.onchange = () => {
      layer.keep_aspect = aspectBox.checked;
      this.commit();
    };
    aspect.appendChild(aspectBox);
    this.propsEl.appendChild(aspect);

    const visible = el("label", "icx-field");
    visible.appendChild(el("span", "", "显示"));
    const visibleBox = el("input");
    visibleBox.type = "checkbox";
    visibleBox.checked = layer.visible;
    visibleBox.onchange = () => {
      layer.visible = visibleBox.checked;
      this.commit();
    };
    visible.appendChild(visibleBox);
    this.propsEl.appendChild(visible);

    const opacityField = el("label", "icx-field");
    opacityField.appendChild(el("span", "", "不透明度"));
    const opacity = el("input");
    opacity.type = "range";
    opacity.min = "0";
    opacity.max = "100";
    opacity.value = String(Math.round(layer.opacity * 100));
    opacity.oninput = () => {
      for (const item of this.selected()) item.opacity = Number(opacity.value) / 100;
      this.requestRender();
    };
    opacity.onchange = () => this.commit();
    opacityField.appendChild(opacity);
    this.propsEl.appendChild(opacityField);

    const flips = el("div", "icx-field");
    flips.appendChild(el("span", "", "翻转"));
    const flipWrap = el("div", "icx-pair");
    const flipH = el("button", "icx-btn", "水平 ↔");
    flipH.onclick = () => {
      for (const item of this.selected()) item.flip_h = !item.flip_h;
      this.commit();
    };
    const flipV = el("button", "icx-btn", "垂直 ↕");
    flipV.onclick = () => {
      for (const item of this.selected()) item.flip_v = !item.flip_v;
      this.commit();
    };
    flipWrap.appendChild(flipH);
    flipWrap.appendChild(flipV);
    flips.appendChild(flipWrap);
    this.propsEl.appendChild(flips);

    const sizeHint = el("div", "icx-sub", "原图 " + layer.naturalW + "×" + layer.naturalH);
    this.propsEl.appendChild(sizeHint);
  }

  private syncInputs() {
    const selected = this.selected()[0];
    if (!selected) return;
    const inputs = this.propsEl.querySelectorAll("input[data-key]");
    inputs.forEach((input) => {
      const element = input as HTMLInputElement;
      const key = element.dataset.key as keyof Layer;
      const value = selected[key];
      if (typeof value === "number") element.value = String(Math.round(value * 10) / 10);
    });
    const sub = this.listEl.querySelector(".icx-row.sel .icx-row-sub");
    if (sub) sub.textContent = Math.round(selected.w) + "×" + Math.round(selected.h) + " · " + Math.round(selected.opacity * 100) + "%";
  }

  private serialize() {
    const layers = [...this.layers]
      .sort((a, b) => a.z - b.z)
      .map((layer) => ({
        id: layer.id,
        index: layer.index,
        name: layer.name,
        x: Math.round(layer.x),
        y: Math.round(layer.y),
        z: layer.z,
        w: Math.round(layer.w),
        h: Math.round(layer.h),
        rotation: Math.round(layer.rotation * 10) / 10,
        opacity: Math.round(layer.opacity * 100) / 100,
        visible: layer.visible,
        keep_aspect: layer.keep_aspect,
        flip_h: layer.flip_h,
        flip_v: layer.flip_v,
      }));
    return {
      version: 2,
      canvas: { width: this.canvas.width, height: this.canvas.height },
      locked: true,
      fingerprint: this.fingerprint,
      layers,
    };
  }

  private async reload() {
    const next = await this.callbacks.reload();
    if (!next) return;
    this.canvas = { ...next.canvas };
    this.layers = next.layers;
    this.fingerprint = next.fingerprint;
    this.stale = next.stale;
    this.selection.clear();
    this.history = [];
    this.historyIndex = -1;
    this.pushHistory(true);
    this.fitView();
    this.refreshUI();
    this.requestRender();
  }

  private close(save: boolean, run = false) {
    if (this.closed) return;
    this.closed = true;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("keydown", this.onKeyDownBound);
    this.root.remove();
    if (save) this.callbacks.save(this.serialize(), run);
    this.callbacks.close();
  }

  /** 外部数据刷新（例如节点重新执行后）。 */
  updateImages(layers: Layer[], fingerprint: string, stale: boolean) {
    this.layers = layers;
    this.fingerprint = fingerprint;
    this.stale = stale;
    this.selection.clear();
    this.history = [];
    this.historyIndex = -1;
    this.pushHistory(true);
    this.refreshUI();
    this.requestRender();
  }
}

export function layerFromPayload(entry: ExecLayer, saved: any, index: number): Promise<Layer> {
  const naturalWidth = Number(entry.width || saved?.w || 512);
  const naturalHeight = Number(entry.height || saved?.h || 512);
  return loadImage(viewURL(entry)).then((image) => ({
    id: "layer_" + index,
    index,
    name: saved?.name || "图层 " + (index + 1),
    x: Number(saved?.x ?? 0),
    y: Number(saved?.y ?? 0),
    z: Number(saved?.z ?? index),
    w: Number(saved?.w ?? naturalWidth),
    h: Number(saved?.h ?? naturalHeight),
    rotation: Number(saved?.rotation ?? 0),
    opacity: Number(saved?.opacity ?? 1),
    visible: saved?.visible ?? true,
    keep_aspect: saved?.keep_aspect ?? true,
    flip_h: saved?.flip_h ?? false,
    flip_v: saved?.flip_v ?? false,
    naturalW: naturalWidth,
    naturalH: naturalHeight,
    img: image,
    thumb: viewURL(entry),
    source: { filename: entry.filename, subfolder: entry.subfolder, type: entry.type },
  }));
}
