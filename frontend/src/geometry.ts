import type { Guide, HandleId, Layer, View } from "./types";

export const HANDLE_TOLERANCE = 7;

const RESIZE_CURSORS: Record<string, string> = {
  n: "ns-resize",
  s: "ns-resize",
  e: "ew-resize",
  w: "ew-resize",
  nw: "nwse-resize",
  se: "nwse-resize",
  ne: "nesw-resize",
  sw: "nesw-resize",
};

const ROTATE_CURSOR =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'><path d='M12 4a8 8 0 1 1-7.4 5' fill='none' stroke='white' stroke-width='2' stroke-linecap='round'/><path d='M12 4V1L8 4.5 12 8' fill='white'/></svg>\") 12 12, crosshair";

/** 控制点光标要跟着图层旋转走，否则手感是反的。 */
export function cursorForHandle(handle: HandleId, rotation: number): string {
  if (handle === "rotate") return ROTATE_CURSOR;
  const baseCursor = RESIZE_CURSORS[handle] ?? "default";
  const angles: Record<string, number> = {
    e: 0,
    se: 45,
    s: 90,
    sw: 135,
    w: 180,
    nw: 225,
    n: 270,
    ne: 315,
  };
  const angle = (angles[handle] ?? 0) + rotation;
  const bucket = ((Math.round(angle / 45) % 8) + 8) % 8;
  return [
    "ew-resize",
    "nwse-resize",
    "ns-resize",
    "nesw-resize",
    "ew-resize",
    "nwse-resize",
    "ns-resize",
    "nesw-resize",
  ][bucket];
}
// 吸附带迟滞：进入阈值 5 屏幕像素，已吸住后放宽到 12 像素才脱开，避免指针微动就来回跳
export const SNAP_ENTER_PX = 5;
export const SNAP_EXIT_PX = 12;

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

export interface SnapState {
  x: number | null;
  y: number | null;
}

export interface SnapResult {
  dx: number;
  dy: number;
  guides: Guide[];
  state: SnapState;
}

export function emptySnapState(): SnapState {
  return { x: null, y: null };
}

function snapLineSets(targets: Layer[], canvas: { width: number; height: number }) {
  const xs = [0, canvas.width / 2, canvas.width];
  const ys = [0, canvas.height / 2, canvas.height];
  for (const target of targets) {
    const bb = boundingBox([target]);
    xs.push(bb.x, bb.x + bb.w / 2, bb.x + bb.w);
    ys.push(bb.y, bb.y + bb.h / 2, bb.y + bb.h);
  }
  const dedupe = (values: number[]) => {
    const seen = new Set<number>();
    const out: number[] = [];
    for (const value of values) {
      const key = Math.round(value * 100) / 100;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(key);
    }
    return out;
  };
  return { xs: dedupe(xs), ys: dedupe(ys) };
}

/** 单轴吸附：优先维持已锁定的线（迟滞），否则按 5px 进入阈值挑最近的一条。 */
function pickAxis(
  edges: number[],
  lines: number[],
  locked: number | null,
  viewScale: number,
): { delta: number; line: number | null } {
  if (locked !== null) {
    let best = { delta: 0, distance: Infinity };
    for (const edge of edges) {
      const delta = locked - edge;
      const distance = Math.abs(delta);
      if (distance < best.distance) best = { delta, distance };
    }
    if (best.distance * viewScale <= SNAP_EXIT_PX) {
      return { delta: Math.round(best.delta), line: locked };
    }
  }

  let best = { delta: 0, distance: Infinity, line: null as number | null };
  for (const edge of edges) {
    for (const line of lines) {
      const distance = Math.abs(line - edge);
      if (distance < best.distance) best = { delta: line - edge, distance, line };
    }
  }
  if (best.line !== null && best.distance * viewScale <= SNAP_ENTER_PX) {
    return { delta: Math.round(best.delta), line: best.line };
  }
  return { delta: 0, line: null };
}

/** 把移动中的包围盒吸附到画布与其他图层的中线/边线。 */
export function snapBox(
  box: { x: number; y: number; w: number; h: number },
  targets: Layer[],
  canvas: { width: number; height: number },
  viewScale: number,
  state: SnapState = { x: null, y: null },
): SnapResult {
  const { xs, ys } = snapLineSets(targets, canvas);
  const x = pickAxis([box.x, box.x + box.w / 2, box.x + box.w], xs, state.x, viewScale);
  const y = pickAxis([box.y, box.y + box.h / 2, box.y + box.h], ys, state.y, viewScale);

  const guides: Guide[] = [];
  if (x.line !== null) guides.push({ axis: "x", value: x.line });
  if (y.line !== null) guides.push({ axis: "y", value: y.line });

  return { dx: x.delta, dy: y.delta, guides, state: { x: x.line, y: y.line } };
}

/** 缩放时的吸附：只处理未旋转的图层，锚定对角边不动；同样带迟滞。 */
export function snapResize(
  layer: Layer,
  handle: HandleId,
  targets: Layer[],
  canvas: { width: number; height: number },
  viewScale: number,
  state: SnapState = { x: null, y: null },
): { x: number; y: number; w: number; h: number; guides: Guide[]; state: SnapState } {
  const result = { x: layer.x, y: layer.y, w: layer.w, h: layer.h };
  const reset: SnapState = { x: null, y: null };
  if (Math.abs(layer.rotation % 360) > 0.5) {
    return { ...result, guides: [], state: reset };
  }

  const { xs, ys } = snapLineSets(targets, canvas);
  const guides: Guide[] = [];
  const nextState: SnapState = { x: null, y: null };

  if (handle.includes("w")) {
    const pick = pickAxis([result.x], xs, state.x, viewScale);
    result.x += pick.delta;
    result.w = Math.max(8, result.w - pick.delta);
    nextState.x = pick.line;
    if (pick.line !== null) guides.push({ axis: "x", value: pick.line });
  } else if (handle.includes("e")) {
    const pick = pickAxis([result.x + result.w], xs, state.x, viewScale);
    result.w = Math.max(8, result.w + pick.delta);
    nextState.x = pick.line;
    if (pick.line !== null) guides.push({ axis: "x", value: pick.line });
  }

  if (handle.includes("n")) {
    const pick = pickAxis([result.y], ys, state.y, viewScale);
    result.y += pick.delta;
    result.h = Math.max(8, result.h - pick.delta);
    nextState.y = pick.line;
    if (pick.line !== null) guides.push({ axis: "y", value: pick.line });
  } else if (handle.includes("s")) {
    const pick = pickAxis([result.y + result.h], ys, state.y, viewScale);
    result.h = Math.max(8, result.h + pick.delta);
    nextState.y = pick.line;
    if (pick.line !== null) guides.push({ axis: "y", value: pick.line });
  }

  return { ...result, guides, state: nextState };
}

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
