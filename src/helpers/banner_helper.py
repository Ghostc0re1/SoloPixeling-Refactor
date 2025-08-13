# src/helpers/banner_helper.py
from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

import config
from utility.image_utils import (
    hex_to_rgb,
    _load_font,
    draw_text,
    make_glow_image_segments,
)
from utility.level_utils import RankCardData


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
async def generate_rank_card(data: RankCardData) -> discord.File:
    """
    Generates a rank card. Supports optional custom banner background and theming via hex colors.
    - primary_color : affects large headings / totals (default white)
    - accent_color  : affects rank label and XP bar color (default golden/yellow)
    - banner_bytes  : used as the card background with a soft dark overlay
    """
    # ---- THEME COLORS (with graceful fallbacks) ----
    white = (255, 255, 255)
    black = (0, 0, 0)
    default_accent = (248, 184, 48)

    # Access attributes from the data object now
    prim_rgb = hex_to_rgb(data.primary_color, white)
    acc_rgb = hex_to_rgb(data.accent_color, default_accent)

    # ---- BACKGROUND ----
    try:
        if data.banner_bytes:
            bg = Image.open(BytesIO(data.banner_bytes)).convert("RGBA")
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
        0.0, min(1.0, data.current_xp / data.required_xp if data.required_xp > 0 else 0)
    )
    remaining_xp = max(0, data.required_xp - data.current_xp)

    # --- Fonts ---
    font_user = _load_font(64)
    font_rank = _load_font(52)
    font_level = _load_font(84)
    font_remaining_xp = _load_font(36)
    font_total_xp = _load_font(64)
    font_xp = _load_font(30)

    if data.rank is not None:
        if data.rank < 10:
            rank_text_gap = 325
        elif data.rank < 100:
            rank_text_gap = 345
        elif data.rank < 1000:
            rank_text_gap = 365
        else:
            rank_text_gap = 325
    else:
        rank_text_gap = 365

    # --- Level gap calc ---
    if data.level is not None:
        if data.level < 10:
            level_text_gap = 0
        elif data.level < 100:
            level_text_gap = 50
        elif data.level < 1000:
            level_text_gap = 100
        else:
            level_text_gap = 0
    else:
        level_text_gap = 0

    # --- Avatar ---
    avatar_size = 300
    if data.member.avatar:
        asset = data.member.avatar.replace(size=128)
        avatar_bytes = await asset.read()  # avoid shadowing `data`
        av = (
            Image.open(BytesIO(avatar_bytes))
            .convert("RGBA")
            .resize((avatar_size, avatar_size))
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
        text=data.member.display_name,
        font=font_user,
        fill_color=prim_rgb,
        anchor="lb",
    )

    # --- Rank label (uses accent color) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - (50 + level_text_gap) - rank_text_gap, 72.5),
        text=f"RANK #{data.rank}" if data.rank is not None else "RANK ?",
        font=font_rank,
        fill_color=acc_rgb,
        anchor="rt",
    )

    # --- Level (uses primary color) ---
    draw_text(
        draw,
        position=(config.CARD_WIDTH - 50, 50),
        text=f"LEVEL {data.level}" if data.level is not None else "LEVEL ?",
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
        text=f"{data.total_xp} XP",
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
    xp_text = f"{data.current_xp} / {data.required_xp} XP"
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
