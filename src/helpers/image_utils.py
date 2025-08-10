from io import BytesIO
from typing import Optional, Tuple, Union
from dataclasses import dataclass

import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps

import config

#
# --- Helpers ---
#
Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]
FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]


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


def _hex_to_rgb(
    s: Optional[str], default: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Parse '#RRGGBB' -> (r,g,b). Returns default on None/invalid."""
    if not s or not isinstance(s, str) or len(s) != 7 or not s.startswith("#"):
        return default
    try:
        return tuple(int(s[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except Exception:
        return default


#
# --- ENDREGION: Helpers ---
#
#
# --- Private Functs ----
#
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


#
# --- ENDREGION: Private Functs ----
#
#
# --- Glow Image Functions ---
#
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


#
# --- Generation Functions ---
#
async def generate_levelup_banner(user: discord.User, new_role: str) -> discord.File:
    """
    Autoscale the font so the text never exceeds 80% of the banner width.
    """
    base = Image.open(config.LEVELUP_BANNER_PATH).convert("RGBA")
    w, _h = base.size
    draw = ImageDraw.Draw(base)

    segments = [
        (user.display_name, config.BOLD_ITALIC_FONT_PATH),
        (" you have been promoted to ", config.REGULAR_FONT_PATH),
        (f"{new_role}.", config.BOLD_ITALIC_FONT_PATH),
    ]

    for size in range(64, 9, -2):
        fonts = [ImageFont.truetype(fp, size) for _, fp in segments]
        total_w = sum(
            draw.textlength(txt, font=font) for (txt, _), font in zip(segments, fonts)
        )
        if total_w <= w * 0.8:
            chosen_size = size
            break
    else:
        chosen_size = 10

    buf = make_glow_image_segments(
        config.LEVELUP_BANNER_PATH, segments, font_size=chosen_size
    )

    return discord.File(fp=buf, filename="levelup.png")


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
async def generate_rank_card(
    member: discord.Member,
    level: int,
    rank: int,
    current_xp: int,
    required_xp: int,
    total_xp: int,
    *,
    primary_color: Optional[str] = None,  # NEW: '#RRGGBB'
    accent_color: Optional[str] = None,  # NEW: '#RRGGBB'
    banner_bytes: Optional[bytes] = None,
) -> discord.File:
    """
    Generates a rank card. Supports optional custom banner background and theming via hex colors.
    - primary_color : affects large headings / totals (default white)
    - accent_color  : affects rank label and XP bar color (default golden/yellow)
    - banner_bytes  : used as the card background with a soft dark overlay
    """
    # ---- THEME COLORS (with graceful fallbacks) ----
    white = (255, 255, 255)
    black = (0, 0, 0)
    default_accent = (248, 184, 48)  # your yellow
    prim_rgb = _hex_to_rgb(primary_color, white)
    acc_rgb = _hex_to_rgb(accent_color, default_accent)

    # ---- BACKGROUND ----
    try:
        if banner_bytes:
            bg = Image.open(BytesIO(banner_bytes)).convert("RGBA")
            bg = ImageOps.fit(
                bg,
                (config.CARD_WIDTH, config.CARD_HEIGHT),
                Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            overlay = Image.new("RGBA", bg.size, (0, 0, 0, 96))  # ~38% black
            card_bg = Image.alpha_composite(bg, overlay)
        else:
            # Fallback to your default background, then reduce its alpha so foreground pops
            card_bg = (
                Image.open(config.RANK_CARD_BACKGROUND_PATH)
                .convert("RGBA")
                .resize((config.CARD_WIDTH, config.CARD_HEIGHT))
            )
            alpha = card_bg.getchannel("A")
            alpha = alpha.point(lambda p: p * 0.5)  # 50% transparency
            card_bg.putalpha(alpha)
    except FileNotFoundError:
        card_bg = Image.new(
            "RGBA", (config.CARD_WIDTH, config.CARD_HEIGHT), (54, 57, 63, 128)
        )

    # ---- FOREGROUND LAYER ----
    foreground = Image.new("RGBA", card_bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(foreground)

    # --- Progress math ---
    progress_percent = max(
        0.0, min(1.0, current_xp / required_xp if required_xp > 0 else 0)
    )
    remaining_xp = max(0, required_xp - current_xp)

    # --- Fonts ---
    font_user = _load_font(64)
    font_rank = _load_font(52)
    font_level = _load_font(84)
    font_remaining_xp = _load_font(36)
    font_total_xp = _load_font(64)
    font_xp = _load_font(24)

    # --- Rank gap calc ---
    if rank is not None:
        if rank < 10:
            rank_text_gap = 325
        elif rank < 100:
            rank_text_gap = 345
        elif rank < 1000:
            rank_text_gap = 365
        else:
            rank_text_gap = 325
    else:
        rank = "unknown"
        rank_text_gap = 365

    # --- Level gap calc ---
    if level is not None:
        if level < 10:
            level_text_gap = 0
        elif level < 100:
            level_text_gap = 50
        elif level < 1000:
            level_text_gap = 100
        else:
            level_text_gap = 0
    else:
        level = "unknown"
        level_text_gap = 0

    # --- Avatar ---
    avatar_size = 300
    if member.avatar:
        asset = member.avatar.replace(size=128)
        data = await asset.read()
        av = (
            Image.open(BytesIO(data)).convert("RGBA").resize((avatar_size, avatar_size))
        )
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle(
            [(0, 0), (avatar_size, avatar_size)], radius=30, fill=255
        )
        foreground.paste(av, (50, 50), mask)

    stroke_width = 1

    # --- Username (uses primary color) ---
    draw_text(
        draw,
        position=(375, 285),
        text=member.display_name,
        font=font_user,
        fill_color=prim_rgb,
        anchor="lb",
    )

    # --- Rank label (uses accent color) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - (50 + level_text_gap) - rank_text_gap, 72.5),
        text=f"RANK #{rank}",
        font=font_rank,
        fill_color=acc_rgb,
        anchor="rt",
    )

    # --- Level (uses primary color) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - 50, 50),
        text=f"LEVEL {level}",
        font=font_level,
        fill_color=prim_rgb,
        anchor="rt",
    )

    # --- Remaining XP (primary) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - 50, 205),
        text=f"{remaining_xp} XP left",
        font=font_remaining_xp,
        fill_color=prim_rgb,
        anchor="rb",
    )

    # --- Total XP (primary) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - 50, 275),
        text=f"{total_xp} XP",
        font=font_total_xp,
        fill_color=prim_rgb,
        anchor="rb",
    )

    # --- XP Bar ---
    bar_x, bar_y = 375, config.CARD_HEIGHT - 100
    bar_width, bar_height = config.CARD_WIDTH - avatar_size - 115, 50
    bar_bg_color = (50, 50, 50, 180)
    bar_fill_color = (*acc_rgb, 255)  # use accent color for the fill

    # Background
    draw.rounded_rectangle(
        [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
        radius=25,
        fill=bar_bg_color,
    )
    # Fill
    if progress_percent > 0:
        fill_width = int(bar_width * progress_percent)
        draw.rounded_rectangle(
            [(bar_x, bar_y), (bar_x + fill_width, bar_y + bar_height)],
            radius=25,
            fill=bar_fill_color,
        )

    # XP Text (primary with outline)
    xp_text = f"{current_xp} / {required_xp} XP"
    text_bbox = draw.textbbox((0, 0), xp_text, font=font_xp)
    text_x = bar_x + (bar_width - (text_bbox[2] - text_bbox[0])) / 2
    text_y = bar_y + (bar_height - (text_bbox[3] - text_bbox[1])) / 2
    draw_text(
        draw,
        (text_x, text_y),
        text=xp_text,
        font=font_xp,
        fill_color=prim_rgb,
        outline_color=black,
        stroke_width=stroke_width,
        anchor="lt",
    )

    # --- Composite FG over BG, then round corners ---
    composite_image = Image.alpha_composite(card_bg, foreground)

    corner_radius = 25
    final_canvas = Image.new("RGBA", composite_image.size, (0, 0, 0, 0))
    corner_mask = Image.new("L", composite_image.size, 0)
    mask_draw = ImageDraw.Draw(corner_mask)
    mask_draw.rounded_rectangle(
        [(0, 0), composite_image.size], radius=corner_radius, fill=255
    )
    final_canvas.paste(composite_image, (0, 0), corner_mask)

    buf = BytesIO()
    final_canvas.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(fp=buf, filename="rank.png")
