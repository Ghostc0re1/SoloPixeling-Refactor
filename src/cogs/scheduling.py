# cogs/scheduling.py

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

#
import discord
from discord.ext import commands, tasks
from discord import app_commands

#
import config

from helpers.logging_helper import get_logger, add_throttle

EASTERN_TIMEZONE = ZoneInfo("America/New_York")

logger = get_logger("scheduler")
heartbeat = get_logger("scheduler.heartbeat")
add_throttle(heartbeat, 900)


class Scheduling(commands.Cog, name="Scheduling"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ping_roles.start()

    async def cog_unload(self):
        try:
            if self.ping_roles.is_running():
                self.ping_roles.cancel()
        except Exception:
            logger.exception("Failed to unload ping_roles loop")

    @tasks.loop(minutes=1)
    async def ping_roles(self):
        now = datetime.now(EASTERN_TIMEZONE)
        weekday = now.weekday()

        heartbeat.debug(
            "Loop tick ET=%s weekday=%s", now.strftime("%Y-%m-%d %H:%M:%S %Z"), weekday
        )

        if not getattr(config, "GUILD_ID", None):
            logger.debug("No GUILD_ID configured; skipping tick")
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.warning("Could not find guild with ID %s", config.GUILD_ID)
            return

        for sched in config.PING_SCHEDULES:
            logger.debug(
                "Checking schedule role_id=%s channel_id=%s", sched.role_id, sched.ch_id
            )

            if weekday not in sched.days:
                logger.debug("Skip: weekday %s not in %s", weekday, sched.days)
                continue

            channel = guild.get_channel(sched.ch_id)
            if not channel:
                logger.warning("Skip: channel_id %s not found", sched.ch_id)
                continue

            # Send ping
            if now.hour == sched.ping_hour and now.minute == sched.ping_min:
                role = guild.get_role(sched.role_id)
                if role:
                    try:
                        await channel.send(f"{role.mention} {sched.msg}")
                        logger.info(
                            "Ping sent: channel=%s role_id=%s msg=%s",
                            channel.name,
                            role.id,
                            sched.msg,
                        )
                    except discord.errors.Forbidden:
                        logger.error(
                            "Missing permissions to send ping in #%s", channel.name
                        )
                    except Exception:
                        logger.exception("Failed to send ping in #%s", channel.name)
                else:
                    logger.error(
                        "Role not found for scheduled ping: role_id=%s", sched.role_id
                    )

            # Purge channel
            if (
                sched.delete_hour is not None
                and now.hour == sched.delete_hour
                and now.minute == sched.delete_min
            ):
                if (
                    getattr(config, "EXCLUDED_CHANNELS", None)
                    and channel.id in config.EXCLUDED_CHANNELS
                ):
                    logger.debug("Skip purge: channel_id %s is excluded", channel.id)
                else:
                    try:
                        await channel.purge(limit=1000)
                        logger.info("Purged messages in #%s (limit=1000)", channel.name)
                    except discord.errors.Forbidden:
                        logger.error(
                            "Missing permissions to purge in #%s", channel.name
                        )
                    except Exception:
                        logger.exception("Failed to purge in #%s", channel.name)

    @ping_roles.before_loop
    async def before_ping_roles(self):
        await self.bot.wait_until_ready()
        logger.info("Scheduler task ready (timezone=%s)", EASTERN_TIMEZONE)

    @app_commands.command(
        name="testschedule", description="Tests the scheduling configuration."
    )
    @app_commands.describe(
        index="Optional: The schedule # to trigger immediately (starts at 0)."
    )
    @app_commands.default_permissions(administrator=True)
    async def testschedule(
        self, interaction: discord.Interaction, index: Optional[int] = None
    ):
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            await interaction.response.send_message(
                "❌ **Error:** Could not find the configured GUILD_ID.", ephemeral=True
            )
            logger.error("testschedule: GUILD_ID %s not found", config.GUILD_ID)
            return

        # === CHECKUP MODE ===
        if index is None:
            embed = discord.Embed(
                title="Scheduler Status Check",
                description="Checking all configured schedules...",
                color=discord.Color.blue(),
            )
            for i, sched in enumerate(config.PING_SCHEDULES):
                # sched: PingSchedule
                role = guild.get_role(sched.role_id)
                channel = guild.get_channel(sched.ch_id)

                status = ""
                status += (
                    f"✅ Channel: {channel.mention}"
                    if channel
                    else f"❌ Channel ID `{sched.ch_id}` not found."
                )
                status += "\n"
                status += (
                    f"✅ Role: `{role.name}`"
                    if role
                    else f"❌ Role ID `{sched.role_id}` not found."
                )

                embed.add_field(
                    name=f"Schedule #{i}: `{sched.msg[:50]}`...",
                    value=status,
                    inline=False,
                )

            # Using interaction.response
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("testschedule checkup run by user_id=%s", interaction.user.id)
            return

        # === TRIGGER MODE ===
        if not 0 <= index < len(config.PING_SCHEDULES):
            await interaction.response.send_message(
                f"❌ **Error:** Invalid index."
                f" Please provide a number between 0 and {len(config.PING_SCHEDULES) - 1}.",
                ephemeral=True,
            )
            logger.warning("testschedule invalid index: %s", index)
            return

        sched_to_test = config.PING_SCHEDULES[index]
        channel = guild.get_channel(sched_to_test.ch_id)
        if not channel:
            await interaction.response.send_message(
                f"❌ **Error:** Cannot trigger. Channel ID `{sched_to_test.ch_id}` was not found.",
                ephemeral=True,
            )
            logger.error(
                "testschedule trigger failed: channel_id %s not found",
                sched_to_test.ch_id,
            )
            return

        role = guild.get_role(sched_to_test.role_id)
        if not role:
            await interaction.response.send_message(
                f"❌ **Error:** Cannot trigger. Role ID `{sched_to_test.role_id}` was not found.",
                ephemeral=True,
            )
            logger.error(
                "testschedule trigger failed: role_id %s not found",
                sched_to_test.role_id,
            )
            return

        try:
            await channel.send(
                f"**--- THIS IS A TEST PING ---**\n{role.mention} {sched_to_test.msg}"
            )
            await interaction.response.send_message(
                f"✅ Successfully sent test ping for schedule **#{index}** to {channel.mention}.",
                ephemeral=True,
            )
            logger.info(
                "testschedule sent: index=%s channel=%s role_id=%s",
                index,
                channel.name,
                role.id,
            )
        except discord.errors.Forbidden:
            await interaction.response.send_message(
                f"❌ **Error:** The bot lacks permission to send messages in {channel.mention}.",
                ephemeral=True,
            )
            logger.error("testschedule forbidden in #%s", channel.name)
        except Exception:
            await interaction.response.send_message(
                "An unexpected error occurred.", ephemeral=True
            )
            logger.exception("testschedule unexpected error")


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduling(bot))
