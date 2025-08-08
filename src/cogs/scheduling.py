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

EASTERN_TIMEZONE = ZoneInfo("America/New_York")


class Scheduling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ping_roles.start()

    async def cog_unload(self):
        self.ping_roles.cancel()

    @tasks.loop(minutes=1)
    async def ping_roles(self):
        now = datetime.now(EASTERN_TIMEZONE)
        weekday = now.weekday()

        print(
            f"[Scheduler] Loop running. Current ET: {now:%Y-%m-%d %H:%M:%S %Z}, Weekday: {weekday}"
        )

        if not config.GUILD_ID:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            print(f"[Scheduler] Could not find guild with ID {config.GUILD_ID}.")
            return

        for sched in config.PING_SCHEDULES:  # sched is now PingSchedule
            print(
                f"Checking schedule for role {sched.role_id} in channel {sched.ch_id}"
            )

            if weekday not in sched.days:
                print(
                    f"Skipping: Today ({weekday}) is not in scheduled days {sched.days}"
                )
                continue

            channel = guild.get_channel(sched.ch_id)
            if not channel:
                print(f"Skipping: Could not find channel with ID {sched.ch_id}")
                continue

            # Send ping
            if now.hour == sched.ping_hour and now.minute == sched.ping_min:
                role = guild.get_role(sched.role_id)
                if role:
                    await channel.send(f"{role.mention} {sched.msg}")
                    print(f"SUCCESS: Sent ping for '{sched.msg}' in #{channel.name}")
                else:
                    print(
                        f"ERROR: Could not find role with ID {sched.role_id} for a scheduled ping."
                    )

            # Purge channel
            if (
                sched.delete_hour is not None
                and now.hour == sched.delete_hour
                and now.minute == sched.delete_min
            ):
                if channel.id not in config.EXCLUDED_CHANNELS:
                    await channel.purge(limit=1000)
                    print(f"SUCCESS: Cleared messages in #{channel.name}")

    @ping_roles.before_loop
    async def before_ping_roles(self):
        await self.bot.wait_until_ready()
        print("[Scheduler] Task loop is ready and running on Eastern Time.")

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
            return

        # === TRIGGER MODE ===
        if not 0 <= index < len(config.PING_SCHEDULES):
            await interaction.response.send_message(
                f"❌ **Error:** Invalid index."
                f" Please provide a number between 0 and {len(config.PING_SCHEDULES) - 1}.",
                ephemeral=True,
            )
            return

        sched_to_test = config.PING_SCHEDULES[index]
        channel = guild.get_channel(sched_to_test.ch_id)
        if not channel:
            await interaction.response.send_message(
                f"❌ **Error:** Cannot trigger. Channel ID `{sched_to_test.ch_id}` was not found.",
                ephemeral=True,
            )
            return

        role = guild.get_role(sched_to_test.role_id)
        if not role:
            await interaction.response.send_message(
                f"❌ **Error:** Cannot trigger. Role ID `{sched_to_test.role_id}` was not found.",
                ephemeral=True,
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
        except discord.errors.Forbidden:
            await interaction.response.send_message(
                f"❌ **Error:** The bot lacks permission to send messages in {channel.mention}.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"An unexpected error occurred: {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduling(bot))
