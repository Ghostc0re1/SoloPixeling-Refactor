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

        success, note = await db.add_entry(interaction.message.id, interaction.user.id)
        await interaction.followup.send(note, ephemeral=True)

        # Optimistic UI only on success
        if success is True:
            embed = (
                interaction.message.embeds[0]
                if interaction.message.embeds
                else discord.Embed()
            )
            idx = next(
                (i for i, f in enumerate(embed.fields) if f.name == "Entries"), None
            )
            if idx is not None:
                try:
                    current = int(embed.fields[idx].value)
                except Exception:
                    current = 0
                embed.set_field_at(
                    idx, name="Entries", value=str(current + 1), inline=True
                )
            else:
                embed.add_field(name="Entries", value="1", inline=True)
            try:
                await interaction.message.edit(embed=embed)
            except Exception:
                pass

        await self.cog.schedule_update(interaction.message)
