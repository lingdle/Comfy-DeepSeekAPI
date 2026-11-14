"""IMAGE 张量 → data URL（JPEG），默认按最省钱参数压缩。"""

import base64
import io


def _to_numpy(tensor):
    if hasattr(tensor, "detach"):
        tensor = tensor.detach()
    if hasattr(tensor, "cpu"):
        tensor = tensor.cpu()
    if hasattr(tensor, "numpy"):
        return tensor.numpy()
    return tensor


def count_batch(tensor):
    """返回该 IMAGE 输入里包含的图片张数（不实际解码）。"""
    if tensor is None:
        return 0
    shape = getattr(tensor, "shape", None)
    if shape is None:
        return 0
    if len(shape) <= 3:
        return 1
    return int(shape[0])


def tensor_to_data_urls(tensor, max_images=5, max_side=1024, quality=85):
    """把 IMAGE([B,H,W,C], 0..1) 转成若干 JPEG data URL。

    - max_images: 最多取几张（batch 超出部分丢弃）
    - max_side:   长边上限，默认 1024（单图 token 上限 1024，再大不加分）
    - quality:    JPEG 质量，默认 85（体积与画质平衡）
    """
    try:
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - ComfyUI 一定带这两个包
        raise RuntimeError("缺少 numpy 或 Pillow，无法处理图片：%s" % exc)

    array = _to_numpy(tensor)
    if array.ndim == 2:
        array = array[None, :, :, None]
    elif array.ndim == 3:
        array = array[None]

    limit = max(0, int(max_images))
    if limit == 0:
        return []

    urls = []
    for index in range(min(int(array.shape[0]), limit)):
        frame = np.clip(array[index], 0.0, 1.0) * 255.0
        frame = frame.astype(np.uint8)
        if frame.ndim == 3 and frame.shape[2] == 1:
            frame = frame[:, :, 0]

        image = Image.fromarray(frame)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image = ImageOps.contain(image, (int(max_side), int(max_side)), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=int(quality), optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        urls.append("data:image/jpeg;base64," + encoded)

    return urls

