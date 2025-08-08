# cogs/giveaway.py
from datetime import datetime, timedelta, timezone
import logging
import discord

from discord.ext import commands
from discord import app_commands
from views.giveaway_view import GiveawayView


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="giveaway", description="[Admin] Start a giveaway in the current channel."
    )
    @app_commands.describe(
        prize="What is the prize for the giveaway?",
        duration="How many minutes the giveaway should last.",
        winners="How many winners should be drawn.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(
        self, interaction: discord.Interaction, prize: str, duration: int, winners: int
    ):
        try:
            if duration <= 0 or winners <= 0:
                await interaction.response.send_message(
                    "Duration and winner count must be greater than zero.",
                    ephemeral=True,
                )
                return

            end_time = datetime.now(timezone.utc) + timedelta(minutes=duration)

            embed = discord.Embed(
                title=f"🎉 Giveaway: {prize} 🎉",
                color=discord.Color.gold(),
            )
            embed.add_field(name="Host", value=interaction.user.mention, inline=True)
            embed.add_field(name="Entries", value="0", inline=True)
            embed.add_field(name="Winners", value=str(winners), inline=True)
            embed.add_field(
                name="Ends",
                value=f"<t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:F>)",
                inline=False,
            )
            embed.set_footer(text=f"Started by {interaction.user.display_name}")

            view = GiveawayView(
                end_time=end_time,
                prize=prize,
                winner_count=winners,
                host=interaction.user,
            )

            await interaction.response.send_message("Giveaway started!", ephemeral=True)
            giveaway_message = await interaction.channel.send(embed=embed, view=view)

            view.message = giveaway_message
        except Exception as e:
            logging.error("Error in /giveaway command: %s", e)
            await interaction.followup.send(
                "An unexpected error occurred while trying to start a giveaway.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
