// Comfy-DeepSeekAPI · ImageCompositorHelper v1.0.0 (built from frontend/src, do not edit)

// src/index.ts
import { app } from "../../scripts/app.js";

// src/api.ts
import { api } from "../../scripts/api.js";
function viewURL(entry) {
  const params = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder ?? "",
    type: entry.type ?? "temp"
  });
  const path = "/view?" + params.toString();
  const anyApi = api;
  if (anyApi && typeof anyApi.apiURL === "function") return anyApi.apiURL(path);
  return path;
}
function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("\u56FE\u7247\u52A0\u8F7D\u5931\u8D25: " + src));
    image.src = src;
  });
}
function findWidget(node, name) {
  const widgets = node?.widgets ?? [];
  return widgets.find((widget) => widget.name === name) ?? null;
}
function getWidgetValue(node, name) {
  const widget = findWidget(node, name);
  return widget && typeof widget.value === "string" ? widget.value : "";
}
function setWidgetValue(node, name, value) {
  const widget = findWidget(node, name);
  if (!widget) return;
  widget.value = value;
  node?.setDirtyCanvas?.(true, true);
}
function hideWidget(widget) {
  if (!widget) return;
  widget.computeSize = () => [0, -4];
  widget.hidden = true;
}
function parseJSON(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
}

// src/geometry.ts
var HANDLE_TOLERANCE = 7;
var RESIZE_CURSORS = {
  n: "ns-resize",
  s: "ns-resize",
  e: "ew-resize",
  w: "ew-resize",
  nw: "nwse-resize",
  se: "nwse-resize",
  ne: "nesw-resize",
  sw: "nesw-resize"
};
var ROTATE_CURSOR = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'><path d='M12 4a8 8 0 1 1-7.4 5' fill='none' stroke='white' stroke-width='2' stroke-linecap='round'/><path d='M12 4V1L8 4.5 12 8' fill='white'/></svg>") 12 12, crosshair`;
function cursorForHandle(handle, rotation) {
  if (handle === "rotate") return ROTATE_CURSOR;
  const baseCursor = RESIZE_CURSORS[handle] ?? "default";
  const angles = {
    e: 0,
    se: 45,
    s: 90,
    sw: 135,
    w: 180,
    nw: 225,
    n: 270,
    ne: 315
  };
  const angle = (angles[handle] ?? 0) + rotation;
  const bucket = (Math.round(angle / 45) % 8 + 8) % 8;
  return [
    "ew-resize",
    "nwse-resize",
    "ns-resize",
    "nesw-resize",
    "ew-resize",
    "nwse-resize",
    "ns-resize",
    "nesw-resize"
  ][bucket];
}
var SNAP_PIXELS = 6;
function toScreen(view, x, y) {
  return { x: x * view.scale + view.tx, y: y * view.scale + view.ty };
}
function toCanvas(view, x, y) {
  return { x: (x - view.tx) / view.scale, y: (y - view.ty) / view.scale };
}
function centerOf(layer) {
  return { x: layer.x + layer.w / 2, y: layer.y + layer.h / 2 };
}
function rotatePoint(x, y, radians) {
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return { x: x * cos - y * sin, y: x * sin + y * cos };
}
function layerCorners(layer) {
  const radians = layer.rotation * Math.PI / 180;
  const center = centerOf(layer);
  const hw = layer.w / 2;
  const hh = layer.h / 2;
  return [
    { x: -hw, y: -hh },
    { x: hw, y: -hh },
    { x: hw, y: hh },
    { x: -hw, y: hh }
  ].map((point) => {
    const rotated = rotatePoint(point.x, point.y, radians);
    return { x: center.x + rotated.x, y: center.y + rotated.y };
  });
}
function hitLayer(layer, x, y) {
  const center = centerOf(layer);
  const radians = -layer.rotation * Math.PI / 180;
  const local = rotatePoint(x - center.x, y - center.y, radians);
  return Math.abs(local.x) <= layer.w / 2 && Math.abs(local.y) <= layer.h / 2;
}
function handlePoints(layer, viewScale) {
  const radians = layer.rotation * Math.PI / 180;
  const center = centerOf(layer);
  const hw = layer.w / 2;
  const hh = layer.h / 2;
  const offset = 34 / viewScale;
  const spots = [
    { id: "nw", x: -hw, y: -hh },
    { id: "n", x: 0, y: -hh },
    { id: "ne", x: hw, y: -hh },
    { id: "e", x: hw, y: 0 },
    { id: "se", x: hw, y: hh },
    { id: "s", x: 0, y: hh },
    { id: "sw", x: -hw, y: hh },
    { id: "w", x: -hw, y: 0 },
    { id: "rotate", x: 0, y: -hh - offset }
  ];
  return spots.map((spot) => {
    const rotated = rotatePoint(spot.x, spot.y, radians);
    return { id: spot.id, x: center.x + rotated.x, y: center.y + rotated.y };
  });
}
function hitHandle(layer, x, y, viewScale) {
  const tolerance = HANDLE_TOLERANCE / viewScale;
  for (const handle of handlePoints(layer, viewScale)) {
    if (Math.abs(handle.x - x) <= tolerance && Math.abs(handle.y - y) <= tolerance) {
      return handle.id;
    }
  }
  return null;
}
function boundingBox(layers) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const layer of layers) {
    for (const corner of layerCorners(layer)) {
      minX = Math.min(minX, corner.x);
      minY = Math.min(minY, corner.y);
      maxX = Math.max(maxX, corner.x);
      maxY = Math.max(maxY, corner.y);
    }
  }
  if (!Number.isFinite(minX)) return { x: 0, y: 0, w: 0, h: 0 };
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}
function intersects(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
function snapBox(box, targets, canvas, viewScale) {
  const threshold = SNAP_PIXELS / viewScale;
  const xLines = [0, canvas.width / 2, canvas.width];
  const yLines = [0, canvas.height / 2, canvas.height];
  for (const layer of targets) {
    const bb = boundingBox([layer]);
    xLines.push(bb.x, bb.x + bb.w / 2, bb.x + bb.w);
    yLines.push(bb.y, bb.y + bb.h / 2, bb.y + bb.h);
  }
  const candidatesX = [box.x, box.x + box.w / 2, box.x + box.w];
  const candidatesY = [box.y, box.y + box.h / 2, box.y + box.h];
  let bestX = { delta: 0, distance: threshold, line: NaN };
  for (const candidate of candidatesX) {
    for (const line of xLines) {
      const distance = Math.abs(line - candidate);
      if (distance < bestX.distance) bestX = { delta: line - candidate, distance, line };
    }
  }
  let bestY = { delta: 0, distance: threshold, line: NaN };
  for (const candidate of candidatesY) {
    for (const line of yLines) {
      const distance = Math.abs(line - candidate);
      if (distance < bestY.distance) bestY = { delta: line - candidate, distance, line };
    }
  }
  const guides = [];
  if (bestX.line === bestX.line) guides.push({ axis: "x", value: bestX.line });
  if (bestY.line === bestY.line) guides.push({ axis: "y", value: bestY.line });
  return { dx: bestX.delta, dy: bestY.delta, guides };
}
function snapResize(layer, handle, targets, canvas, viewScale) {
  const result = { x: layer.x, y: layer.y, w: layer.w, h: layer.h };
  if (Math.abs(layer.rotation % 360) > 0.5) return { ...result, guides: [] };
  const threshold = SNAP_PIXELS / viewScale;
  const xLines = [0, canvas.width / 2, canvas.width];
  const yLines = [0, canvas.height / 2, canvas.height];
  for (const target of targets) {
    const bb = boundingBox([target]);
    xLines.push(bb.x, bb.x + bb.w / 2, bb.x + bb.w);
    yLines.push(bb.y, bb.y + bb.h / 2, bb.y + bb.h);
  }
  const guides = [];
  const snapAxis = (edge, lines, apply) => {
    let best = { delta: 0, distance: threshold, line: NaN };
    for (const line of lines) {
      const distance = Math.abs(line - edge);
      if (distance < best.distance) best = { delta: line - edge, distance, line };
    }
    if (best.line === best.line) {
      apply(best.delta, best.line);
      guides.push({ axis: lines === xLines ? "x" : "y", value: best.line });
    }
  };
  if (handle.includes("w")) {
    const edge = result.x;
    snapAxis(edge, xLines, (delta) => {
      result.x += delta;
      result.w = Math.max(8, result.w - delta);
    });
  } else if (handle.includes("e")) {
    const edge = result.x + result.w;
    snapAxis(edge, xLines, (delta) => {
      result.w = Math.max(8, result.w + delta);
    });
  }
  if (handle.includes("n")) {
    const edge = result.y;
    snapAxis(edge, yLines, (delta) => {
      result.y += delta;
      result.h = Math.max(8, result.h - delta);
    });
  } else if (handle.includes("s")) {
    const edge = result.y + result.h;
    snapAxis(edge, yLines, (delta) => {
      result.h = Math.max(8, result.h + delta);
    });
  }
  return { ...result, guides };
}
function resizeLayer(origin, handle, pointerX, pointerY, lockAspect) {
  const radians = origin.rotation * Math.PI / 180;
  const center = centerOf(origin);
  const hx = handle.includes("w") ? -1 : handle.includes("e") ? 1 : 0;
  const hy = handle.includes("n") ? -1 : handle.includes("s") ? 1 : 0;
  const local = rotatePoint(pointerX - center.x, pointerY - center.y, -radians);
  const oppositeLocal = { x: -hx * origin.w / 2, y: -hy * origin.h / 2 };
  const anchorWorld = {
    x: center.x + rotatePoint(oppositeLocal.x, oppositeLocal.y, radians).x,
    y: center.y + rotatePoint(oppositeLocal.x, oppositeLocal.y, radians).y
  };
  let width = origin.w;
  let height = origin.h;
  if (hx !== 0) width = Math.max(8, Math.abs(local.x - oppositeLocal.x));
  if (hy !== 0) height = Math.max(8, Math.abs(local.y - oppositeLocal.y));
  if (hx === 0 && hy === 0) return {};
  if (lockAspect) {
    const ratio = origin.w / origin.h;
    if (hx !== 0 && hy !== 0) {
      const byWidth = Math.max(width, height * ratio);
      width = byWidth;
      height = byWidth / ratio;
    } else if (hx !== 0) {
      height = width / ratio;
    } else {
      width = height * ratio;
    }
  }
  const newCenterLocal = { x: hx * width / 2, y: hy * height / 2 };
  const rotated = rotatePoint(newCenterLocal.x, newCenterLocal.y, radians);
  const centerWorld = { x: anchorWorld.x + rotated.x, y: anchorWorld.y + rotated.y };
  return {
    x: Math.round(centerWorld.x - width / 2),
    y: Math.round(centerWorld.y - height / 2),
    w: Math.round(width),
    h: Math.round(height)
  };
}

// src/canvas.ts
var HANDLE_SIZE = 7;
function checker(ctx, width, height, cell, offsetX, offsetY) {
  ctx.save();
  ctx.fillStyle = "#2a2a31";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#232329";
  const startX = (offsetX % (cell * 2) + cell * 2) % (cell * 2);
  const startY = (offsetY % (cell * 2) + cell * 2) % (cell * 2);
  for (let y = -startY; y < height + cell; y += cell) {
    for (let x = -startX; x < width + cell; x += cell) {
      const even = (Math.floor((x + startX) / cell) + Math.floor((y + startY) / cell)) % 2 === 0;
      if (even) continue;
      ctx.fillRect(x, y, cell, cell);
    }
  }
  ctx.restore();
}
function render(ctx, state, cssWidth, cssHeight) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  const dpr = window.devicePixelRatio || 1;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#17171b";
  ctx.fillRect(0, 0, cssWidth, cssHeight);
  const { view, canvas } = state;
  const origin = toScreen(view, 0, 0);
  const width = canvas.width * view.scale;
  const height = canvas.height * view.scale;
  ctx.save();
  ctx.beginPath();
  ctx.rect(origin.x, origin.y, width, height);
  ctx.clip();
  checker(ctx, cssWidth, cssHeight, 10, -origin.x, -origin.y);
  ctx.fillStyle = "#111114";
  ctx.fillRect(origin.x, origin.y, width, height);
  const ordered = [...state.layers].sort((a, b) => a.z - b.z);
  for (const layer of ordered) {
    if (!layer.visible || layer.opacity <= 0) continue;
    const image = layer.img;
    if (!image) continue;
    const center = toScreen(view, layer.x + layer.w / 2, layer.y + layer.h / 2);
    const drawWidth = layer.w * view.scale;
    const drawHeight = layer.h * view.scale;
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, layer.opacity));
    ctx.translate(center.x, center.y);
    if (layer.rotation) ctx.rotate(layer.rotation * Math.PI / 180);
    if (layer.flip_h || layer.flip_v) ctx.scale(layer.flip_h ? -1 : 1, layer.flip_v ? -1 : 1);
    try {
      ctx.drawImage(image, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);
    } catch (_error) {
    }
    ctx.restore();
  }
  ctx.restore();
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1;
  ctx.strokeRect(origin.x + 0.5, origin.y + 0.5, width, height);
  for (const layer of state.layers) {
    if (!state.selection.has(layer.id)) continue;
    const corners = layerCorners(layer).map((point) => toScreen(view, point.x, point.y));
    ctx.save();
    ctx.strokeStyle = "#4f9dff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let index = 1; index < corners.length; index += 1) ctx.lineTo(corners[index].x, corners[index].y);
    ctx.closePath();
    ctx.stroke();
    const handles = handlePoints(layer, view.scale).map((handle) => ({
      id: handle.id,
      ...toScreen(view, handle.x, handle.y)
    }));
    for (const handle of handles) {
      ctx.beginPath();
      if (handle.id === "rotate") {
        ctx.fillStyle = "#8b5cf6";
        ctx.arc(handle.x, handle.y, HANDLE_SIZE / 1.4, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(handle.x - HANDLE_SIZE / 2, handle.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
        ctx.strokeRect(handle.x - HANDLE_SIZE / 2, handle.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      }
    }
    ctx.restore();
  }
  if (state.guides.length) {
    ctx.save();
    ctx.strokeStyle = "#ff5fa2";
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 4]);
    for (const guide of state.guides) {
      ctx.beginPath();
      if (guide.axis === "x") {
        const x = toScreen(view, guide.value, 0).x;
        ctx.moveTo(x, 0);
        ctx.lineTo(x, cssHeight);
      } else {
        const y = toScreen(view, 0, guide.value).y;
        ctx.moveTo(0, y);
        ctx.lineTo(cssWidth, y);
      }
      ctx.stroke();
    }
    ctx.restore();
  }
  if (state.marquee) {
    const from = toScreen(view, state.marquee.x0, state.marquee.y0);
    const to = toScreen(view, state.marquee.x1, state.marquee.y1);
    ctx.save();
    ctx.fillStyle = "rgba(79,157,255,0.12)";
    ctx.strokeStyle = "rgba(79,157,255,0.8)";
    ctx.setLineDash([4, 3]);
    ctx.fillRect(from.x, from.y, to.x - from.x, to.y - from.y);
    ctx.strokeRect(from.x, from.y, to.x - from.x, to.y - from.y);
    ctx.restore();
  }
}

// src/editor.ts
var STYLE_ID = "icx-style";
var MIN_SCALE = 0.05;
var MAX_SCALE = 8;
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== void 0) node.textContent = text;
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
var Editor = class {
  constructor(input, callbacks) {
    this.selection = /* @__PURE__ */ new Set();
    this.view = { scale: 1, tx: 0, ty: 0 };
    this.guides = [];
    this.drag = { kind: "none" };
    this.reorder = null;
    this.spaceDown = false;
    this.history = [];
    this.historyIndex = -1;
    this.dirty = false;
    this.raf = 0;
    this.closed = false;
    this.onKeyDownBound = (event) => this.onKeyDown(event);
    this.loop = () => {
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
          marquee: this.drag.kind === "marquee" ? this.drag : null
        }, rect.width, rect.height);
      }
      this.raf = requestAnimationFrame(this.loop);
    };
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
    this.root.tabIndex = -1;
    this.root.style.outline = "none";
    this.root.addEventListener("pointerdown", (event) => {
      const target = event.target;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
      this.root.focus({ preventScroll: true });
    });
    this.root.focus({ preventScroll: true });
    this.ctx = this.canvasEl.getContext("2d");
    this.bindEvents();
    this.pushHistory();
    this.fitView();
    this.resize();
    this.refreshUI();
    this.loop();
  }
  buildHeader() {
    const head = el("div", "icx-head");
    head.appendChild(el("span", "icx-title", "\u56FE\u5C42\u5408\u6210\u5668"));
    this.hintEl = el("span", "icx-hint", this.stale ? "\u8F93\u5165\u5DF2\u53D8\u5316\uFF0C\u5DF2\u56DE\u9000\u9ED8\u8BA4\u5E03\u5C40" : "\u62D6\u52A8\u6446\u4F4D \xB7 \u89D2\u70B9\u7F29\u653E \xB7 Shift \u89E3\u9501\u6BD4\u4F8B \xB7 Ctrl+Z \u64A4\u9500");
    if (this.stale) this.hintEl.classList.add("warn");
    head.appendChild(this.hintEl);
    head.appendChild(el("span", "icx-spacer"));
    head.appendChild(el("span", "icx-sub", "\u6EDA\u8F6E\u7F29\u653E \xB7 \u7A7A\u683C/\u4E2D\u952E\u5E73\u79FB \xB7 \u65B9\u5411\u952E\u5FAE\u8C03 \xB7 Esc \u4FDD\u5B58\u5E76\u5173\u95ED"));
    return head;
  }
  buildFooter() {
    const foot = el("div", "icx-foot");
    const left = el("div", "icx-foot-side");
    const fit = el("button", "icx-mini", "Fit");
    fit.style.width = "36px";
    fit.title = "\u7F29\u653E\u5230\u9002\u5408\u7A97\u53E3";
    fit.onclick = () => {
      this.fitView();
      this.requestRender();
    };
    left.appendChild(fit);
    const zoomOut = el("button", "icx-mini", "\u2212");
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
    this.undoBtn = el("button", "icx-btn", "\u21B6 \u64A4\u9500");
    this.undoBtn.title = "\u64A4\u9500\uFF08Ctrl+Z\uFF09";
    this.undoBtn.onclick = () => this.undo();
    right.appendChild(this.undoBtn);
    this.redoBtn = el("button", "icx-btn", "\u21B7 \u91CD\u505A");
    this.redoBtn.title = "\u91CD\u505A\uFF08Ctrl+Shift+Z / Ctrl+Y\uFF09";
    this.redoBtn.onclick = () => this.redo();
    right.appendChild(this.redoBtn);
    const reload = el("button", "icx-btn", "\u91CD\u65B0\u52A0\u8F7D\u8F93\u5165");
    reload.onclick = () => this.reload();
    right.appendChild(reload);
    const reset = el("button", "icx-btn", "\u6062\u590D");
    reset.onclick = () => this.restore();
    right.appendChild(reset);
    const close = el("button", "icx-btn", "\u5173\u95ED");
    close.onclick = () => this.close(false);
    right.appendChild(close);
    const save = el("button", "icx-btn primary", "\u9501\u5B9A\u5E76\u4FDD\u5B58\u5E76\u8FD0\u884C");
    save.title = "\u4FDD\u5B58\u5E03\u5C40\u5E76\u7ACB\u5373\u8FD0\u884C\u672C\u8282\u70B9";
    save.onclick = () => this.close(true, true);
    right.appendChild(save);
    foot.appendChild(right);
    return foot;
  }
  bindEvents() {
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
  onKeyDown(event) {
    if (this.closed) return;
    const target = event.target;
    if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    const swallow = (action) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      action();
    };
    if (event.key === "Escape") {
      swallow(() => this.close(true));
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      swallow(() => event.shiftKey ? this.redo() : this.undo());
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
    const nudge = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step]
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
  selected() {
    return this.layers.filter((layer) => this.selection.has(layer.id));
  }
  pointer(event) {
    const rect = this.canvasEl.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    return { screenX, screenY, ...toCanvas(this.view, screenX, screenY) };
  }
  onPointerDown(event) {
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
          startAngle: Math.atan2(point.y - center.y, point.x - center.x) * 180 / Math.PI,
          origin: new Map(this.selected().map((layer) => [layer.id, layer.rotation]))
        };
        this.canvasEl.style.cursor = cursorForHandle("rotate", 0);
        return;
      }
      if (handle) {
        this.drag = {
          kind: "resize",
          handle,
          origin: new Map(this.selected().map((layer) => [layer.id, { ...layer }]))
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
        origin: new Map(this.selected().map((layer) => [layer.id, { x: layer.x, y: layer.y }]))
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
  updateCursor(event) {
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
  onPointerMove(event) {
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
        const angle = Math.atan2(point.y - center.y, point.x - center.x) * 180 / Math.PI;
        let rotation = base + (angle - this.drag.startAngle);
        if (event.shiftKey) rotation = Math.round(rotation / 15) * 15;
        layer.rotation = Math.round((rotation % 360 + 360) % 360 * 10) / 10;
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
        h: Math.abs(this.drag.y1 - this.drag.y0)
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
  onPointerUp(_event) {
    if (this.closed) return;
    if (this.drag.kind === "marquee" || this.drag.kind === "move" || this.drag.kind === "resize" || this.drag.kind === "rotate") {
      this.commit();
    }
    this.drag = { kind: "none" };
    this.guides = [];
    this.canvasEl.style.cursor = "";
    this.requestRender();
  }
  onWheel(event) {
    if (this.closed) return;
    event.preventDefault();
    const rect = this.canvasEl.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
    this.zoomAt(screenX, screenY, factor);
  }
  zoomAt(screenX, screenY, factor) {
    const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, this.view.scale * factor));
    if (next === this.view.scale) return;
    const before = toCanvas(this.view, screenX, screenY);
    this.view.scale = next;
    this.view.tx = screenX - before.x * next;
    this.view.ty = screenY - before.y * next;
    this.updateZoomLabel();
    this.requestRender();
  }
  zoomBy(factor) {
    const rect = this.canvasEl.getBoundingClientRect();
    this.zoomAt(rect.width / 2, rect.height / 2, factor);
  }
  fitView() {
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
  updateZoomLabel() {
    if (this.zoomEl) this.zoomEl.textContent = Math.round(this.view.scale * 100) + "%";
  }
  resize() {
    const rect = this.stage.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvasEl.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvasEl.height = Math.max(1, Math.round(rect.height * dpr));
    this.requestRender();
  }
  requestRender() {
    this.dirty = true;
  }
  pushHistory(initial = false) {
    const snapshot = {
      canvas: { ...this.canvas },
      layers: this.layers.map((layer) => ({ ...layer }))
    };
    if (!initial && this.historyIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.historyIndex + 1);
    }
    this.history.push(snapshot);
    if (this.history.length > 60) this.history.shift();
    this.historyIndex = this.history.length - 1;
  }
  commit() {
    this.pushHistory();
    this.refreshUI();
    this.requestRender();
  }
  undo() {
    if (this.historyIndex <= 0) return;
    this.historyIndex -= 1;
    this.restoreSnapshot(this.history[this.historyIndex]);
  }
  redo() {
    if (this.historyIndex >= this.history.length - 1) return;
    this.historyIndex += 1;
    this.restoreSnapshot(this.history[this.historyIndex]);
  }
  restoreSnapshot(snapshot) {
    const images = new Map(this.layers.map((layer) => [layer.id, layer.img]));
    const thumbs = new Map(this.layers.map((layer) => [layer.id, layer.thumb]));
    this.layers = snapshot.layers.map((layer) => ({ ...layer, img: images.get(layer.id), thumb: thumbs.get(layer.id) }));
    const ids = new Set(this.layers.map((layer) => layer.id));
    for (const id of [...this.selection]) if (!ids.has(id)) this.selection.delete(id);
    this.refreshUI();
    this.requestRender();
  }
  restore() {
    const open = this.history[0];
    if (!open) return;
    this.restoreSnapshot(open);
    this.history = [this.history[0]];
    this.historyIndex = 0;
  }
  updateHistoryButtons() {
    if (this.undoBtn) this.undoBtn.disabled = this.historyIndex <= 0;
    if (this.redoBtn) this.redoBtn.disabled = this.historyIndex >= this.history.length - 1;
  }
  refreshUI() {
    this.updateHistoryButtons();
    this.renderList();
    this.renderProps();
    if (this.hintEl) {
      this.hintEl.textContent = this.selection.size > 1 ? "\u5DF2\u9009 " + this.selection.size + " \u5C42\uFF1A\u62D6\u52A8\u6574\u4F53\u79FB\u52A8 \xB7 Shift \u70B9\u9009\u589E\u51CF" : "\u62D6\u52A8\u6446\u4F4D \xB7 \u89D2\u70B9\u7F29\u653E \xB7 Shift \u89E3\u9501\u6BD4\u4F8B \xB7 Ctrl+Z \u64A4\u9500";
    }
    this.updateZoomLabel();
  }
  renderList() {
    this.listEl.innerHTML = "";
    const ordered = [...this.layers].sort((a, b) => b.z - a.z);
    for (const layer of ordered) {
      const row = el("div", "icx-row" + (this.selection.has(layer.id) ? " sel" : ""));
      row.dataset.layerId = layer.id;
      const grip = el("span", "icx-grip", "\u28FF");
      grip.title = "\u62D6\u62FD\u8C03\u6574\u5C42\u7EA7";
      row.appendChild(grip);
      const thumb = el("img", "icx-thumb");
      if (layer.thumb) thumb.src = layer.thumb;
      thumb.title = layer.visible ? "\u70B9\u51FB\u5207\u6362\u663E\u9690" : "\u5DF2\u9690\u85CF\uFF0C\u70B9\u51FB\u663E\u793A";
      thumb.style.opacity = layer.visible ? "1" : "0.35";
      thumb.onclick = (event) => {
        event.stopPropagation();
        layer.visible = !layer.visible;
        this.commit();
      };
      row.appendChild(thumb);
      const meta = el("div");
      meta.appendChild(el("div", "icx-row-name", layer.name));
      meta.appendChild(el("div", "icx-row-sub", Math.round(layer.w) + "\xD7" + Math.round(layer.h) + " \xB7 " + Math.round(layer.opacity * 100) + "%"));
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
    if (!ordered.length) this.listEl.appendChild(el("div", "icx-empty", "\u6CA1\u6709\u56FE\u5C42"));
  }
  beginReorder(event, layer) {
    if (event.button !== 0) return;
    this.reorder = { id: layer.id, startY: event.clientY, active: false };
    const onMove = (moveEvent) => {
      if (!this.reorder) return;
      if (!this.reorder.active && Math.abs(moveEvent.clientY - this.reorder.startY) < 4) return;
      this.reorder.active = true;
      document.body.style.cursor = "grabbing";
      const dragged = this.listEl.querySelector(
        '.icx-row[data-layer-id="' + this.reorder.id + '"]'
      );
      dragged?.classList.add("dragging");
      this.markDropTarget(moveEvent.clientY);
    };
    const onUp = (upEvent) => {
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
  rows() {
    return Array.from(this.listEl.querySelectorAll(".icx-row"));
  }
  rowAt(y) {
    const rows = this.rows();
    if (!rows.length) return null;
    for (let index = 0; index < rows.length; index += 1) {
      const rect = rows[index].getBoundingClientRect();
      if (y < rect.top + rect.height / 2) return index;
    }
    return rows.length;
  }
  markDropTarget(y) {
    this.clearDropMarks();
    const rows = this.rows();
    const target = this.rowAt(y);
    if (target === null || !rows.length) return;
    const row = rows[Math.min(target, rows.length - 1)];
    row.classList.add(target >= rows.length ? "drop-after" : "drop-before");
  }
  clearDropMarks() {
    for (const row of this.rows()) row.classList.remove("drop-before", "drop-after", "dragging");
  }
  /** 列表是自顶向下（z 大在上），拖到第 row 个位置 = 放到对应 z。 */
  moveLayerToRow(layerId, row) {
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
  renderProps() {
    this.propsEl.innerHTML = "";
    const selected = this.selected();
    if (!selected.length) {
      this.propsEl.appendChild(el("div", "icx-empty", "\u672A\u9009\u4E2D\u56FE\u5C42\uFF1A\u70B9\u753B\u5E03\u6216\u5DE6\u680F\u9009\u62E9"));
      return;
    }
    const layer = selected[0];
    const isMulti = selected.length > 1;
    this.propsEl.appendChild(el("div", "icx-sub", isMulti ? "\u5DF2\u9009 " + selected.length + " \u5C42\uFF08\u7F16\u8F91\u7B2C\u4E00\u5C42\uFF09" : "\u56FE\u5C42\u5C5E\u6027"));
    const nameField = el("label", "icx-field");
    nameField.appendChild(el("span", "", "\u540D\u79F0"));
    const nameInput = el("input");
    nameInput.type = "text";
    nameInput.value = layer.name;
    nameInput.onchange = () => {
      layer.name = nameInput.value || layer.name;
      this.commit();
    };
    nameField.appendChild(nameInput);
    this.propsEl.appendChild(nameField);
    const numberRow = (label, key, step = 1) => {
      const wrap = el("label", "icx-field");
      wrap.appendChild(el("span", "", label));
      const input = el("input");
      input.type = "number";
      input.step = String(step);
      input.dataset.key = String(key);
      input.value = String(Math.round(layer[key] * 10) / 10);
      input.onchange = () => {
        const value = Number(input.value);
        if (!Number.isFinite(value)) return;
        for (const item of this.selected()) item[key] = key === "w" || key === "h" ? Math.max(8, value) : value;
        this.commit();
      };
      wrap.appendChild(input);
      this.propsEl.appendChild(wrap);
      return input;
    };
    const xy = el("div", "icx-pair");
    this.propsEl.appendChild(xy);
    const posRow = el("div", "icx-field");
    posRow.appendChild(el("span", "", "\u4F4D\u7F6E X/Y"));
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
    sizeRow.appendChild(el("span", "", "\u5C3A\u5BF8 W/H"));
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
    numberRow("\u5C42\u7EA7 Z", "z");
    numberRow("\u65CB\u8F6C \xB0", "rotation", 1);
    const aspect = el("label", "icx-field");
    aspect.appendChild(el("span", "", "\u9501\u5B9A\u6BD4\u4F8B"));
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
    visible.appendChild(el("span", "", "\u663E\u793A"));
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
    opacityField.appendChild(el("span", "", "\u4E0D\u900F\u660E\u5EA6"));
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
    flips.appendChild(el("span", "", "\u7FFB\u8F6C"));
    const flipWrap = el("div", "icx-pair");
    const flipH = el("button", "icx-btn", "\u6C34\u5E73 \u2194");
    flipH.onclick = () => {
      for (const item of this.selected()) item.flip_h = !item.flip_h;
      this.commit();
    };
    const flipV = el("button", "icx-btn", "\u5782\u76F4 \u2195");
    flipV.onclick = () => {
      for (const item of this.selected()) item.flip_v = !item.flip_v;
      this.commit();
    };
    flipWrap.appendChild(flipH);
    flipWrap.appendChild(flipV);
    flips.appendChild(flipWrap);
    this.propsEl.appendChild(flips);
    const sizeHint = el("div", "icx-sub", "\u539F\u56FE " + layer.naturalW + "\xD7" + layer.naturalH);
    this.propsEl.appendChild(sizeHint);
  }
  syncInputs() {
    const selected = this.selected()[0];
    if (!selected) return;
    const inputs = this.propsEl.querySelectorAll("input[data-key]");
    inputs.forEach((input) => {
      const element = input;
      const key = element.dataset.key;
      const value = selected[key];
      if (typeof value === "number") element.value = String(Math.round(value * 10) / 10);
    });
    const sub = this.listEl.querySelector(".icx-row.sel .icx-row-sub");
    if (sub) sub.textContent = Math.round(selected.w) + "\xD7" + Math.round(selected.h) + " \xB7 " + Math.round(selected.opacity * 100) + "%";
  }
  serialize() {
    const layers = [...this.layers].sort((a, b) => a.z - b.z).map((layer) => ({
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
      flip_v: layer.flip_v
    }));
    return {
      version: 2,
      canvas: { width: this.canvas.width, height: this.canvas.height },
      locked: true,
      fingerprint: this.fingerprint,
      layers
    };
  }
  async reload() {
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
  close(save, run = false) {
    if (this.closed) return;
    this.closed = true;
    cancelAnimationFrame(this.raf);
    window.removeEventListener("keydown", this.onKeyDownBound);
    this.root.remove();
    if (save) this.callbacks.save(this.serialize(), run);
    this.callbacks.close();
  }
  /** 外部数据刷新（例如节点重新执行后）。 */
  updateImages(layers, fingerprint, stale) {
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
};
function layerFromPayload(entry, saved, index) {
  const naturalWidth = Number(entry.width || saved?.w || 512);
  const naturalHeight = Number(entry.height || saved?.h || 512);
  return loadImage(viewURL(entry)).then((image) => ({
    id: "layer_" + index,
    index,
    name: saved?.name || "\u56FE\u5C42 " + (index + 1),
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
    thumb: entry.thumb
  }));
}

// src/index.ts
var NODE_TYPE = "ImageCompositorHelper";
var WIDGET_NAME = "layout_json";
function runNow(node) {
  const anyApp = app;
  try {
    if (typeof anyApp?.queuePrompt === "function") {
      anyApp.queuePrompt(0, 1);
      return true;
    }
  } catch (error) {
    console.warn("[ICX] queuePrompt \u8C03\u7528\u5931\u8D25", error);
  }
  const button = document.querySelector(
    "#queue-button, [data-testid='queue-button'], .queue-button"
  );
  if (button) {
    button.click();
    return true;
  }
  return false;
}
function buildContainer(node) {
  const container = document.createElement("div");
  container.style.cssText = "display:flex;flex-direction:column;gap:6px;padding:6px;box-sizing:border-box;width:100%;";
  const preview = document.createElement("img");
  preview.style.cssText = "width:100%;max-height:220px;object-fit:contain;border-radius:6px;background:#17171b;display:none;";
  container.appendChild(preview);
  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:8px;align-items:center;";
  const button = document.createElement("button");
  button.textContent = "\u6253\u5F00\u5408\u6210\u5668";
  button.style.cssText = "height:28px;padding:0 12px;border-radius:6px;border:1px solid #3a3a46;background:#2b6ee8;color:#fff;font-size:12px;cursor:pointer;";
  const status = document.createElement("span");
  status.textContent = "\u5148\u8FD0\u884C\u4E00\u6B21\u4EE5\u8F7D\u5165\u56FE\u5C42";
  status.style.cssText = "font-size:11px;color:#8d97ab;";
  row.appendChild(button);
  row.appendChild(status);
  container.appendChild(row);
  return { container, preview, button, status };
}
async function loadLayers(node) {
  const payload = node._icx?.payload ?? null;
  if (!payload || !payload.layers || !payload.layers.length) return null;
  const fromWidget = parseJSON(getWidgetValue(node, WIDGET_NAME));
  const saved = fromWidget?.layers?.length ? fromWidget : payload.layout;
  const savedLayers = Array.isArray(saved?.layers) ? saved.layers : [];
  const layers = [];
  for (let index = 0; index < payload.layers.length; index += 1) {
    const entry = payload.layers[index];
    const position = entry.index ?? index;
    const savedLayer = savedLayers.find((item) => Number(item?.index) === position) ?? savedLayers[position];
    const layer = await layerFromPayload(entry, savedLayer, position);
    layer.thumb = viewURL(entry);
    layers.push(layer);
  }
  const canvas = Array.isArray(payload.canvas) ? { width: Number(payload.canvas[0]) || 1024, height: Number(payload.canvas[1]) || 1024 } : { width: 1024, height: 1024 };
  return {
    canvas,
    layers,
    fingerprint: String(payload.fingerprint ?? ""),
    stale: Boolean(payload.stale?.[0])
  };
}
async function openEditor(node) {
  if (node._icx?.editor) return;
  const payload = node._icx?.payload;
  if (!payload) {
    node._icx.status.textContent = "\u8FD8\u6CA1\u6709\u6267\u884C\u7ED3\u679C\uFF1A\u5148\u70B9 Run \u8DD1\u4E00\u6B21";
    console.warn("[ICX] \u6CA1\u6709\u6267\u884C\u7ED3\u679C\uFF0C\u5148\u8FD0\u884C\u4E00\u6B21\u5DE5\u4F5C\u6D41");
    return;
  }
  const state = await loadLayers(node);
  if (!state) {
    node._icx.status.textContent = "\u56FE\u5C42\u6570\u636E\u4E3A\u7A7A\uFF1A\u68C0\u67E5\u8282\u70B9\u8F93\u51FA\u6216\u6D4F\u89C8\u5668\u63A7\u5236\u53F0";
    console.warn("[ICX] payload \u91CC\u6CA1\u6709 layers", payload);
    return;
  }
  if (!state.layers.length) {
    node._icx.status.textContent = "\u56FE\u5C42\u9884\u89C8\u6CA1\u751F\u6210\uFF1A\u770B ComfyUI \u63A7\u5236\u53F0\u65E5\u5FD7";
    console.warn("[ICX] layers \u4E3A\u7A7A\uFF0C\u53EF\u80FD\u662F\u9884\u89C8\u56FE\u4FDD\u5B58\u5931\u8D25", payload?.errors);
    return;
  }
  const editor = new Editor(state, {
    save: (layout, run) => {
      setWidgetValue(node, WIDGET_NAME, JSON.stringify(layout));
      if (!run) {
        node._icx.status.textContent = "\u5E03\u5C40\u5DF2\u4FDD\u5B58\uFF1A\u518D\u8FD0\u884C\u4E00\u6B21\u5373\u53EF\u5408\u6210";
        return;
      }
      const queued = runNow(node);
      node._icx.status.textContent = queued ? "\u5E03\u5C40\u5DF2\u4FDD\u5B58\uFF0C\u6B63\u5728\u8FD0\u884C\u2026" : "\u5E03\u5C40\u5DF2\u4FDD\u5B58\uFF1A\u8BF7\u70B9 Run \u8FD0\u884C";
    },
    reload: async () => {
      const fresh = await loadLayers(node);
      if (fresh) node._icx.status.textContent = "\u5DF2\u91CD\u65B0\u52A0\u8F7D " + fresh.layers.length + " \u5C42";
      return fresh;
    },
    close: () => {
      node._icx.editor = null;
    }
  });
  node._icx.editor = editor;
}
function setupNode(node) {
  if (node._icx) return;
  const { container, preview, button, status } = buildContainer(node);
  node._icx = { payload: null, editor: null, container, preview, button, status };
  node.addDOMWidget("icx_preview", "deepseek_compositor_ui", container, { serialize: false });
  hideWidget(findWidget(node, WIDGET_NAME));
  button.onclick = () => {
    openEditor(node).catch((error) => {
      status.textContent = "\u6253\u5F00\u5931\u8D25\uFF1A" + (error?.message ?? error);
      console.error("[ImageCompositorHelper]", error);
    });
  };
  const originalMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function(canvas, options) {
    const result = originalMenu?.apply(this, arguments);
    options.push({
      content: "\u6253\u5F00\u56FE\u5C42\u5408\u6210\u5668",
      callback: () => {
        openEditor(node).catch((error) => {
          status.textContent = "\u6253\u5F00\u5931\u8D25\uFF1A" + (error?.message ?? error);
          console.error("[ImageCompositorHelper]", error);
        });
      }
    });
    return result;
  };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function(output) {
    const result = originalExecuted?.apply(this, arguments);
    const payload = output;
    node._icx.payload = payload;
    console.log("[ICX] \u6267\u884C\u7ED3\u679C", payload);
    const count = payload?.layers?.length ?? 0;
    const failed = payload?.errors?.length ?? 0;
    if (!count) {
      status.textContent = failed ? "\u56FE\u5C42\u9884\u89C8\u4FDD\u5B58\u5931\u8D25\uFF1A" + payload.errors[0] : "\u6CA1\u6709\u6536\u5230\u56FE\u5C42\u6570\u636E\uFF08\u89C1\u63A7\u5236\u53F0\uFF09";
    } else if (payload?.stale?.[0]) {
      status.textContent = "\u8F93\u5165\u5DF2\u53D8\u5316\uFF1A\u5E03\u5C40\u5DF2\u56DE\u9000\u9ED8\u8BA4\uFF0C\u6253\u5F00\u53EF\u91CD\u65B0\u6446";
    } else {
      status.textContent = "\u5DF2\u8F7D\u5165 " + count + " \u5C42 \xB7 \u753B\u5E03 " + (payload?.canvas ?? []).join("\xD7");
    }
    if (payload?.preview) {
      preview.src = viewURL(payload.preview);
      preview.style.display = "block";
    }
    return result;
  };
}
app.registerExtension({
  name: "DeepSeekAPI.ImageCompositorHelper",
  nodeCreated(node) {
    const type = node?.comfyClass ?? node?.type;
    if (type !== NODE_TYPE) return;
    try {
      setupNode(node);
      console.log("[ICX] \u5408\u6210\u5668\u8282\u70B9\u5DF2\u6302\u8F7D", node?.id);
    } catch (error) {
      console.error("[ImageCompositorHelper] setup failed", error);
    }
  }
});
