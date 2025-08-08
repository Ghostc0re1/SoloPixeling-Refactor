import discord


class LeaderboardView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, all_rows: list):
        super().__init__(timeout=180.0)
        self.interaction = interaction
        self.all_rows = all_rows
        self.current_page = 0
        self.per_page = 10
        self.total_pages = max(0, (len(self.all_rows) - 1) // self.per_page)
        self.message = None

    async def generate_embed(self) -> discord.Embed:
        start_index = self.current_page * self.per_page
        end_index = start_index + self.per_page
        page_rows = self.all_rows[start_index:end_index]

        embed = discord.Embed(title="🏆 Server Leaderboard", color=discord.Color.gold())
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages + 1}")

        if not page_rows:
            embed.description = "There are no users on this page."
            return embed

        leaderboard_entries = []
        for i, (uid, lvl, xp) in enumerate(page_rows, start=start_index + 1):
            entry = f"**{i}.** <@{uid}>: **Level {lvl}** ({xp} XP)"
            leaderboard_entries.append(entry)

        embed.description = "\n".join(leaderboard_entries)
        return embed

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == 0
        self.children[2].disabled = self.current_page >= self.total_pages
        self.children[3].disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="«", style=discord.ButtonStyle.secondary)
    async def first_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        if self.current_page > 0:
            self.current_page = 0
            self.update_buttons()
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="←", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="→", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_buttons()
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="»", style=discord.ButtonStyle.primary)
    async def last_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page = self.total_pages
            self.update_buttons()
            embed = await self.generate_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.errors.NotFound:
                pass
