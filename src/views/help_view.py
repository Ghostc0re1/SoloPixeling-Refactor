import discord


class HelpView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=180.0)
        self.embeds = embeds
        self.current_page = 0
        self.message = None  # To store the message for on_timeout editing

    def update_buttons(self):
        """Enable or disable buttons based on the current page."""
        if len(self.embeds) <= 1:
            self.clear_items()  # No buttons if there's only one page
            return
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.embeds[self.current_page], view=self
            )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.embeds[self.current_page], view=self
            )

    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)
