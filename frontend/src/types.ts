export interface Layer {
  id: string;
  index: number;
  name: string;
  x: number;
  y: number;
  z: number;
  w: number;
  h: number;
  rotation: number;
  opacity: number;
  visible: boolean;
  keep_aspect: boolean;
  flip_h: boolean;
  flip_v: boolean;
  naturalW: number;
  naturalH: number;
  img?: HTMLImageElement;
  thumb?: string;
}

export interface CanvasSize {
  width: number;
  height: number;
}

export interface Snapshot {
  canvas: CanvasSize;
  layers: Layer[];
}

export interface View {
  scale: number;
  tx: number;
  ty: number;
}

export interface ExecLayer {
  filename: string;
  subfolder?: string;
  type?: string;
  index?: number;
  width?: number;
  height?: number;
}

export interface ExecPayload {
  layers?: ExecLayer[];
  preview?: ExecLayer;
  canvas?: number[];
  fingerprint?: string;
  stale?: boolean[];
  layout?: any;
  errors?: string[];
}

export type HandleId =
  | "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "rotate";

export interface Guide {
  axis: "x" | "y";
  value: number;
}

export type DragMode =
  | { kind: "none" }
  | { kind: "move"; startX: number; startY: number; origin: Map<string, { x: number; y: number }> }
  | { kind: "resize"; handle: HandleId; origin: Map<string, Layer> }
  | { kind: "rotate"; startAngle: number; origin: Map<string, number> }
  | { kind: "marquee"; x0: number; y0: number; x1: number; y1: number }
  | { kind: "pan"; tx: number; ty: number; px: number; py: number };
