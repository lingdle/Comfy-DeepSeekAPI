import type { Guide, HandleId, Layer, View } from "./types";

export const HANDLE_TOLERANCE = 7;
const SNAP_PIXELS = 6;

export function toScreen(view: View, x: number, y: number) {
  return { x: x * view.scale + view.tx, y: y * view.scale + view.ty };
}

export function toCanvas(view: View, x: number, y: number) {
  return { x: (x - view.tx) / view.scale, y: (y - view.ty) / view.scale };
}

export function centerOf(layer: Layer) {
  return { x: layer.x + layer.w / 2, y: layer.y + layer.h / 2 };
}

export function rotatePoint(x: number, y: number, radians: number) {
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return { x: x * cos - y * sin, y: x * sin + y * cos };
}

export function layerCorners(layer: Layer) {
  const radians = (layer.rotation * Math.PI) / 180;
  const center = centerOf(layer);
  const hw = layer.w / 2;
  const hh = layer.h / 2;
  return [
    { x: -hw, y: -hh },
    { x: hw, y: -hh },
    { x: hw, y: hh },
    { x: -hw, y: hh },
  ].map((point) => {
    const rotated = rotatePoint(point.x, point.y, radians);
    return { x: center.x + rotated.x, y: center.y + rotated.y };
  });
}

export function hitLayer(layer: Layer, x: number, y: number) {
  const center = centerOf(layer);
  const radians = (-layer.rotation * Math.PI) / 180;
  const local = rotatePoint(x - center.x, y - center.y, radians);
  return Math.abs(local.x) <= layer.w / 2 && Math.abs(local.y) <= layer.h / 2;
}

export function handlePoints(layer: Layer, viewScale: number) {
  const radians = (layer.rotation * Math.PI) / 180;
  const center = centerOf(layer);
  const hw = layer.w / 2;
  const hh = layer.h / 2;
  const offset = 34 / viewScale;
  const spots: Array<{ id: HandleId; x: number; y: number }> = [
    { id: "nw", x: -hw, y: -hh },
    { id: "n", x: 0, y: -hh },
    { id: "ne", x: hw, y: -hh },
    { id: "e", x: hw, y: 0 },
    { id: "se", x: hw, y: hh },
    { id: "s", x: 0, y: hh },
    { id: "sw", x: -hw, y: hh },
    { id: "w", x: -hw, y: 0 },
    { id: "rotate", x: 0, y: -hh - offset },
  ];
  return spots.map((spot) => {
    const rotated = rotatePoint(spot.x, spot.y, radians);
    return { id: spot.id, x: center.x + rotated.x, y: center.y + rotated.y };
  });
}

export function hitHandle(layer: Layer, x: number, y: number, viewScale: number): HandleId | null {
  const tolerance = HANDLE_TOLERANCE / viewScale;
  for (const handle of handlePoints(layer, viewScale)) {
    if (Math.abs(handle.x - x) <= tolerance && Math.abs(handle.y - y) <= tolerance) {
      return handle.id;
    }
  }
  return null;
}

export function boundingBox(layers: Layer[]) {
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

export function intersects(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

export interface SnapResult {
  dx: number;
  dy: number;
  guides: Guide[];
}

/** 把移动中的包围盒吸附到画布与其他图层的中线/边线。 */
export function snapBox(
  box: { x: number; y: number; w: number; h: number },
  targets: Layer[],
  canvas: { width: number; height: number },
  viewScale: number,
): SnapResult {
  const threshold = SNAP_PIXELS / viewScale;
  const xLines: number[] = [0, canvas.width / 2, canvas.width];
  const yLines: number[] = [0, canvas.height / 2, canvas.height];
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

  const guides: Guide[] = [];
  if (bestX.line === bestX.line) guides.push({ axis: "x", value: bestX.line });
  if (bestY.line === bestY.line) guides.push({ axis: "y", value: bestY.line });
  return { dx: bestX.delta, dy: bestY.delta, guides };
}

/** 拖控制点：对角为锚点，keep_aspect 时按比例缩放。 */
export function resizeLayer(
  origin: Layer,
  handle: HandleId,
  pointerX: number,
  pointerY: number,
  lockAspect: boolean,
): Partial<Layer> {
  const radians = (origin.rotation * Math.PI) / 180;
  const center = centerOf(origin);
  const hx = handle.includes("w") ? -1 : handle.includes("e") ? 1 : 0;
  const hy = handle.includes("n") ? -1 : handle.includes("s") ? 1 : 0;
  const local = rotatePoint(pointerX - center.x, pointerY - center.y, -radians);
  const oppositeLocal = { x: (-hx * origin.w) / 2, y: (-hy * origin.h) / 2 };
  const anchorWorld = {
    x: center.x + rotatePoint(oppositeLocal.x, oppositeLocal.y, radians).x,
    y: center.y + rotatePoint(oppositeLocal.x, oppositeLocal.y, radians).y,
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

  const newCenterLocal = { x: (hx * width) / 2, y: (hy * height) / 2 };
  const rotated = rotatePoint(newCenterLocal.x, newCenterLocal.y, radians);
  const centerWorld = { x: anchorWorld.x + rotated.x, y: anchorWorld.y + rotated.y };
  return {
    x: Math.round(centerWorld.x - width / 2),
    y: Math.round(centerWorld.y - height / 2),
    w: Math.round(width),
    h: Math.round(height),
  };
}
