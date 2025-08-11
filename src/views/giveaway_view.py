# src/views/giveaway_view.py

import discord
from data import database as db


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _update_entry_count(self, message: discord.Message):
        """Fetches entry count from DB and updates the embed."""
        entry_count = await db.get_entry_count(message.id)

        # Safer embed handling
        embed = (
            message.embeds[0]
            if message.embeds
            else discord.Embed(color=discord.Color.gold())
        )

        # Ensure Entries field exists
        for i, f in enumerate(embed.fields):
            if f.name == "Entries":
                embed.set_field_at(
                    i, name="Entries", value=str(entry_count), inline=True
                )
                break
        else:
            embed.add_field(name="Entries", value=str(entry_count), inline=True)

        await message.edit(embed=embed)

    @discord.ui.button(
        label="Enter Giveaway",
        style=discord.ButtonStyle.primary,
        emoji="🎉",
        custom_id="persistent_giveaway:enter",
    )
    async def enter_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        rec = await db.get_giveaway_by_id(interaction.message.id)
        if not rec or not rec.get("is_active"):
            return await interaction.response.send_message(
                "That giveaway has ended.", ephemeral=True
            )

        success, msg = await db.add_entry(interaction.message.id, interaction.user.id)
        await interaction.response.send_message(msg, ephemeral=True)
        if success:
            await self._update_entry_count(interaction.message)
