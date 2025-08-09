# cogs/giveaway.py

import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands

from views.giveaway_view import GiveawayView

from data import database as db
import config


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways_loop.start()

    async def cog_unload(self):
        # Gracefully stop the task when the cog is unloaded.
        self.check_giveaways_loop.cancel()

    # --- GIVEAWAY START COMMAND ---
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
                name="Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=False
            )
            embed.set_footer(text=f"Started by {interaction.user.display_name}")

            await interaction.response.send_message("Giveaway started!", ephemeral=True)
            giveaway_message = await interaction.channel.send(
                embed=embed, view=GiveawayView()
            )

            await db.create_giveaway(
                message=giveaway_message,
                prize=prize,
                end_time=end_time,
                winner_count=winners,
                host=interaction.user,
            )
        except Exception as e:
            logging.error("Error in /giveaway command: %s", e)
            # Use followup for responses after an initial response
            await interaction.followup.send("An error occurred.", ephemeral=True)

    # --- BACKGROUND TASK FOR ENDING GIVEAWAYS ---
    @tasks.loop(seconds=config.GIVEAWAY_CHECK_INTERVAL)
    async def check_giveaways_loop(self):
        active_giveaways = await db.get_active_giveaways()
        now = datetime.now(timezone.utc)

        for g in active_giveaways:
            end_time = datetime.fromisoformat(g["end_time"])
            if now >= end_time:
                await self.process_ended_giveaway(g)

    @check_giveaways_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    # --- GIVEAWAY ENDING LOGIC ---
    async def process_ended_giveaway(self, g: dict):
        """Contains all the logic from your old on_timeout method."""
        if not await db.end_giveaway(g["message_id"]):
            return

        channel = self.bot.get_channel(g["channel_id"])
        if not channel:
            return

        try:
            message = await channel.fetch_message(g["message_id"])
        except (discord.NotFound, discord.Forbidden):
            return

        # Get all entrants from the database
        entrant_ids = await db.get_giveaway_entrants(g["message_id"])
        if not entrant_ids:
            embed = message.embeds[0]
            embed.title = "🎉 Giveaway Ended! 🎉"
            embed.color = discord.Color.red()
            embed.clear_fields()
            embed.add_field(name="Prize", value=g["prize"])
            embed.add_field(name="Status", value="Ended with no entries.")
            await message.edit(
                content="This giveaway has ended.", embed=embed, view=None
            )
            return

        # --- Winner selection logic (reused from your old view) ---
        guild = self.bot.get_guild(g["guild_id"])
        entrants = [m for uid in entrant_ids if (m := guild.get_member(uid))]

        if not entrants:
            # Handle no valid members found (e.g., they all left the server)
            return

        weights = self._weights_for(entrants)
        winners = self._pick_winners(entrants, weights, g["winner_count"])

        # Update the original embed
        embed = message.embeds[0]
        embed.title = "🎉 Giveaway Ended! 🎉"
        embed.color = discord.Color.red()

        winner_mentions = (
            ", ".join(w.mention for w in winners)
            if winners
            else "No one! Maybe they all left?"
        )

        for idx, field in enumerate(embed.fields):
            if field.name.lower().startswith("winner"):
                embed.set_field_at(
                    idx, name="Winners", value=winner_mentions, inline=False
                )
                break
        else:
            embed.add_field(name="Winners", value=winner_mentions, inline=False)

        await message.edit(content="This giveaway has ended.", embed=embed, view=None)

        if winners:
            await message.reply(
                f"Congratulations {winner_mentions}! You won the **{g['prize']}**!"
            )

    # --- HELPER METHODS FOR WINNER SELECTION (moved from the view) ---
    def _weights_for(self, entrants: list[discord.Member]) -> list[int]:
        weights = []
        for member in entrants:
            weight = config.DEFAULT_WEIGHT
            if member.roles:
                weight = max(
                    [weight] + [config.ROLE_WEIGHTS.get(r.id, 0) for r in member.roles]
                )
            weights.append(weight)
        return weights

    def _pick_winners(
        self, entrants: list[discord.Member], weights: list[int], k: int
    ) -> list[discord.Member]:
        k = min(k, len(entrants))
        if k == 0:
            return []

        selected, seen = [], set()

        max_attempts = k * 10
        attempts = 0

        while len(selected) < k and attempts < max_attempts:
            pick = random.choices(entrants, weights=weights, k=1)[0]
            if pick.id not in seen:
                seen.add(pick.id)
                selected.append(pick)
            attempts += 1

        return selected


async def setup(bot: commands.Bot):
    # This is CRITICAL. It tells the bot to listen for the
    # persistent view's buttons when it starts up.
    bot.add_view(GiveawayView())

    await bot.add_cog(Giveaway(bot))
