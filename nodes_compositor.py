"""图层合成助手（ImageCompositorHelper，V3 schema）。

连线：autogrow 接受若干 IMAGE（4 通道把第 4 通道当 alpha），按索引叠成图层；
前端编辑器在画布上摆位置/大小/旋转/层级，锁定后写回 layout_json；
再次执行即按存档合成，输出 IMAGE(3 通道) + MASK + layout JSON。
"""

import json
import logging
import os
import uuid

from comfy_api.latest import io

from .core.compositor import (
    MAX_LAYERS,
    canvas_of,
    default_layout,
    fingerprint,
    layout_layers,
    layout_payload,
    parse_layout,
    sorted_slots,
)
from .core.friendly import guarded
from .core.render import (
    composite,
    prepare_layer,
    tensor_digest,
    to_pil,
    to_rgba,
)

LOG = logging.getLogger("DeepSeekAPI")

NODE_ID = "ImageCompositorHelper"

PREVIEW_SIDE = 1024  # 编辑器里每层缩略图的长边上限
COMPOSITE_PREVIEW_LIMIT = 4096  # 合成预览的上限：这个尺寸以内按原尺寸存，原生预览标注才等于画布


def _frame_size(tensor):
    """返回 (宽, 高)。ComfyUI 的 IMAGE 是 [B, H, W, C]，别把宽高读反。"""
    frame = tensor[0] if tensor.dim() == 4 else tensor
    return int(frame.shape[1]), int(frame.shape[0])


def _save_temp(image, prefix):
    """把 PIL 图存进 temp/，返回 ui.images 条目。"""
    import folder_paths

    directory = folder_paths.get_temp_directory()
    name = "%s_%s.png" % (prefix, uuid.uuid4().hex[:10])
    image.save(os.path.join(directory, name), compress_level=3)
    return {"filename": name, "subfolder": "", "type": "temp"}


class ImageCompositorHelperNode(io.ComfyNode):
    """按数组顺序叠图的画布合成器。"""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_ID,
            display_name="图层合成助手",
            category="DeepSeekAPI",
            # 输出就是合成结果，标记成输出节点：否则只连它一个时 ComfyUI 会报
            # “工作流未包含任何输出节点”，单节点 partial execution 也不认它
            is_output_node=True,
            description=(
                "把若干张带透明的图按数组顺序叠成一张合成图：节点上点「打开合成器」，"
                "在画布里拖位置、改大小、旋转、调层级与不透明度，锁定保存后执行即得结果。"
                "4 通道输入把第 4 通道当 alpha，3 通道按不透明处理；输出 3 通道 IMAGE + MASK + 布局 JSON。"
            ),
            search_aliases=[
                "compositor",
                "layer",
                "rgba",
                "composite",
                "图层",
                "合成",
                "拼图",
                "排版",
            ],
            inputs=[
                io.Autogrow.Input(
                    "images",
                    display_name="图层",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("image"),
                        prefix="image_",
                        min=0,
                        max=MAX_LAYERS,
                    ),
                    optional=True,
                    tooltip=(
                        "按 image_0 → image_7 的顺序从底到顶叠放；可有空位。"
                        "4 通道当 alpha，3 通道按不透明"
                    ),
                ),
                io.Int.Input(
                    "canvas_width",
                    default=0,
                    min=0,
                    max=8192,
                    step=64,
                    tooltip="画布宽度；0 = 用存档里的画布，再没有就用第一张图的尺寸",
                    advanced=True,
                ),
                io.Int.Input(
                    "canvas_height",
                    default=0,
                    min=0,
                    max=8192,
                    step=64,
                    tooltip="画布高度；0 = 用存档里的画布，再没有就用第一张图的尺寸",
                    advanced=True,
                ),
                io.String.Input(
                    "layout_json",
                    default="",
                    multiline=True,
                    placeholder="由合成器自动写入，一般不用手改",
                    tooltip="布局存档 JSON（每层的 x / y / z / w / h / 旋转 / 不透明度）；解析失败会回退默认布局",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Image.Output(
                    display_name="image",
                    tooltip="合成结果，3 通道（透明度在 mask 里）",
                ),
                io.Mask.Output(
                    display_name="mask",
                    tooltip="整幅画布的合成 alpha",
                ),
                io.String.Output(
                    display_name="layout",
                    tooltip="本次实际使用的布局 JSON（每层 x / y / z / w / h 等）",
                ),
            ],
        )

    @classmethod
    @guarded
    def execute(
        cls,
        images=None,
        canvas_width=0,
        canvas_height=0,
        layout_json="",
    ) -> io.NodeOutput:
        tensors = sorted_slots(images)
        if not tensors:
            raise ValueError("图层输入为空：请至少把一张图接到「图层」上")

        if len(tensors) > MAX_LAYERS:
            LOG.warning("图层超过 %d 个，多余部分已忽略", MAX_LAYERS)
            tensors = tensors[:MAX_LAYERS]

        sizes = [_frame_size(tensor) for tensor in tensors]
        digests = [tensor_digest(tensor) for tensor in tensors]
        fp = fingerprint(
            [(index, height, width, digests[index]) for index, (width, height) in enumerate(sizes)]
        )

        layout = parse_layout(layout_json)
        matched = bool(layout) and layout.get("fingerprint") == fp
        layers, stored_ok = layout_layers(layout, sizes) if matched else ([], False)
        stale = not stored_ok

        explicit = (
            (int(canvas_width), int(canvas_height))
            if int(canvas_width) > 0 and int(canvas_height) > 0
            else None
        )
        canvas = canvas_of(layout if stored_ok else None, explicit or sizes[0])
        if not stored_ok:
            layout = default_layout(sizes, canvas)
            layers, _ = layout_layers(layout, sizes)

        prepared = []
        for layer in layers:
            tensor = tensors[layer["index"]]
            if not layer["visible"] or layer["opacity"] <= 0:
                continue
            image, x, y = prepare_layer(to_rgba(tensor), layer)
            prepared.append((image, x, y, layer["opacity"]))

        rgb, alpha = composite(prepared, canvas[0], canvas[1])

        layer_entries = []
        errors = []
        names = []
        for index, tensor in enumerate(tensors):
            names.append("图层 %d" % (index + 1))
            width, height = sizes[index]
            try:
                entry = _save_temp(to_pil(to_rgba(tensor), PREVIEW_SIDE), "rgba_layer_%d" % index)
            except Exception as exc:  # pragma: no cover - 预览失败不影响合成
                LOG.exception("图层 %d 预览保存失败：%s", index, exc)
                errors.append("layer %d: %s" % (index, exc))
                entry = None
            if entry:
                entry.update({"index": index, "width": width, "height": height})
                layer_entries.append(entry)

        for layer in layers:
            layer["name"] = names[layer["index"]]

        effective = layout_payload(layers, canvas, fp)
        preview = None
        try:
            import torch

            preview = _save_temp(
                to_pil(torch.cat([rgb, alpha], dim=-1), COMPOSITE_PREVIEW_LIMIT),
                "rgba_composite",
            )
        except Exception as exc:  # pragma: no cover - 合成预览失败不影响输出
            LOG.exception("合成预览保存失败：%s", exc)
            errors.append("preview: %s" % exc)

        ui = {
            "layers": layer_entries,
            "canvas": [canvas[0], canvas[1]],
            "fingerprint": fp,
            "stale": [stale],
            "layout": effective,
        }
        if preview:
            # 走标准 images 通道：ComfyUI 自己渲染缩略图，前端不再自己拼 /view 地址
            ui["images"] = [preview]
        if errors:
            ui["errors"] = errors

        LOG.info(
            "图层合成：%d 层，画布 %dx%d，存档=%s，预览=%s",
            len(prepared),
            canvas[0],
            canvas[1],
            "回退默认" if stale else "命中",
            preview.get("filename") if preview else "无",
        )

        image_out = rgb.unsqueeze(0)
        mask_out = alpha[..., 0]
        layout_text = json.dumps(effective, ensure_ascii=False, separators=(",", ":"))

        try:
            return io.NodeOutput(image_out, mask_out, layout_text, ui=ui)
        except TypeError:  # pragma: no cover - 老版本 io.NodeOutput 不支持 ui
            return io.NodeOutput(image_out, mask_out, layout_text)
