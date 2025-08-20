import asyncio
import time
import random
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from PIL import Image, ImageOps

#
import discord
from discord.ext import commands, tasks
from discord import app_commands

#
import config
from utility import image_utils
from utility.level_utils import (
    RankCardData,
    xp_for_level,
    level_from_xp,
    XpResult,
)
from helpers import banner_helper
from helpers.level_helper import fetch_banner_bytes
from helpers.logging_helper import get_logger, add_throttle
from data import database
from views.confirmation_view import ConfirmView
from views.leaderboard_view import LeaderboardView


log = get_logger("leveling")
xp_logger = get_logger("leveling.xp")
add_throttle(xp_logger, 60)

heartbeat = get_logger("leveling.heartbeat")
add_throttle(heartbeat, 300)

ET = ZoneInfo("America/New_York")


class Leveling(commands.Cog, name="Leveling"):
    def __init__(self, bot: commands.Bot, *, auto_start_loops: bool = True):
        self.bot = bot
        self._last_xp = {}
        self.guild_cooldowns = {}
        self.guild_xp_ranges = {}
        self.guild_levelup_channels = {}

        # background loop state
        self._loops_started = False
        self._start_on_ready = False

        if auto_start_loops:
            self._try_start_background_tasks()

    def _try_start_background_tasks(self) -> None:
        """Start loops only if an event loop is already running; otherwise defer."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g., during unit test object construction) → defer.
            self._start_on_ready = True
            return
        self._start_background_tasks()

    def _start_background_tasks(self) -> None:
        if self._loops_started:
            return
        # these are @tasks.loop-decorated objects created at class load time
        self.daily_award_stage_task.start()
        self.drain_award_outbox.start()
        self._loops_started = True

    async def cog_unload(self):
        # Cancel both loops on unload/reload
        for loop_task in (
            getattr(self, "daily_award_stage_task", None),
            getattr(self, "drain_award_outbox", None),
        ):
            try:
                if loop_task and loop_task.is_running():
                    loop_task.cancel()
            except Exception:
                log.exception(
                    "Failed to cancel loop %s", getattr(loop_task, "__name__", "<loop>")
                )

    @commands.Cog.listener()
    async def on_ready(self):
        """Load all settings from the database on startup."""
        if self._start_on_ready and not self._loops_started:
            self._start_background_tasks()

        try:
            self.guild_cooldowns = await database.get_all_cooldowns()
            self.guild_xp_ranges = await database.get_all_xp_ranges()
            log.info("Loaded XP ranges for %d guilds.", len(self.guild_xp_ranges))

            all_channel_settings = await database.get_all_channel_settings()
            for guild_id, settings in all_channel_settings.items():
                if settings.get("levelup"):
                    self.guild_levelup_channels[guild_id] = settings["levelup"]
            log.info(
                "Loaded level-up channel settings for %d guilds.",
                len(self.guild_levelup_channels),
            )
            log.info("Loaded cooldowns for %d guilds.", len(self.guild_cooldowns))

            # Catch-up (optional): if yesterday has rows, stage & immediately try to drain once.
            ystr = (datetime.now(ET).date() - timedelta(days=1)).isoformat()
            if await database.daily_xp_exists(ystr):
                log.info(
                    "🔄 Catch-up: daily_xp present for %s, staging & draining once.",
                    ystr,
                )
                await self.stage_awards_for_date(ystr)
                await self._drain_award_outbox_once()
            else:
                log.info("✅ Catch-up: no daily_xp rows for %s.", ystr)

        except Exception:
            log.exception("Failed to load leveling settings on_ready")

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
        except Exception:
            log.exception("Error processing XP gain for message %s", message.id)

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
        xp_logger.debug(
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
            log.warning(
                "Missing permissions to announce level up in guild %s", message.guild.id
            )
        except Exception:
            log.exception("Failed to announce level up for %s", message.author.id)

    # pylint: disable=too-many-branches
    async def stage_awards_for_date(self, target_date: str) -> None:
        for guild in self.bot.guilds:
            top = await database.get_daily_top_user(guild.id, target_date)
            if not top:
                log.info("No daily_xp rows for guild=%s on %s", guild.id, target_date)
                continue

            user_id, xp_gain = top
            chan_id = getattr(config, "DAILY_ANNOUNCE_CHANNEL", {}).get(guild.id)
            await database.stage_daily_award(
                guild.id, target_date, user_id, xp_gain, chan_id
            )
            log.info(
                "Staged award: guild=%s date=%s user=%s xp=%s",
                guild.id,
                target_date,
                user_id,
                xp_gain,
            )

    async def _drain_award_outbox_once(self) -> None:
        for row in await database.list_outbox_pending():
            guild_id = int(row["guild_id"])
            target_date = str(row["target_date"])
            user_id = int(row["user_id"])
            xp_gain = int(row["xp_gain"])
            chan_id = (row.get("payload") or {}).get("channel_id")

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            # Best-effort role ops
            try:
                role = guild.get_role(config.DAILY_XP_ROLE)
                if role:
                    for holder in list(role.members):
                        try:
                            await holder.remove_roles(
                                role, reason=f"Daily XP reset {target_date}"
                            )
                        except Exception:
                            log.warning(
                                "Role remove failed for %s in %s", holder.id, guild_id
                            )

                    try:
                        member = guild.get_member(user_id) or await guild.fetch_member(
                            user_id
                        )
                        if role not in member.roles:
                            await member.add_roles(
                                role, reason=f"Most XP on {target_date}: {xp_gain}"
                            )
                    except Exception:
                        log.warning(
                            "Winner fetch/add failed for %s in %s", user_id, guild_id
                        )
            except Exception:
                log.warning("Role ops skipped for guild=%s due to error", guild_id)

            # Announce
            msg_id = 0
            try:
                if chan_id:
                    ch = guild.get_channel(chan_id) or await self.bot.fetch_channel(
                        chan_id
                    )
                    if isinstance(ch, discord.TextChannel):
                        msg = await ch.send(
                            f"🏆 Congrats <@{user_id}>: you gained **{xp_gain} XP** on {target_date}!"
                        )
                        msg_id = msg.id
                    else:
                        log.warning(
                            "Configured channel %s not a TextChannel in %s",
                            chan_id,
                            guild_id,
                        )
                else:
                    log.warning("No announce channel configured for guild=%s", guild_id)
            except Exception:
                log.exception(
                    "Announcement failed for guild=%s date=%s", guild_id, target_date
                )
                continue  # leave pending; retry next loop

            # Mark announced and then cleanup (gated by announced_at)
            try:
                await database.mark_award_announced(guild_id, target_date, msg_id)
                deleted = await database.reset_daily_xp_after_announce(
                    guild_id, target_date
                )
                log.info(
                    "Announced and reset guild=%s date=%s (deleted=%s)",
                    guild_id,
                    target_date,
                    deleted,
                )
            except Exception:
                log.exception(
                    "Post-announce DB ops failed for guild=%s date=%s",
                    guild_id,
                    target_date,
                )
                # It was announced but not reset; next pass will only run reset since announced_at is set.

    @tasks.loop(time=dt_time(0, 0, tzinfo=ET))
    async def daily_award_stage_task(self):
        target_date = (datetime.now(ET) - timedelta(days=1)).date().isoformat()
        log.info("⏰ daily_award_stage_task tick for %s", target_date)
        await self.stage_awards_for_date(target_date)

    @daily_award_stage_task.before_loop
    async def before_daily_award_stage(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=2)
    async def drain_award_outbox(self):
        await self._drain_award_outbox_once()

    @drain_award_outbox.before_loop
    async def before_drain_award_outbox(self):
        await self.bot.wait_until_ready()
        await self._drain_award_outbox_once()

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

        except Exception:
            log.exception("Error in /rank command")
            await interaction.followup.send(
                "Could not generate rank card. Please try again later.",
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
        except Exception:
            log.exception("Error in /leaderboard command:")
            await interaction.followup.send(
                "Could not retrieve the leaderboard. Please try again later.",
                ephemeral=True,
            )

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
        except Exception:
            log.exception("rank-set-banner failed")
            await interaction.followup.send(
                "Failed to set banner. Please try again.", ephemeral=True
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
        except Exception:
            log.exception("rank-remove-banner failed")
            await interaction.followup.send(
                "Failed to remove banner. Please try again.", ephemeral=True
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
        except Exception:
            log.exception("rank-set-colors failed")
            await interaction.followup.send(
                "Failed to save colors. Please try again.", ephemeral=True
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
            log.exception("rank-reset-colors failed")
            await interaction.followup.send(
                "Failed to reset colors. Please try again.", ephemeral=True
            )

    @staticmethod
    def _parse_date_or_yesterday_et(s: str | None) -> str:
        if s:
            try:
                datetime.strptime(s, "%Y-%m-%d")  # strict check
                return s
            except ValueError as exc:
                raise ValueError("Date must be in YYYY-MM-DD format.") from exc
        return (datetime.now(ET) - timedelta(days=1)).date().isoformat()

    @app_commands.command(
        name="testdaily", description="Test the daily award for a specific date."
    )
    @app_commands.describe(
        date="The date to test in YYYY-MM-DD format. Defaults to yesterday (ET)."
    )
    @commands.is_owner()
    async def test_daily_award(
        self, interaction: discord.Interaction, date: Optional[str] = None
    ):
        """Dry-run: briefly give/remove the DAILY_XP_ROLE to yesterday's winner."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            target_date = self._parse_date_or_yesterday_et(date)
            guild = interaction.guild
            if guild is None:
                return await interaction.edit_original_response(
                    content="❌ This command must be run in a server."
                )

            # Find winner
            top = await database.get_daily_top_user(guild.id, target_date)
            if not top:
                return await interaction.edit_original_response(
                    content=f"❌ No winner found for **{guild.name}** on `{target_date}`."
                )

            user_id, xp_gain = top

            # Resolve role
            role = guild.get_role(config.DAILY_XP_ROLE)
            if not role:
                return await interaction.edit_original_response(
                    content=f"❌ `DAILY_XP_ROLE` not found (ID `{config.DAILY_XP_ROLE}`)."
                )

            # Resolve member (may have left)
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    # Still report winner by ID/mention fallback
                    return await interaction.edit_original_response(
                        content=(
                            "❌ **Test Failed:** The winning user is no longer in this server.\n"
                            f"**Winner (ID):** `{user_id}`\n"
                            f"**XP Gained:** `{xp_gain}`\n"
                            f"**Date:** `{target_date}`"
                        )
                    )

            # Award briefly
            await member.add_roles(role, reason=f"Admin test for {target_date}")
            await interaction.followup.send(
                f"✅ **Awarding Test**\n"
                f"Gave `{role.name}` to **{member.display_name}** "
                f"for **{xp_gain} XP** on `{target_date}`.\n"
                f"*Removing role in 5 seconds…*",
                ephemeral=True,
            )
            await asyncio.sleep(5)
            await member.remove_roles(role, reason="Admin test complete.")

            # Final summary
            await interaction.edit_original_response(
                content=(
                    "✅ **Test Complete!**\n"
                    f"Temporarily awarded and removed `{role.name}` from **{member.display_name}**.\n\n"
                    f"**Winner:** <@{user_id}> (`{user_id}`)\n"
                    f"**XP Gained:** `{xp_gain}`\n"
                    f"**Date:** `{target_date}`"
                )
            )

        except ValueError as ve:
            await interaction.edit_original_response(content=f"❌ {ve}")
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=(
                    "❌ **PERMISSION ERROR**\n"
                    f"I can’t assign `{getattr(role, 'name', 'DAILY_XP_ROLE')}`. "
                    "Check my role hierarchy and permissions."
                )
            )
        except Exception as e:
            log.exception("Error during /testdaily command")
            await interaction.edit_original_response(
                content=f"Unexpected error: ```{e}```"
            )

    @app_commands.command(
        name="testdailydelete",
        description="Test deletion of daily XP data for a specific date (with confirmation).",
    )
    @commands.is_owner()
    async def test_daily_delete(
        self, interaction: discord.Interaction, date: Optional[str] = None
    ):
        """Shows a confirm dialog; the view should call the announced-gated reset RPC."""
        try:
            target_date = self._parse_date_or_yesterday_et(date)
            guild = interaction.guild
            if guild is None:
                return await interaction.response.send_message(
                    "❌ This command must be run in a server.", ephemeral=True
                )

            view = ConfirmView(
                guild_id=guild.id, date_str=target_date, author_id=interaction.user.id
            )
            # message = await interaction.response.send_message(
            #     f"🚨 **Confirm deletion of daily XP on `{guild}` for `{target_date}`?**\n"
            #     "This will only succeed if the daily winner was **successfully announced**.",
            #     view=view,
            #     ephemeral=True,
            # )
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass
        except ValueError as ve:
            await interaction.response.send_message(f"❌ {ve}", ephemeral=True)
        except Exception:
            log.exception("Error during /testdailydelete command")
            await interaction.response.send_message(
                "Unexpected error opening confirmation.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
