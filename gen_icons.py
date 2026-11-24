"""生成 PWA 图标（纯 PIL，不依赖外部素材）"""
from pathlib import Path

from PIL import Image, ImageDraw


def make_icon(size, out_path):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角背景
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(23, 26, 33, 255))

    # 内圈
    pad = int(size * 0.18)
    d.rounded_rectangle(
        [pad, pad, size - pad - 1, size - pad - 1],
        radius=int(size * 0.13),
        outline=(59, 130, 246, 255),
        width=max(2, int(size * 0.022)),
    )

    # K 线柱（4 根，红绿交替）
    n = 4
    bw = int(size * 0.10)
    gap = int(size * 0.055)
    total = n * bw + (n - 1) * gap
    x0 = (size - total) // 2

    heights = [0.34, 0.52, 0.40, 0.68]
    colors = [(239, 68, 68, 255), (34, 197, 94, 255),
              (239, 68, 68, 255), (34, 197, 94, 255)]

    base_y = size - pad - int(size * 0.10)
    for i in range(n):
        x = x0 + i * (bw + gap)
        h = int((size - 2 * pad - int(size * 0.16)) * heights[i])
        y = base_y - h
        d.rounded_rectangle([x, y, x + bw, base_y], radius=max(2, bw // 5),
                            fill=colors[i])
        # 影线
        cx = x + bw // 2
        d.line([cx, y - int(size * 0.045), cx, y], fill=colors[i],
               width=max(1, int(size * 0.014)))

    img.save(out_path, "PNG")
    print(f"  {out_path} ({size}x{size})")


if __name__ == "__main__":
    web = Path(__file__).resolve().parent / "web"
    web.mkdir(exist_ok=True)
    make_icon(192, web / "icon-192.png")
    make_icon(512, web / "icon-512.png")
    # apple-touch-icon
    make_icon(180, web / "apple-touch-icon.png")
    print("done")
