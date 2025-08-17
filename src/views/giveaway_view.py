# src/views/giveaway_view.py
from typing import TYPE_CHECKING
import discord
from data import database as db


if TYPE_CHECKING:
    from ..cogs.giveaway import Giveaway


class GiveawayView(discord.ui.View):
    def __init__(self, cog: "Giveaway"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Enter Giveaway",
        style=discord.ButtonStyle.primary,
        emoji="🎉",
        custom_id="persistent_giveaway:enter",
    )
    async def enter_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        rec = await db.get_giveaway_by_id(interaction.message.id)
        if not rec or not rec.get("is_active"):
            return await interaction.followup.send(
                "That giveaway has ended.", ephemeral=True
            )

        success, msg = await db.add_entry(interaction.message.id, interaction.user.id)

        await interaction.followup.send(msg, ephemeral=True)

        if success:
            await self.cog.schedule_update(interaction.message)
