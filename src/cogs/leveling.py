from datetime import datetime, timedelta, time as dt_time
import logging
import time
import random
from zoneinfo import ZoneInfo

#
import discord
from discord.ext import commands, tasks
from discord import app_commands

#
import config
from helpers.level_utils import xp_for_level, level_from_xp, XpResult
from helpers import image_utils
from data import database
from views.leaderboard_view import LeaderboardView


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
            self.guild_cooldowns = database.get_all_cooldowns()
            self.guild_xp_ranges = database.get_all_xp_ranges()
            print(f"Loaded XP ranges for {len(self.guild_xp_ranges)} guilds.")
            all_channel_settings = database.get_all_channel_settings()
            for guild_id, settings in all_channel_settings.items():
                if settings.get("levelup"):
                    self.guild_levelup_channels[guild_id] = settings["levelup"]
            print(
                f"Loaded level-up channel settings for {len(self.guild_levelup_channels)} guilds."
            )
            print(f"Loaded cooldowns for {len(self.guild_cooldowns)} guilds.")

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
            res = self._process_xp_gain(message)
            if res and res.leveled_up:
                await self._announce_levelup(message, res.new_level)
        except Exception as e:
            logging.error("Error processing XP gain for message %s: %s", message.id, e)

    # pylint: disable=too-many-locals
    def _process_xp_gain(self, message: discord.Message) -> XpResult | None:
        """Apply cooldown, award XP, persist, and return level-change info (or None if skipped)."""
        user_id = message.author.id
        guild_id = message.guild.id

        xp_range = self.guild_xp_ranges.get(guild_id, config.DEFAULT_XP_RANGE)
        cooldown = self.guild_cooldowns.get(guild_id, config.DEFAULT_XP_COOLDOWN)

        now = time.time()
        last = self._last_xp.get(user_id, 0.0)
        if now - last < cooldown:
            return None
        self._last_xp[user_id] = now

        xp_gain = random.randint(*xp_range)

        user_data = database.get_user(user_id, guild_id)
        current_xp, _stored_level = user_data if user_data else (0, 0)
        current_level = level_from_xp(current_xp)

        new_total_xp = current_xp + xp_gain
        new_level = level_from_xp(new_total_xp)

        database.set_user_xp_and_level(user_id, guild_id, new_total_xp, new_level)
        database.increment_daily_xp(user_id, guild_id, xp_gain)

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
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        await interaction.response.defer()
        try:
            target_member = member or interaction.user
            user_data = database.get_user(target_member.id, interaction.guild.id)
            user_rank = database.get_user_rank(target_member.id, interaction.guild.id)

            if not user_data or user_rank is None:
                return await interaction.followup.send(
                    "That user has no XP yet.", ephemeral=True
                )

            total_xp, level = user_data
            xp_of_current_level_start = xp_for_level(level)
            xp_of_next_level_start = xp_for_level(level + 1)
            xp_progress = total_xp - xp_of_current_level_start
            xp_needed = xp_of_next_level_start - xp_of_current_level_start

            rank_card = await image_utils.generate_rank_card(
                member=target_member,
                level=level,
                rank=user_rank,
                current_xp=xp_progress,
                required_xp=xp_needed,
                total_xp=total_xp,
            )
            await interaction.followup.send(file=rank_card)
        except Exception as e:
            logging.error("Error in /rank command: %s", e)
            await interaction.followup.send(
                "Could not generate rank card. Please try again later.", ephemeral=True
            )

    @app_commands.command(
        name="leaderboard", description="Show the server's top users by level and XP."
    )
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            rows = database.get_leaderboard(interaction.guild.id, 200)

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
                top = database.get_daily_top_user(guild.id, yesterday)
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
            database.reset_daily_xp(yesterday)
        except Exception as e:
            logging.error("Failed to reset daily XP for %s: %s", yesterday, e)

    @daily_award_task.before_loop
    async def before_daily_award(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
