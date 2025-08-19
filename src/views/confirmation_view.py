import discord
from data import database


class ConfirmView(discord.ui.View):
    def __init__(
        self,
        guild_id: int,
        date_str: str,
        author_id: int | None = None,
        *,
        timeout: float = 30,
    ):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.date_str = date_str
        self.author_id = (
            author_id  # only this user can press (optional but recommended)
        )

    async def _only_invoker(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None:
            return True
        if interaction.user and interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "❌ You can’t use this button.", ephemeral=True
        )
        return False

    async def _disable_all(self, interaction: discord.Interaction, *, keep_view: bool):
        for item in self.children:
            item.disabled = True
        # Prefer editing the original message. Use response if not used yet; otherwise edit.
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=(self if keep_view else None))
        else:
            try:
                await interaction.edit_original_response(
                    view=(self if keep_view else None)
                )
            except Exception:
                # Fallback: try followup
                if interaction.followup:
                    await interaction.followup.edit_message(
                        interaction.message.id, view=(self if keep_view else None)
                    )

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._only_invoker(interaction):
            return
        # Disable UI immediately to prevent double clicks
        for item in self.children:
            item.disabled = True
        try:
            deleted = await database.reset_daily_xp_after_announce(
                self.guild_id, self.date_str
            )
            content = f"🧹 Deleted `{deleted}` rows for `{self.date_str}` (announcement recorded)."
        except Exception as e:
            content = f"❌ Delete refused: announcement not recorded or other error.\n```{e}```"

        # Edit message content and remove the view
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=content, view=None)
        else:
            try:
                await interaction.edit_original_response(content=content, view=None)
            except Exception:
                if interaction.followup:
                    await interaction.followup.edit_message(
                        interaction.message.id, content=content, view=None
                    )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._only_invoker(interaction):
            return
        await self._disable_all(interaction, keep_view=False)
        # Now update content to indicate cancel
        msg = "❌ Deletion cancelled."
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=msg, view=None)
        else:
            try:
                await interaction.edit_original_response(content=msg, view=None)
            except Exception:
                if interaction.followup:
                    await interaction.followup.edit_message(
                        interaction.message.id, content=msg, view=None
                    )

    async def on_timeout(self) -> None:
        # If the view times out, try to disable the buttons silently
        try:
            for item in self.children:
                item.disabled = True
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=None)
        except Exception:
            pass
