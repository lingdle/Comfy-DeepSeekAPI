"""图层渲染（torch）：缩放、旋转、翻转、逐层 over 合成。

只在 ComfyUI 运行时用；torch 延迟导入，导入本模块本身不需要 torch。
"""

import hashlib
import math


def _torch():
    import torch

    return torch


def tensor_digest(tensor):
    """形状 + 32x32 缩略图的 sha1，用于布局指纹（换图即失效）。"""
    torch = _torch()
    frame = tensor[0] if tensor.dim() == 4 else tensor
    frame = frame.detach().float()
    x = frame.permute(2, 0, 1).unsqueeze(0)
    small = torch.nn.functional.adaptive_avg_pool2d(x, (32, 32))
    payload = ("%dx%d|" % (frame.shape[1], frame.shape[0])).encode("ascii")
    digest = hashlib.sha1(payload + small.cpu().numpy().tobytes())
    return digest.hexdigest()[:16]


def to_rgba(tensor):
    """任意 IMAGE（3 或 4 通道）→ [H, W, 4]，4 通道时第 4 通道当 alpha。"""
    torch = _torch()
    frame = tensor[0] if tensor.dim() == 4 else tensor
    frame = frame.float().clamp(0.0, 1.0)
    if frame.shape[-1] == 4:
        rgb, alpha = frame[..., :3], frame[..., 3:4]
    else:
        rgb = frame[..., :3]
        alpha = torch.ones_like(frame[..., :1])
    return torch.cat([rgb, alpha], dim=-1)


def resize_rgba(image, width, height):
    """双线性缩放；缩小超过 2 倍时先 area，避免锯齿。"""
    torch = _torch()
    height, width = max(1, int(height)), max(1, int(width))
    if image.shape[0] == height and image.shape[1] == width:
        return image
    x = image.permute(2, 0, 1).unsqueeze(0)
    shrink = max(x.shape[2] / height, x.shape[3] / width)
    if shrink > 2:
        x = torch.nn.functional.interpolate(x, size=(height, width), mode="area")
    else:
        x = torch.nn.functional.interpolate(
            x, size=(height, width), mode="bilinear", align_corners=False
        )
    return x.squeeze(0).permute(1, 2, 0)


def rotate_rgba(image, degrees):
    """绕中心旋转，返回 (旋转后的图, 新宽, 新高)；角度小时原样返回。"""
    torch = _torch()
    degrees = float(degrees) % 360.0
    if degrees < 1e-3 or 360.0 - degrees < 1e-3:
        return image, int(image.shape[1]), int(image.shape[0])

    height, width = int(image.shape[0]), int(image.shape[1])
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    out_w = int(math.ceil(abs(width * cos) + abs(height * sin)))
    out_h = int(math.ceil(abs(width * sin) + abs(height * cos)))

    theta = torch.tensor(
        [
            [
                [cos * out_w / width, sin * out_h / width, 0.0],
                [-sin * out_w / height, cos * out_h / height, 0.0],
            ]
        ],
        dtype=torch.float32,
        device=image.device,
    )
    grid = torch.nn.functional.affine_grid(
        theta, (1, 4, out_h, out_w), align_corners=False
    )
    x = image.permute(2, 0, 1).unsqueeze(0)
    sampled = torch.nn.functional.grid_sample(
        x, grid, mode="bilinear", padding_mode="zeros", align_corners=False
    )
    return sampled.squeeze(0).permute(1, 2, 0), out_w, out_h


def prepare_layer(image, layer):
    """按图层参数缩放/翻转/旋转，返回 (图, 放置左上角 x, y)。"""
    torch = _torch()
    width, height = int(layer["w"]), int(layer["h"])
    scaled = resize_rgba(image, width, height)
    if layer.get("flip_h"):
        scaled = torch.flip(scaled, dims=[1])
    if layer.get("flip_v"):
        scaled = torch.flip(scaled, dims=[0])
    rotated, rot_w, rot_h = rotate_rgba(scaled, layer.get("rotation", 0.0))
    center_x = layer["x"] + width / 2.0
    center_y = layer["y"] + height / 2.0
    return rotated, int(round(center_x - rot_w / 2.0)), int(round(center_y - rot_h / 2.0))


def composite(prepared, canvas_width, canvas_height):
    """prepared: [(rgba, x, y, opacity)]，按顺序 over 合成，返回 (rgb, alpha)。"""
    torch = _torch()
    device = prepared[0][0].device if prepared else "cpu"
    acc_rgb = torch.zeros((canvas_height, canvas_width, 3), device=device)
    acc_alpha = torch.zeros((canvas_height, canvas_width, 1), device=device)

    for image, x, y, opacity in prepared:
        if opacity <= 0:
            continue
        height, width = int(image.shape[0]), int(image.shape[1])
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(canvas_width, x + width), min(canvas_height, y + height)
        if x1 <= x0 or y1 <= y0:
            continue

        src = image[y0 - y : y1 - y, x0 - x : x1 - x]
        alpha = (src[..., 3:4] * float(opacity)).clamp(0.0, 1.0)
        premultiplied = src[..., :3] * alpha

        acc_rgb[y0:y1, x0:x1] = premultiplied + acc_rgb[y0:y1, x0:x1] * (1.0 - alpha)
        acc_alpha[y0:y1, x0:x1] = alpha + acc_alpha[y0:y1, x0:x1] * (1.0 - alpha)

    rgb = acc_rgb / acc_alpha.clamp_min(1e-6)
    return rgb.clamp(0.0, 1.0), acc_alpha.clamp(0.0, 1.0)


def to_pil(image, max_side=None):
    """float 图像（RGB 或 RGBA）→ PIL；可选先等比缩小。"""
    from PIL import Image

    array = (image.detach().float().clamp(0.0, 1.0).cpu().numpy() * 255.0).round()
    pil = Image.fromarray(array.astype("uint8"), mode="RGBA" if array.shape[-1] == 4 else "RGB")
    if max_side and max(pil.size) > max_side:
        pil = pil.copy()
        pil.thumbnail((max_side, max_side), Image.LANCZOS)
    return pil
