import random
from datetime import datetime, timezone
import asyncio

#
import discord

#
import config
from helpers.giveaway_utils import GiveawayState


class GiveawayView(discord.ui.View):
    def __init__(
        self, end_time: datetime, prize: str, winner_count: int, host: discord.Member
    ):
        remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
        super().__init__(timeout=remaining if remaining > 0 else 0)
        self.end_time = end_time
        self.state = GiveawayState(
            prize=prize,
            winner_count=winner_count,
            host_id=host.id,
            entries=set(),
            winners=[],
        )
        self.message: discord.Message | None = None
        self.lock = asyncio.Lock()

    @discord.ui.button(
        label="Enter Giveaway", style=discord.ButtonStyle.primary, emoji="🎉"
    )
    async def enter_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        async with self.lock:
            if interaction.user.id in self.state.entries:
                await interaction.response.send_message(
                    "You have already entered this giveaway!", ephemeral=True
                )
                return

            self.state.entries.add(interaction.user.id)

            if self.message:
                updated_embed = self._refresh_embed_entries()
                await self.message.edit(view=self, embed=updated_embed)

        await interaction.response.send_message(
            "You have entered the giveaway!", ephemeral=True
        )

    #
    # --- Private Functions ---
    #
    def _disable_buttons(self) -> None:
        for child in self.children:
            child.disabled = True

    def _collect_entrants(self) -> list[discord.Member]:
        guild = self.message.guild if self.message else None
        if not guild:
            return []
        return [m for uid in self.state.entries if (m := guild.get_member(uid))]

    def _weights_for(self, entrants: list[discord.Member]) -> list[int]:
        weights = []
        for member in entrants:
            weight = config.DEFAULT_WEIGHT
            # use max() once rather than loop+assign
            if member.roles:
                weight = max(
                    [weight] + [config.ROLE_WEIGHTS.get(r.id, 0) for r in member.roles]
                )
            weights.append(weight)
        return weights

    def _pick_winners(
        self, entrants: list[discord.Member], weights: list[int]
    ) -> list[discord.Member]:
        k = min(self.state.winner_count, len(entrants))
        if k == 0:
            return []
        try:
            pool = set(random.choices(entrants, weights=weights, k=k * 5))
            return random.sample(list(pool), k=k)
        except (ValueError, IndexError):
            return random.sample(entrants, k=k)

    def _mark_ended_embed(self, embed: discord.Embed) -> discord.Embed:
        embed.title = "🎉 Giveaway Ended! 🎉"
        embed.color = discord.Color.red()
        return embed

    def _refresh_embed_entries(self) -> discord.Embed | None:
        if not self.message:
            return None
        embed = self.message.embeds[0]
        for idx, field in enumerate(embed.fields):
            if field.name == "Entries":
                embed.set_field_at(
                    idx, name="Entries", value=str(len(self.state.entries)), inline=True
                )
                break
        return embed

    #
    # --- ENDREGION: Private Functions ---
    #
    async def on_timeout(self):
        if not self.message:
            return
        embed = self._mark_ended_embed(self.message.embeds[0])
        self._disable_buttons()

        entrants = self._collect_entrants()
        if not entrants:
            await self.message.edit(
                content="This giveaway has ended.", embed=embed, view=self
            )
            await self.message.channel.send(
                "No one entered the giveaway, so there are no winners."
            )
            return

        weights = self._weights_for(entrants)
        winners = self._pick_winners(entrants, weights)
        self.state.winners = winners

        winner_mentions = (
            ", ".join(w.mention for w in winners) if winners else "No winners"
        )
        for idx, field in enumerate(embed.fields):
            if field.name.lower().startswith("winner"):
                embed.set_field_at(
                    idx, name="Winners", value=winner_mentions, inline=False
                )
                break
        else:
            embed.add_field(name="Winners", value=winner_mentions, inline=False)

        self._refresh_embed_entries()
        await self.message.edit(
            content="This giveaway has ended.", embed=embed, view=self
        )

        if winners:
            await self.message.reply(
                f"Congratulations {winner_mentions}! You won the **{self.state.prize}**!"
            )
