import hashlib
from io import BytesIO
from typing import Optional, Tuple, Union
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps

import config


Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]
FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
MAX_PIXELS = config.MAX_PIXELS


@dataclass(frozen=True)
class GlowStyle:
    color: tuple[int, int, int, int] = (0, 204, 254, 255)
    radii: tuple[int, int, int] = (20, 40, 80)


@dataclass(frozen=True)
class TextRun:
    text: str
    font: FontType
    width: int


@dataclass(slots=True, frozen=True)
class TextDrawSpec:
    position: Tuple[float, float]
    text: str
    font: FontType
    fill_color: Color
    anchor: str = "lt"
    outline_color: Optional[Color] = None
    stroke_width: int = 0

    def apply(self, ctx: ImageDraw.ImageDraw) -> None:
        """Render this text onto the given ImageDraw context."""
        ctx.text(
            xy=self.position,
            text=self.text,
            fill=self.fill_color,
            font=self.font,
            anchor=self.anchor,
            stroke_width=self.stroke_width,
            stroke_fill=self.outline_color,
        )


def hex_to_rgb(s: Optional[str], default: tuple[int, int, int]) -> tuple[int, int, int]:
    """Parse '#RRGGBB' -> (r,g,b). Returns default on None/invalid."""
    if not s or not isinstance(s, str) or len(s) != 7 or not s.startswith("#"):
        return default
    try:
        return tuple(int(s[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except Exception:
        return default


def flatten_rgba_to_rgb(img: Image.Image, bg=(0, 0, 0)) -> Image.Image:
    """Flatten RGBA onto a solid background for JPEG output."""
    if img.mode not in ("RGBA", "LA"):
        return img.convert("RGB")
    bg_img = Image.new("RGB", img.size, bg)
    bg_img.paste(img, mask=img.split()[-1])
    return bg_img


def sniff_ext_and_mime(
    _fmt: str, _has_alpha: bool, prefer_webp: bool
) -> tuple[str, str]:
    """Choose output container. Favor WebP, else JPEG."""
    if prefer_webp:
        return ("webp", "image/webp")
    return ("jpg", "image/jpeg")


def safe_open(raw: bytes) -> Image.Image:
    """Safely open uploaded image; guard size, normalize EXIF orientation, use first frame."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    img = Image.open(BytesIO(raw))
    try:
        if getattr(img, "is_animated", False):
            img.seek(0)
    except Exception:
        pass
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def encode_webp(img: Image.Image, *, lossless: bool, quality: int = 85) -> bytes:
    out = BytesIO()
    params = {"format": "WEBP", "method": 6}  # literal instead of dict()
    if lossless:
        params["lossless"] = True
    else:
        params["quality"] = quality
    img.save(out, **params)
    return out.getvalue()


def encode_jpeg(img: Image.Image, *, quality: int = 85) -> bytes:
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_font(size: int):
    candidates = config.REGULAR_FONT_PATH
    if not isinstance(candidates, (list, tuple)):
        candidates = [candidates]

    for fp in candidates:
        try:
            return ImageFont.truetype(str(fp), size)
        except OSError as e:
            print(f"failed to load font {fp}: {e}")
            continue
    print("falling back to default font")
    return ImageFont.load_default()


# pylint: disable=too-many-arguments
def _build_glow_layer(
    *,
    base_size: tuple[int, int],
    x: int,
    y: int,
    runs: list[TextRun],
    style: GlowStyle,
    radius: int,
) -> Image.Image:
    layer = Image.new("RGBA", base_size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    cx = x
    for run in runs:
        ld.text((cx, y), run.text, font=run.font, fill=style.color)
        cx += run.width
    return layer.filter(ImageFilter.GaussianBlur(radius))


def _measure_text(
    draw: ImageDraw.ImageDraw, text: str, font: FontType
) -> tuple[int, int]:
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return (r - l), (b - t)


def _find_max_font_size(
    draw: ImageDraw.ImageDraw, prefix: str, suffix: str, max_width: int
) -> int:
    font_size = 1
    while True:
        f = _load_font(font_size)
        total_w, _ = _measure_text(draw, prefix + suffix, f)
        if total_w > max_width * 0.5:
            font_size = max(1, font_size - 1)
            break
        font_size += 1
    return font_size


# --- Glow Image Functions ---
# pylint: disable=too-many-arguments
def draw_text(
    ctx: ImageDraw.ImageDraw,
    position: Tuple[float, float],
    *,
    text: str,
    font: FontType,
    fill_color: Color,
    anchor: str = "lt",
    outline_color: Optional[Color] = None,
    stroke_width: int = 0,
) -> TextDrawSpec:
    spec = TextDrawSpec(
        position=position,
        text=text,
        font=font,
        fill_color=fill_color,
        anchor=anchor,
        outline_color=outline_color,
        stroke_width=stroke_width,
    )
    spec.apply(ctx)
    return spec


# pylint: disable=too-many-locals
def make_multiline_glow(
    template_path: str,
    lines: list[
        list[tuple[str, str]]
    ],  # list of lines, each a list of (text, font_path)
    max_font_size: int = 50,
    glow_radii: tuple[int, int, int] = (20, 40, 80),
    v_pad: int = 8,  # vertical padding between lines
) -> BytesIO:
    base = Image.open(template_path).convert("RGBA")
    w, h = base.size
    draw = ImageDraw.Draw(base)

    # 1) Autoscale: find a size that fits every line under 50% width
    chosen = max_font_size
    while chosen > 8:
        too_wide = False
        for line in lines:
            fnts = [ImageFont.truetype(str(fp), chosen) for _, fp in line]
            total_w = sum(
                draw.textlength(txt, font=f) for (txt, _), f in zip(line, fnts)
            )
            if total_w > w * 0.50:
                too_wide = True
                break
        if not too_wide:
            break
        chosen -= 2

    fonts_list = [
        [ImageFont.truetype(str(fp), chosen) for _, fp in line] for line in lines
    ]
    widths_list = [
        [draw.textlength(txt, font=f) for (txt, _), f in zip(line, fonts_list[i])]
        for i, line in enumerate(lines)
    ]
    line_heights = [
        max(f.getmetrics()[0] + f.getmetrics()[1] for f in fonts_list[i])
        for i in range(len(lines))
    ]

    # 3) Compute total text-block height & center start-Y
    total_h = sum(line_heights) + v_pad * (len(lines) - 1)
    y0 = (h - total_h) // 2

    # 4) Build glow layer
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for r in glow_radii:
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        y = y0
        for i, line in enumerate(lines):
            x = (w - sum(widths_list[i])) // 2
            for (txt, _), f, seg_w in zip(line, fonts_list[i], widths_list[i]):
                ld.text((x, y), txt, font=f, fill=(0, 204, 254, 255))
                x += seg_w
            y += line_heights[i] + v_pad
        glow = ImageChops.add(glow, layer.filter(ImageFilter.GaussianBlur(r)))

    # 5) Composite & draw crisp text
    combined = ImageChops.add(base, glow)
    fd = ImageDraw.Draw(combined)
    y = y0
    for i, line in enumerate(lines):
        x = (w - sum(widths_list[i])) // 2
        for (txt, _), f, seg_w in zip(line, fonts_list[i], widths_list[i]):
            fd.text((x, y), txt, font=f, fill=(255, 255, 255, 255))
            x += seg_w
        y += line_heights[i] + v_pad

    buf = BytesIO()
    combined.save(buf, "PNG")
    buf.seek(0)
    return buf


# pylint: disable=too-many-locals#
def make_glow_image(template_path: str, *, prefix: str, suffix: str) -> BytesIO:
    base = Image.open(template_path).convert("RGBA")
    w, h = base.size
    draw = ImageDraw.Draw(base)

    font_size = _find_max_font_size(draw, prefix, suffix, w)
    font_reg = _load_font(font_size)
    font_bi = _load_font(font_size)

    pw, ph = _measure_text(draw, prefix, font_reg)
    sw, sh = _measure_text(draw, suffix, font_bi)
    x = (w - (pw + sw)) // 2
    y = (h - max(ph, sh)) // 2

    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    style = GlowStyle()
    pw, ph = _measure_text(draw, prefix, font_reg)
    sw, sh = _measure_text(draw, suffix, font_bi)
    runs = [
        TextRun(prefix, font_reg, pw),
        TextRun(suffix, font_bi, sw),
    ]
    for radius in style.radii:
        glow = ImageChops.add(
            glow,
            _build_glow_layer(
                base_size=base.size,
                x=x,
                y=y,
                runs=runs,
                style=style,
                radius=radius,
            ),
        )

    combined = ImageChops.add(base, glow)
    final = ImageDraw.Draw(combined)
    final.text((x, y), prefix, font=font_reg, fill=(255, 255, 255, 255))
    final.text((x + pw, y), suffix, font=font_bi, fill=(255, 255, 255, 255))

    buf = BytesIO()
    combined.save(buf, format="PNG")
    buf.seek(0)
    return buf


# pylint: disable=too-many-locals
def make_glow_image_segments(
    template_path: str, segments: list[tuple[str, str]], font_size: int = 72
) -> BytesIO:
    """
    segments: List of (text, font_path) tuples.
    """
    base = Image.open(template_path).convert("RGBA")
    w, h = base.size
    # Preload fonts and measure widths
    dummy = ImageDraw.Draw(base)
    fonts = [ImageFont.truetype(str(fp), font_size) for _, fp in segments]
    widths = [dummy.textlength(txt, font=f) for (txt, _), f in zip(segments, fonts)]
    total_w = sum(widths)
    # Center horizontally, and vertically middle
    x0 = (w - total_w) // 2
    y0 = (h - font_size) // 2

    # Build a glow layer
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for radius in (20, 40, 80):
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        x = x0
        for (txt, _), f in zip(segments, fonts):
            ld.text((x, y0), txt, font=f, fill=(0, 204, 254, 255))
            x += dummy.textlength(txt, font=f)
        glow = ImageChops.add(glow, layer.filter(ImageFilter.GaussianBlur(radius)))

    # Composite and draw white text
    combined = ImageChops.add(base, glow)
    fd = ImageDraw.Draw(combined)
    x = x0
    for (txt, _), f in zip(segments, fonts):
        fd.text((x, y0), txt, font=f, fill=(255, 255, 255, 255))
        x += dummy.textlength(txt, font=f)

    buf = BytesIO()
    combined.save(buf, "PNG")
    buf.seek(0)
    return buf
