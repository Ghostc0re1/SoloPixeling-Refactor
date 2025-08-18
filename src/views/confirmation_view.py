# You can place this class inside your cog file


import discord

from data import database


class ConfirmView(discord.ui.View):
    def __init__(self, guild_id: int, date_str: str):
        super().__init__(timeout=30)  # The view will time out after 30 seconds
        self.guild_id = guild_id
        self.date_str = date_str

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Disable the buttons to prevent double-clicks
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        # Call the database function to delete the data
        deleted_count = await database.reset_daily_xp_for_guild(
            self.guild_id, self.date_str
        )

        # Report the result
        await interaction.followup.send(
            f"✅ **Deletion Complete!**\n"
            f"Deleted **{deleted_count}** daily XP rows for guild `{self.guild_id}` on `{self.date_str}`.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Disable the buttons and provide feedback
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.", view=self
        )
