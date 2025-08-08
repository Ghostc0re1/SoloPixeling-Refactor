from typing import Optional

#
import discord


class PurgeConfirmationView(discord.ui.View):
    def __init__(self, channel_to_purge: discord.TextChannel, limit: Optional[int]):
        super().__init__(timeout=30.0)
        self.channel_to_purge = channel_to_purge
        self.limit = limit  # Store the limit

    async def disable_all_items(self):
        """Disables all buttons in the view."""
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @discord.ui.button(label="Confirm Purge", style=discord.ButtonStyle.danger)
    async def confirm_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await interaction.response.defer()
        await self.disable_all_items()

        deleted_messages = await self.channel_to_purge.purge(limit=self.limit)

        await interaction.followup.send(
            f"✅ **Success!** Purged **{len(deleted_messages)}** "
            f"messages from {self.channel_to_purge.mention}.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await interaction.response.defer()
        await self.disable_all_items()
        await interaction.followup.send(
            " Phew! Purge operation canceled.", ephemeral=True
        )

    async def on_timeout(self):
        await self.disable_all_items()
