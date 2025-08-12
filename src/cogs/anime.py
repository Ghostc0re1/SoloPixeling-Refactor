import asyncio
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

import config  # Optional: ANIME_RECS_CHANNEL_ID = int | None

ANILIST_URL = "https://graphql.anilist.co"
CACHE_TTL = 300  # seconds


SEARCH_QUERY = """
query ($search: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    media(search: $search, type: ANIME, isAdult: false, sort: POPULARITY_DESC) {
      id
      idMal
      title { userPreferred romaji english native }
      format
      episodes
      season
      seasonYear
      averageScore
      coverImage { large }
      siteUrl
    }
  }
}
"""

DETAILS_QUERY = """
query ($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    idMal
    title { userPreferred }
    format
    episodes
    season
    seasonYear
    averageScore
    coverImage { large }
    siteUrl
    description(asHtml: false)
  }
}
"""


def _season_str(item: Dict[str, Any]) -> str:
    s, y = item.get("season"), item.get("seasonYear")
    return f"{s.title()} {y}" if s and y else (str(y) if y else "—")


def _opt_score(v: Optional[int | float]) -> Optional[str]:
    return f"{v}" if v else None


def _option_label(item: Dict[str, Any]) -> Tuple[str, str]:
    t = (
        (item.get("title") or {}).get("userPreferred")
        or (item.get("title") or {}).get("romaji")
        or (item.get("title") or {}).get("english")
        or (item.get("title") or {}).get("native")
        or "Unknown"
    )
    desc_bits = [
        item.get("format") or "—",
        f"{item.get('episodes') or '?'} eps",
        _season_str(item),
    ]
    if item.get("averageScore"):
        desc_bits.append(f"★ {item['averageScore']}")
    return str(t)[:100], " • ".join(desc_bits)[:100]


class AnimeCog(commands.Cog):
    """Anime recommendations via AniList with autocomplete + embed posting."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self._search_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._detail_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._guild_channels: Dict[int, int] = {}
        self._global_channel_id = getattr(config, "ANIME_RECS_CHANNEL_ID", None)

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    # ---------- GraphQL helpers ----------
    async def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        assert self.session is not None
        async with self.session.post(
            ANILIST_URL,
            json={"query": query, "variables": variables},
            headers={"Accept": "application/json"},
        ) as r:
            # AniList exposes X-RateLimit-* headers; you could read & backoff if needed.
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"AniList error {r.status}: {text[:200]}")
            return await r.json()

    async def _search(self, query: str) -> List[Dict[str, Any]]:
        key = query.lower().strip()
        now = dt.datetime.now().timestamp()
        if key in self._search_cache:
            ts, items = self._search_cache[key]
            if now - ts < CACHE_TTL:
                return items

        data = await self._graphql(
            SEARCH_QUERY, {"search": query, "page": 1, "perPage": 10}
        )
        items = data["data"]["Page"]["media"] or []
        self._search_cache[key] = (now, items)
        return items

    async def _details(self, anilist_id: int) -> Dict[str, Any]:
        now = dt.datetime.now().timestamp()
        if anilist_id in self._detail_cache:
            ts, item = self._detail_cache[anilist_id]
            if now - ts < CACHE_TTL:
                return item

        data = await self._graphql(DETAILS_QUERY, {"id": anilist_id})
        item = data["data"]["Media"]
        self._detail_cache[anilist_id] = (now, item)
        return item

    # ---------- UI helpers ----------
    def _target_channel(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if gid and gid in self._guild_channels:
            ch = interaction.guild.get_channel(self._guild_channels[gid])
            if ch:
                return ch
        if self._global_channel_id and interaction.guild:
            ch = interaction.guild.get_channel(self._global_channel_id)
            if ch:
                return ch
        return interaction.channel

    def _embed(self, item: Dict[str, Any], user: discord.Member, reason: Optional[str]):
        title = (item.get("title") or {}).get("userPreferred") or "Unknown"
        url = item.get("siteUrl") or f"https://anilist.co/anime/{item.get('id')}"
        emb = discord.Embed(title=title, url=url)
        img = ((item.get("coverImage") or {}).get("large")) or None
        if img:
            emb.set_thumbnail(url=img)

        fields = [
            ("Format", str(item.get("format") or "—"), True),
            ("Episodes", str(item.get("episodes") or "?"), True),
            ("Season", _season_str(item), True),
        ]
        if item.get("averageScore"):
            fields.append(("Score", f"{item['averageScore']}", True))
        for n, v, inline in fields:
            emb.add_field(name=n, value=v, inline=inline)

        desc = (item.get("description") or "No synopsis available.")[:512]
        emb.add_field(name="Synopsis", value=desc, inline=False)

        footer = f"Recommended by {user.display_name}"
        if reason:
            footer += f" • {reason[:60]}"
        emb.set_footer(text=footer)
        return emb

    # ---------- Commands ----------
    @app_commands.command(
        name="anime", description="Search AniList and post an anime recommendation"
    )
    @app_commands.describe(
        pick="Start typing to search and then select",
        reason="Optional note to include with your rec",
    )
    async def anime(
        self, interaction: discord.Interaction, pick: str, reason: Optional[str] = None
    ):
        try:
            anilist_id = int(pick)
        except ValueError:
            await interaction.response.send_message(
                "Please select an anime from the suggestions.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = await self._details(anilist_id)
        except Exception as e:
            await interaction.followup.send(f"Lookup failed: {e}", ephemeral=True)
            return

        channel = self._target_channel(interaction)
        embed = self._embed(item, user=interaction.user, reason=reason)

        view = discord.ui.View()
        site_url = item.get("siteUrl") or f"https://anilist.co/anime/{item.get('id')}"
        view.add_item(
            discord.ui.Button(
                label="Open on AniList", url=site_url, style=discord.ButtonStyle.link
            )
        )

        id_mal = item.get("idMal")
        if id_mal:
            view.add_item(
                discord.ui.Button(
                    label="Open on MyAnimeList",
                    url=f"https://myanimelist.net/anime/{id_mal}",
                    style=discord.ButtonStyle.link,
                )
            )

        msg = await channel.send(embed=embed, view=view)
        await interaction.followup.send(
            f"Posted in {channel.mention}: {msg.jump_url}", ephemeral=True
        )

    @anime.autocomplete("pick")
    async def anime_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        q = current.strip()
        if not q:
            return []
        try:
            results = await asyncio.wait_for(self._search(q), timeout=6)
        except Exception:
            return []
        choices: List[app_commands.Choice[str]] = []
        for item in results[:25]:
            label, desc = _option_label(item)
            choices.append(
                app_commands.Choice(name=f"{label} — {desc}", value=str(item["id"]))
            )
        return choices

    @app_commands.command(
        name="anime_setchannel",
        description="Set the channel where recommendations should be posted",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        self._guild_channels[interaction.guild_id] = channel.id
        await interaction.response.send_message(
            f"Anime recs will now be posted to {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AnimeCog(bot))
