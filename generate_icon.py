import math
from PIL import Image, ImageDraw, ImageFilter

def create_app_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background rounded rectangle with modern blue-indigo gradient
    padding = int(size * 0.06)
    corner_radius = int(size * 0.22)
    box = [padding, padding, size - padding, size - padding]

    # Create gradient base
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)

    for y in range(padding, size - padding):
        factor = (y - padding) / (size - 2 * padding)
        # Gradient from vibrant electric blue (#2563eb) to deep indigo/purple (#1e1b4b / #4f46e5)
        r = int(24 + factor * (37 - 24))
        g = int(99 + factor * (38 - 99))
        b = int(235 + factor * (200 - 235))
        grad_draw.line([(padding, y), (size - padding, y)], fill=(r, g, b, 255))

    # Mask with rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(box, radius=corner_radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # Subtle inner border / glow
    border_draw = ImageDraw.Draw(img)
    border_draw.rounded_rectangle(box, radius=corner_radius, outline=(255, 255, 255, 45), width=int(size * 0.015))

    # 2. Add glowing accent circular ring in center-top
    cx = size // 2
    cy = int(size * 0.48)

    # 3. Draw a modern stylized Downward Download Arrow + Media Arc
    # Media play arc / bracket at top
    arc_box = [int(size * 0.24), int(size * 0.18), int(size * 0.76), int(size * 0.70)]
    border_draw.arc(arc_box, start=200, end=340, fill=(255, 255, 255, 120), width=int(size * 0.025))

    # Download arrow shaft
    arrow_w = int(size * 0.12)
    arrow_top = int(size * 0.26)
    arrow_mid = int(size * 0.52)
    arrow_bottom = int(size * 0.68)
    head_w = int(size * 0.25)

    # Draw arrow stem
    stem_left = cx - arrow_w // 2
    stem_right = cx + arrow_w // 2
    border_draw.rounded_rectangle([stem_left, arrow_top, stem_right, arrow_mid], radius=int(arrow_w * 0.3), fill=(255, 255, 255, 255))

    # Draw arrow head (triangle)
    triangle = [
        (cx - head_w, arrow_mid - int(size * 0.02)),
        (cx + head_w, arrow_mid - int(size * 0.02)),
        (cx, arrow_bottom)
    ]
    border_draw.polygon(triangle, fill=(255, 255, 255, 255))

    # Rounded bottom tray / bracket representing destination disk/tray
    tray_y = int(size * 0.76)
    tray_w = int(size * 0.26)
    tray_h = int(size * 0.05)
    tray_depth = int(size * 0.08)

    tray_points = [
        (cx - tray_w, tray_y - tray_depth),
        (cx - tray_w, tray_y),
        (cx + tray_w, tray_y),
        (cx + tray_w, tray_y - tray_depth)
    ]
    border_draw.line(tray_points, fill=(255, 255, 255, 235), width=int(size * 0.035), joint="round")

    return img

if __name__ == "__main__":
    import os
    project_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(project_dir, "icon.png")
    ico_path = os.path.join(project_dir, "app_icon.ico")

    icon_256 = create_app_icon(256)
    icon_256.save(png_path, "PNG")

    # Save multi-resolution Windows .ico with native uncompressed DIBs
    # so Windows Explorer can render it at all DPI scales and views
    icon_256.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        bitmap_format="bmp"
    )
    print(f"Successfully generated {png_path} and {ico_path}!")
