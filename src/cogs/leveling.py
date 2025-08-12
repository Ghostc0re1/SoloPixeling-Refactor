import asyncio
from datetime import datetime, timedelta, time as dt_time
import logging
import time
import random
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from PIL import Image, ImageOps

#
import discord
from discord.ext import commands, tasks
from discord import app_commands

#
import config
from utility.level_utils import (
    RankCardData,
    xp_for_level,
    level_from_xp,
    XpResult,
)
from utility import image_utils
from helpers.level_helper import fetch_banner_bytes
from helpers import banner_helper
from data import database
from views.leaderboard_view import LeaderboardView

logger = logging.getLogger(__name__)


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_xp = {}
        self.guild_cooldowns = {}
        self.guild_xp_ranges = {}
        self.guild_levelup_channels = {}
        self._awards_started = False

    async def cog_unload(self):
        try:
            if self.daily_award_task.is_running():
                self.daily_award_task.cancel()
        except Exception as e:
            logging.error("Failed to unload daily_award_task: %s", e)

    @commands.Cog.listener()
    async def on_ready(self):
        """Load all settings from the database on startup."""

        # Cooldowns
        try:
            self.guild_cooldowns = await database.get_all_cooldowns()
            self.guild_xp_ranges = await database.get_all_xp_ranges()
            logger.info("Loaded XP ranges for %d guilds.", len(self.guild_xp_ranges))
            all_channel_settings = await database.get_all_channel_settings()
            for guild_id, settings in all_channel_settings.items():
                if settings.get("levelup"):
                    self.guild_levelup_channels[guild_id] = settings["levelup"]
            logger.info(
                "Loaded level-up channel settings for %d guilds.",
                len(self.guild_levelup_channels),
            )
            logger.info("Loaded cooldowns for %d guilds.", len(self.guild_cooldowns))

            if not self._awards_started:
                self.daily_award_task.start()
                self._awards_started = True
        except Exception as e:
            logging.error("Failed to load leveling settings on_ready: %s", e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.bot
            or not message.guild
            or message.channel.id in config.EXCLUDED_CHANNELS
        ):
            return

        try:
            res = await self._process_xp_gain(message)
            if res and res.leveled_up:
                await self._announce_levelup(message, res.new_level)
        except Exception as e:
            logging.error("Error processing XP gain for message %s: %s", message.id, e)

    # pylint: disable=too-many-locals
    async def _process_xp_gain(self, message: discord.Message) -> XpResult | None:
        """Apply cooldown, award XP, persist, and return level-change info (or None if skipped)."""
        user_id = message.author.id
        guild_id = message.guild.id

        xp_range = self.guild_xp_ranges.get(guild_id, config.DEFAULT_XP_RANGE)
        cooldown = self.guild_cooldowns.get(guild_id, config.DEFAULT_XP_COOLDOWN)

        now = time.time()
        key = (guild_id, user_id)
        last = self._last_xp.get(key, 0.0)
        if now - last < cooldown:
            return None
        self._last_xp[key] = now

        xp_gain = random.randint(*xp_range)

        user_data = await database.get_user(user_id, guild_id)
        current_xp, _stored_level = user_data if user_data else (0, 0)
        current_level = level_from_xp(current_xp)

        new_total_xp = current_xp + xp_gain
        new_level = level_from_xp(new_total_xp)

        await database.set_user_xp_and_level(user_id, guild_id, new_total_xp, new_level)
        await database.increment_daily_xp(user_id, guild_id, xp_gain)

        leveled_up = new_level > current_level
        logging.debug(
            "XP processed: user=%s guild=%s gain=%s total=%s lvl=%s->%s",
            user_id,
            guild_id,
            xp_gain,
            new_total_xp,
            current_level,
            new_level,
        )
        return XpResult(
            leveled_up=leveled_up, new_level=new_level, old_level=current_level
        )

    async def _announce_levelup(self, message: discord.Message, new_level: int) -> None:
        """Send level-up message and apply role rewards if configured."""
        try:
            guild_id = message.guild.id
            channel_id = self.guild_levelup_channels.get(
                guild_id, config.DEFAULT_LEVELUP_CHANNEL_ID
            )
            if not channel_id:
                return

            lvl_ch = message.guild.get_channel(channel_id)
            if not lvl_ch:
                return

            await lvl_ch.send(f"Player {message.author.mention} has leveled up.")

            # Role reward (optional)
            role_id = config.ROLE_REWARDS.get(new_level)
            if not role_id:
                return

            role = message.guild.get_role(role_id)
            if not role:
                return

            lines = [
                [
                    ("Player ", config.REGULAR_FONT_PATH),
                    (message.author.display_name, config.BOLD_ITALIC_FONT_PATH),
                ],
                [("has been promoted to an ", config.REGULAR_FONT_PATH)],
                [(f"{role.name}.", config.BOLD_ITALIC_FONT_PATH)],
            ]

            buf = image_utils.make_multiline_glow(
                config.LEVELUP_BANNER_PATH,
                lines,
                max_font_size=50,
                glow_radii=(20, 40, 80),
                v_pad=8,
            )

            await lvl_ch.send(
                file=discord.File(fp=buf, filename="rankup.jpg"),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            await message.author.add_roles(role, reason="Level up reward")
        except discord.Forbidden:
            logging.warning(
                "Missing permissions to announce level up in guild %s", message.guild.id
            )
        except Exception as e:
            logging.error(
                "Failed to announce level up for %s: %s", message.author.id, e
            )

    @app_commands.command(
        name="rank", description="Check your (or someone else's) rank & XP"
    )
    @app_commands.describe(member="The member to check")
    async def rank(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=False)
        try:
            target = member or interaction.user

            user_data = await database.get_user(target.id, interaction.guild.id)
            user_rank = await database.get_user_rank(target.id, interaction.guild.id)

            if not user_data or user_rank is None:
                return await interaction.followup.send(
                    "That user has no XP yet.", ephemeral=True
                )

            total_xp, level = user_data
            cur_level_xp = xp_for_level(level)
            next_level_xp = xp_for_level(level + 1)

            data = (
                await database.get_user_profile(target.id, interaction.guild.id) or {}
            )
            primary = data.get("primary_color")
            accent = data.get("accent_color")
            banner_path = data.get("banner_path")

            banner_bytes = (
                await fetch_banner_bytes(banner_path) if banner_path else None
            )

            card = RankCardData(
                member=target,
                level=level,
                rank=user_rank,
                current_xp=total_xp - cur_level_xp,
                required_xp=next_level_xp - cur_level_xp,
                total_xp=total_xp,
                primary_color=primary,
                accent_color=accent,
                banner_bytes=banner_bytes,
            )

            # assumes you updated the function signature to accept the dataclass
            image_file = await banner_helper.generate_rank_card(card)
            await interaction.followup.send(file=image_file)

        except Exception as e:
            logging.exception("Error in /rank command")
            await interaction.followup.send(
                f"Could not generate rank card. Please try again later. Error: {e}",
                ephemeral=True,
            )

    @app_commands.command(
        name="leaderboard",
        description="Show the server's top users by level and XP.",
    )
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            rows = await database.get_leaderboard(interaction.guild.id, 200)
            if not rows:
                return await interaction.followup.send(
                    "No leaderboard data yet.", ephemeral=True
                )

            view = LeaderboardView(interaction, rows)
            view.update_buttons()
            embed = await view.generate_embed()

            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message
        except Exception as e:
            logging.error("Error in /leaderboard command: %s", e)
            await interaction.followup.send(
                "Could not retrieve the leaderboard. Please try again later.",
                ephemeral=True,
            )

    @tasks.loop(time=dt_time(0, 0, tzinfo=ZoneInfo("America/New_York")))
    async def daily_award_task(self):
        eastern_now = datetime.now(ZoneInfo("America/New_York"))
        yesterday = (eastern_now - timedelta(days=1)).strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            try:
                top = await database.get_daily_top_user(guild.id, yesterday)
                if not top:
                    continue
                user_id, xp_gain = top

                role = guild.get_role(config.DAILY_XP_ROLE)

                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    continue
                if not role:
                    continue

                for m in role.members:
                    await m.remove_roles(role, reason="Daily XP reset")

                await member.add_roles(role, reason=f"Most XP yesterday: {xp_gain}")

                chan_id = config.DAILY_ANNOUNCE_CHANNEL.get(guild.id)
                if chan_id:
                    ch = guild.get_channel(chan_id)
                    if ch:
                        await ch.send(
                            f"🏆 Congrats {member.mention}: you gained **{xp_gain} XP** yesterday!"
                        )
            except discord.NotFound:
                continue
            except discord.Forbidden:
                logging.warning(
                    "Missing permissions for daily awards in guild %s", guild.id
                )
            except Exception as e:
                logging.error("Error in daily_award_task for guild %s: %s", guild.id, e)

        try:
            await database.reset_daily_xp(yesterday)
        except Exception as e:
            logging.error("Failed to reset daily XP for %s: %s", yesterday, e)

    @daily_award_task.before_loop
    async def before_daily_award(self):
        await self.bot.wait_until_ready()

    def _is_hex(self, s: str) -> bool:
        return (
            isinstance(s, str)
            and len(s) == 7
            and s.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in s[1:])
        )

    # pylint: disable=too-many-arguments
    def _process_banner_bytes(
        self,
        raw: bytes,
        prefer_webp: bool = True,
        *,
        target_size: Tuple[int, int] = (config.CARD_WIDTH, config.CARD_HEIGHT),
        centering: Tuple[float, float] = (0.5, 0.5),  # 0..1
        darken_overlay_rgba: tuple[int, int, int, int] | None = None,
        jpeg_bg: tuple[int, int, int] = (0, 0, 0),
    ) -> tuple[bytes, str, str]:
        """
        Return (processed_bytes, mime, ext) cropped to exactly `target_size` via cover scaling.
        """
        # 1) Open safely & normalize
        img = image_utils.safe_open(raw).convert("RGBA")

        # 2) Cover scale + crop to the banner box
        img = ImageOps.fit(
            img,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=centering,
        )

        # 3) Optional overlay to help white text pop
        if darken_overlay_rgba:
            overlay = Image.new("RGBA", img.size, darken_overlay_rgba)
            img = Image.alpha_composite(img, overlay)

        # 4) Pick format & encode
        has_alpha = img.mode == "RGBA"
        ext, mime = image_utils.sniff_ext_and_mime(
            img.format or "", has_alpha, prefer_webp=prefer_webp
        )

        if ext == "webp":
            out_bytes = image_utils.encode_webp(img, lossless=has_alpha, quality=85)
            return out_bytes, mime, ext

        # JPEG path: flatten first
        jpg_img = image_utils.flatten_rgba_to_rgb(img, bg=jpeg_bg)
        out_bytes = image_utils.encode_jpeg(jpg_img, quality=85)
        return out_bytes, mime, ext

    @app_commands.command(
        name="rank-set-banner",
        description="Upload a custom rank banner (scaled to 1600x400).",
    )
    @app_commands.describe(image="PNG/JPEG/WebP, up to 2 MB")
    async def rank_set_banner(
        self, interaction: discord.Interaction, image: discord.Attachment
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            if image.content_type not in config.ALLOWED_MIME:
                return await interaction.followup.send(
                    "Unsupported file type. Please upload PNG, JPEG, or WebP.",
                    ephemeral=True,
                )
            if image.size > config.MAX_UPLOAD_BYTES:
                return await interaction.followup.send(
                    "File too large. Please keep it under 2 MB.", ephemeral=True
                )

            raw = await image.read()

            processed, mime, ext = await asyncio.to_thread(
                self._process_banner_bytes,
                raw,
                True,  # prefer_webp
                target_size=(config.CARD_WIDTH, config.CARD_HEIGHT),
                centering=(0.5, 0.5),
                darken_overlay_rgba=(0, 0, 0, 96),
                jpeg_bg=(0, 0, 0),
            )
            await database.set_rank_banner(
                interaction.user.id, interaction.guild.id, processed, mime, ext
            )
            await interaction.followup.send(
                "✅ Banner updated! Use `/rank` to see it.", ephemeral=True
            )
        except Exception as e:
            logging.exception("rank-set-banner failed")
            await interaction.followup.send(
                f"Failed to set banner. Please try again. {e}", ephemeral=True
            )

    @app_commands.command(
        name="rank-remove-banner", description="Remove your custom rank banner."
    )
    async def rank_remove_banner(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await database.remove_rank_banner(
                interaction.user.id, interaction.guild.id, delete_file=False
            )
            await interaction.followup.send(
                "✅ Banner removed. Your rank card will use the default background.",
                ephemeral=True,
            )
        except Exception as e:
            logging.exception("rank-remove-banner failed")
            await interaction.followup.send(
                f"Failed to remove banner. Please try again. {e}", ephemeral=True
            )

    @app_commands.command(
        name="rank-set-colors",
        description="Set primary/accent colors for your rank card (hex like #FF8800).",
    )
    @app_commands.describe(
        primary="Primary hex color (#RRGGBB)", accent="Accent hex color (#RRGGBB)"
    )
    async def rank_set_colors(
        self,
        interaction: discord.Interaction,
        primary: str | None = None,
        accent: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if primary is None and accent is None:
                return await interaction.followup.send(
                    "Provide at least one color.", ephemeral=True
                )

            if primary is not None and not self._is_hex(primary):
                return await interaction.followup.send(
                    "Invalid primary color. Use hex like `#1E90FF`.", ephemeral=True
                )
            if accent is not None and not self._is_hex(accent):
                return await interaction.followup.send(
                    "Invalid accent color. Use hex like `#FFD700`.", ephemeral=True
                )

            await database.set_profile_colors(
                interaction.user.id, interaction.guild.id, primary, accent
            )
            await interaction.followup.send(
                "✅ Colors saved! Use `/rank` to see them.", ephemeral=True
            )
        except Exception as e:
            logging.exception("rank-set-colors failed")
            await interaction.followup.send(
                f"Failed to save colors. Please try again. Error: {e}", ephemeral=True
            )

    @app_commands.command(
        name="rank-reset-colors",
        description="Reset your rank card colors to the defaults.",
    )
    async def rank_reset_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await database.clear_profile_colors(
                interaction.user.id, interaction.guild.id
            )
            await interaction.followup.send(
                "✅ Colors reset to defaults.", ephemeral=True
            )
        except Exception:
            logging.exception("rank-reset-colors failed")
            await interaction.followup.send(
                "Failed to reset colors. Please try again.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
