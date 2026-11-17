import { handlePoints, layerCorners, toScreen } from "./geometry";
import type { Guide, Layer, View } from "./types";

export interface RenderState {
  canvas: { width: number; height: number };
  layers: Layer[];
  view: View;
  selection: Set<string>;
  guides: Guide[];
  marquee: { x0: number; y0: number; x1: number; y1: number } | null;
}

const HANDLE_SIZE = 7;

function checker(ctx: CanvasRenderingContext2D, width: number, height: number, cell: number, offsetX: number, offsetY: number) {
  ctx.save();
  ctx.fillStyle = "#2a2a31";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#232329";
  const startX = ((offsetX % (cell * 2)) + cell * 2) % (cell * 2);
  const startY = ((offsetY % (cell * 2)) + cell * 2) % (cell * 2);
  for (let y = -startY; y < height + cell; y += cell) {
    for (let x = -startX; x < width + cell; x += cell) {
      const even = (Math.floor((x + startX) / cell) + Math.floor((y + startY) / cell)) % 2 === 0;
      if (even) continue;
      ctx.fillRect(x, y, cell, cell);
    }
  }
  ctx.restore();
}

export function render(ctx: CanvasRenderingContext2D, state: RenderState, cssWidth: number, cssHeight: number) {
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
    if (layer.rotation) ctx.rotate((layer.rotation * Math.PI) / 180);
    if (layer.flip_h || layer.flip_v) ctx.scale(layer.flip_h ? -1 : 1, layer.flip_v ? -1 : 1);
    try {
      ctx.drawImage(image, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);
    } catch (_error) {
      /* 图未就绪时跳过 */
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
      ...toScreen(view, handle.x, handle.y),
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
