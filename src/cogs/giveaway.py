# src/cogs/giveaway.py

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

import config
from helpers.giveaway_helper import fetch_member_safe
from helpers.logging_helper import add_throttle, get_logger
from utility.giveaway_utils import parse_message_id, parse_utc_iso
from views.giveaway_view import GiveawayView
from data import database as db


logger = get_logger("giveaway")
heartbeat = get_logger("giveaway.heartbeat")
add_throttle(heartbeat, 900)


class Giveaway(commands.Cog, name="Giveaway"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways_loop.start()
        self._update_tasks = {}
        if not getattr(bot, "_giveaway_view_registered", False):
            bot.add_view(GiveawayView(self))
            bot._giveaway_view_registered = True

    async def cog_unload(self):
        try:
            self.check_giveaways_loop.cancel()
        except Exception:
            logger.exception("Failed to cancel check_giveaways_loop")

        try:
            for task in self._update_tasks.values():
                task.cancel()
        except Exception:
            logger.exception("Failed to cancel _update_tasks")

    # --- Private Functions ---
    def _find_field_index(self, embed: discord.Embed, name_prefix: str) -> int | None:
        """Case-insensitive search by field name prefix, returns index or None."""
        for i, f in enumerate(embed.fields):
            if f.name.lower().startswith(name_prefix.lower()):
                return i
        return None

    def _build_ended_embed(
        self,
        g_data: dict,
        winners: list[discord.Member],
        original_embed: Optional[discord.Embed] = None,
        status: str | None = None,
    ) -> discord.Embed:
        """Builds the final 'Giveaway Ended' embed."""
        embed = original_embed if original_embed else discord.Embed()
        embed.title = "🎉 Giveaway Ended! 🎉"
        embed.color = discord.Color.red()
        embed.description = None

        embed.clear_fields()
        embed.add_field(name="Prize", value=g_data.get("prize", "—"), inline=True)

        if not winners:
            winner_mentions = "No one! Maybe they all left?"
        else:
            winner_mentions = ", ".join(w.mention for w in winners)

        embed.add_field(name="Winners", value=winner_mentions, inline=False)
        if status:
            embed.add_field(name="Status", value=status, inline=False)
        return embed

    def _weights_for(self, entrants: list[discord.Member]) -> list[int]:
        weights = []
        for member in entrants:
            weight = config.DEFAULT_WEIGHT
            if member.roles:
                weight = max(
                    [weight] + [config.ROLE_WEIGHTS.get(r.id, 0) for r in member.roles]
                )
            weights.append(weight)
        return weights

    def _pick_winners(
        self, entrants: list[discord.Member], weights: list[int], k: int
    ) -> list[discord.Member]:
        k = min(k, len(entrants))
        if k <= 0:
            return []

        pool = list(zip(entrants, weights))
        total = sum(w for _, w in pool)
        winners: list[discord.Member] = []
        for _ in range(k):
            if total <= 0:
                break
            r = random.uniform(0, total)
            upto = 0.0
            for i, (m, w) in enumerate(pool):
                upto += w
                if upto >= r:
                    winners.append(m)
                    pool.pop(i)
                    total -= w
                    break
        return winners

    async def _get_message_channel(
        self, channel_id: int
    ) -> discord.TextChannel | discord.Thread | None:
        ch = self.bot.get_channel(channel_id)
        if isinstance(ch, (discord.TextChannel, discord.Thread)):
            return ch
        try:
            fetched = await self.bot.fetch_channel(channel_id)
            return (
                fetched
                if isinstance(fetched, (discord.TextChannel, discord.Thread))
                else None
            )
        except (discord.NotFound, discord.Forbidden):
            return None

    async def _get_valid_entrants(
        self, guild_id: int, entrant_ids: list[int]
    ) -> list[discord.Member]:
        """Fetches member objects for a list of user IDs, skipping those not in the guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.warning("Cannot get valid entrants; guild %d not found.", guild_id)
            return []

        entrants = []
        for uid in entrant_ids:
            if m := await fetch_member_safe(guild, uid):
                entrants.append(m)
        return entrants

    async def _debounced_update(self, message: discord.Message):
        """
        This is the actual task that waits, updates, and cleans up.
        It's designed to be created by _schedule_update.
        """
        try:

            await asyncio.sleep(5)
            message = await message.channel.fetch_message(message.id)
            await self._update_entry_count(message)
        except discord.NotFound:
            pass
        except Exception:
            logger.exception("Failed to update giveaway message %s", message.id)
        finally:
            self._update_tasks.pop(message.id, None)

    async def schedule_update(self, message: discord.Message):
        """
        Checks if an update task is already running for a message.
        If not, it creates and schedules a new one.
        """
        if message.id not in self._update_tasks:
            self._update_tasks[message.id] = asyncio.create_task(
                self._debounced_update(message)
            )

    async def _update_entry_count(self, message: discord.Message):
        """Fetches entry count from DB and updates the embed."""
        entry_count = await db.get_entry_count(message.id)

        # Safer embed handling
        embed = (
            message.embeds[0]
            if message.embeds
            else discord.Embed(color=discord.Color.gold())
        )

        idx = next((i for i, f in enumerate(embed.fields) if f.name == "Entries"), None)
        shown = None
        if idx is not None:
            try:
                shown = int(embed.fields[idx].value)
            except Exception:
                shown = None

        if shown == entry_count:
            return

        if idx is not None:
            embed.set_field_at(idx, name="Entries", value=str(entry_count), inline=True)
        else:
            embed.add_field(name="Entries", value=str(entry_count), inline=True)

        await message.edit(embed=embed)

    # --- GIVEAWAY ENDING LOGIC ---
    async def process_ended_giveaway(self, g: dict):
        """
        Finalize a giveaway:
        - Flip is_active in DB (atomic guard inside end_giveaway)
        - Fetch the message (using cache then API)
        - Compute winners from DB entrants
        - Edit embed robustly (works even if original embed is gone)
        """
        ctx = {}
        try:

            ctx = {"gid": g["guild_id"], "cid": g["channel_id"], "mid": g["message_id"]}

            flipped = await db.end_giveaway(g["message_id"])
            if not flipped:
                return

            # 2) Find channel (cache -> fetch)
            channel = await self._get_message_channel(g["channel_id"])
            if channel is None:
                logger.warning("Channel missing/forbidden", extra=ctx)
                return

            # 3) Fetch message
            try:
                message = await channel.fetch_message(g["message_id"])
            except discord.NotFound:
                logger.warning("Message not found", extra=ctx)
                return
            except discord.Forbidden:
                logger.warning("Forbidden fetching message", extra=ctx)
                return

            # 4) Load entrants
            entrant_ids = await db.get_giveaway_entrants(g["message_id"])
            logger.info(
                "Finalizing giveaway %s: %d entrants",
                g["message_id"],
                len(entrant_ids),
                extra=ctx,
            )

            # 5) Build a safe embed baseline (even if original had no embeds)
            embed = (
                message.embeds[0]
                if message.embeds
                else discord.Embed(color=discord.Color.gold())
            )
            embed.title = "🎉 Giveaway Ended! 🎉"
            embed.color = discord.Color.red()

            # Always show the prize
            prize_idx = self._find_field_index(embed, "Prize")
            if prize_idx is not None:
                embed.set_field_at(
                    prize_idx, name="Prize", value=g.get("prize", "—"), inline=True
                )
            else:
                embed.add_field(name="Prize", value=g.get("prize", "—"), inline=True)

            if not entrant_ids:
                final_embed = self._build_ended_embed(g, winners=[])
                try:
                    await message.edit(
                        content="This giveaway has ended.", embed=final_embed, view=None
                    )
                except Exception:
                    logger.exception(
                        "Failed to edit giveaway message %s", g.get("message_id")
                    )
                return

            # 7) skip users who left
            guild = self.bot.get_guild(g["guild_id"])
            if not guild:
                logger.warning("Guild not found", extra=ctx)
                return

            entrants = await self._get_valid_entrants(g["guild_id"], entrant_ids)

            if not entrants:
                final_embed = self._build_ended_embed(g, winners=[])
                try:
                    await message.edit(
                        content="This giveaway has ended.", embed=final_embed, view=None
                    )
                except Exception:
                    logger.exception("Failed to edit giveaway message", extra=ctx)
                return

            # 8) Pick winners
            weights = self._weights_for(entrants)
            winners = self._pick_winners(entrants, weights, int(g["winner_count"]))
            logger.info(
                "Picked %d winners for giveaway %s",
                len(winners),
                g["message_id"],
                extra=ctx,
            )

            final_embed = self._build_ended_embed(
                g, winners, message.embeds[0] if message.embeds else None
            )

            try:
                await message.edit(
                    content="This giveaway has ended.", embed=final_embed, view=None
                )
            except Exception:
                logger.exception("Failed to edit giveaway message", extra=ctx)

            if winners:
                winner_mentions = ", ".join(w.mention for w in winners)
                try:
                    await message.reply(
                        f"Congratulations {winner_mentions}! You won the **{g['prize']}**!"
                    )
                except Exception:
                    logger.exception("Failed to reply with winners", extra=ctx)

        except Exception:
            logger.exception("process_ended_giveaway failed", extra=ctx)

    # --- GIVEAWAY START COMMAND ---
    @app_commands.command(
        name="giveaway", description="[Admin] Start a giveaway in the current channel."
    )
    @app_commands.describe(
        prize="What is the prize for the giveaway?",
        duration="How many minutes the giveaway should last.",
        winners="How many winners should be drawn.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_start(
        self, interaction: discord.Interaction, prize: str, duration: int, winners: int
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        giveaway_message = None
        try:
            if not isinstance(
                interaction.channel, (discord.TextChannel, discord.Thread)
            ):
                return await interaction.followup.send(
                    "Run this in a text channel or thread.", ephemeral=True
                )

            if duration <= 0 or winners <= 0:
                await interaction.followup.send(
                    "Duration and winner count must be greater than zero.",
                    ephemeral=True,
                )
                return
            if winners > 50 or duration > 60 * 24 * 14:
                return await interaction.followup.send(
                    "Please keep winners ≤ 50 and duration ≤ 14 days.", ephemeral=True
                )

            now = datetime.now(timezone.utc)
            end_time = now + timedelta(minutes=duration)
            ts = int(end_time.timestamp())

            title_prize = prize if len(prize) <= 220 else prize[:217] + "..."
            embed = discord.Embed(
                title=f"🎉 Giveaway: {title_prize} 🎉", color=discord.Color.gold()
            )
            embed.add_field(name="Host", value=interaction.user.mention, inline=True)
            embed.add_field(name="Prize", value=prize, inline=True)
            embed.add_field(name="Winners", value=str(winners), inline=True)
            embed.add_field(name="Entries", value="0", inline=True)
            embed.add_field(
                name="Ends",
                value=f"<t:{ts}:R> (<t:{ts}:F>)",
                inline=False,
            )
            embed.description = "Click **Enter Giveaway** below to join."
            embed.set_footer(text=f"Started by {interaction.user.display_name}")

            await interaction.followup.send("Giveaway started!", ephemeral=True)
            giveaway_message = await interaction.channel.send(
                embed=embed, view=GiveawayView(self)
            )
            logger.info(
                "Giveaway started: mid=%s ends=%s winners=%s",
                giveaway_message.id,
                end_time.isoformat(),
                winners,
            )

            await db.create_giveaway(
                message=giveaway_message,
                prize=prize,
                end_time=end_time,
                winner_count=winners,
                host=interaction.user,
            )
        except Exception:
            if giveaway_message:
                logger.exception(
                    "create_giveaway failed; cleaning up message %s",
                    giveaway_message.id,
                )
                try:
                    await giveaway_message.edit(
                        view=None, content="Giveaway setup failed."
                    )
                except Exception:
                    pass
            else:
                logger.exception("create_giveaway failed before message could be sent.")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "⚠️ Giveaway setup failed.", ephemeral=True
                    )
                else:
                    await interaction.response.defer(
                        "⚠️ Giveaway setup failed.", ephemeral=True
                    )
            except Exception:
                pass

            return

    # --- BACKGROUND TASK FOR ENDING GIVEAWAYS ---
    @tasks.loop(seconds=config.GIVEAWAY_CHECK_INTERVAL)
    async def check_giveaways_loop(self):
        try:
            now = datetime.now(timezone.utc)
            due = await db.get_due_giveaways(now)
            heartbeat.debug("due=%d at %s", len(due), now)
            for g in due:
                await self.process_ended_giveaway(g)
        except Exception:
            logger.exception("check_giveaways_loop error (kept alive)")

    @check_giveaways_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(random.uniform(0.0, 0.4))

    @app_commands.command(
        name="giveaway-end",
        description="[Admin] Force finalize a giveaway by message ID or message link.",
    )
    @app_commands.describe(
        message_id_or_link="The message ID or full message link of the giveaway post"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_end_cmd(
        self, interaction: discord.Interaction, message_id_or_link: str
    ):
        await interaction.response.defer(ephemeral=True)
        mid = parse_message_id(message_id_or_link)
        if mid is None:
            return await interaction.followup.send(
                "❌ Invalid message ID or link.", ephemeral=True
            )

        rec = await db.get_giveaway_by_id(mid)
        if not rec:
            return await interaction.followup.send(
                "❌ No giveaway found with that message ID.", ephemeral=True
            )

        # cross-guild guard
        if rec["guild_id"] != interaction.guild.id:
            return await interaction.followup.send(
                "❌ That giveaway does not belong to this server.", ephemeral=True
            )

        try:
            await self.process_ended_giveaway(rec)
            await interaction.followup.send("✅ Giveaway finalized.", ephemeral=True)
        except Exception:
            logger.exception("Manual finalize error for giveaway %s", mid)
            await interaction.followup.send(
                "⚠️ Error while finalizing. Check logs.", ephemeral=True
            )

    @app_commands.command(
        name="giveaway-list",
        description="[Admin] List active giveaways in this server.",
    )
    @app_commands.describe(channel="Optionally filter by channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_list(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await db.list_active_giveaways_for_guild(interaction.guild.id)
            if channel:
                rows = [r for r in rows if r["channel_id"] == channel.id]

            if not rows:
                return await interaction.followup.send(
                    "No active giveaways.", ephemeral=True
                )

            embed = discord.Embed(
                title=f"Active Giveaways ({len(rows)})",
                color=discord.Color.gold(),
            )
            for r in rows[:25]:  # Discord embed sanity
                ts = int(parse_utc_iso(r["end_time"]).timestamp())
                embed.add_field(
                    name=f"ID {r['message_id']}",
                    value=(
                        f"• Prize: **{r['prize']}**\n"
                        f"• Winners: **{r['winner_count']}**\n"
                        f"• Channel: <#{r['channel_id']}>\n"
                        f"• Ends: <t:{ts}:R> (<t:{ts}:F>)"
                    ),
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("giveaway_list failed")
            await interaction.followup.send(
                "⚠️ Failed to list giveaways.", ephemeral=True
            )

    @app_commands.command(
        name="giveaway-reroll",
        description="[Admin] Reroll winners for a finished giveaway.",
    )
    @app_commands.describe(
        message_id_or_link="The message ID or link",
        winners="Number of winners to reroll (default=1)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        message_id_or_link: str,
        winners: Optional[int] = 1,
    ):
        await interaction.response.defer(ephemeral=True)
        mid = parse_message_id(message_id_or_link)
        if mid is None:
            return await interaction.followup.send(
                "❌ Invalid message ID or link.", ephemeral=True
            )

        rec = await db.get_giveaway_by_id(mid)
        if not rec or rec["guild_id"] != interaction.guild.id:
            return await interaction.followup.send(
                "❌ Giveaway not found in this server.", ephemeral=True
            )

        if rec.get("is_active"):
            return await interaction.followup.send(
                "⏳ That giveaway is still active. End it first.", ephemeral=True
            )

        entrant_ids = await db.get_giveaway_entrants(mid)
        if not entrant_ids:
            return await interaction.followup.send(
                "No entrants to reroll.", ephemeral=True
            )

        guild = self.bot.get_guild(rec["guild_id"])
        if not guild:
            logger.warning(
                "Reroll: guild %s not found for message %s", rec["guild_id"], mid
            )
            return

        entrants = await self._get_valid_entrants(rec["guild_id"], entrant_ids)

        weights = self._weights_for(entrants)
        k = max(1, min(int(winners or 1), len(entrants)))

        rerolled_winners = self._pick_winners(entrants, weights, k)
        if not rerolled_winners:
            return await interaction.followup.send(
                "No eligible entrants to reroll.", ephemeral=True
            )
        mentions = ", ".join(w.mention for w in rerolled_winners)

        channel = self.bot.get_channel(
            rec["channel_id"]
        ) or await self.bot.fetch_channel(rec["channel_id"])
        try:
            msg = await channel.fetch_message(mid)
        except Exception:
            return await interaction.followup.send(
                f"Rerolled: {mentions}\n(Original message not found to edit.)",
                ephemeral=True,
            )

        embed = (
            msg.embeds[0] if msg.embeds else discord.Embed(color=discord.Color.gold())
        )
        idx = next(
            (i for i, f in enumerate(embed.fields) if f.name == "Rerolled Winners"),
            None,
        )
        if idx is not None:
            embed.set_field_at(
                idx, name="Rerolled Winners", value=mentions, inline=False
            )
        else:
            embed.add_field(name="Rerolled Winners", value=mentions, inline=False)
        try:
            await msg.edit(embed=embed)
        except Exception:
            logger.exception("Failed to edit message for reroll %s", mid)
        try:
            await msg.reply(f"🎲 Reroll: {mentions}")
        except Exception:
            logger.exception("Failed to reply reroll winners %s", mid)

        await interaction.followup.send("✅ Rerolled.", ephemeral=True)


async def setup(bot: commands.Bot):

    await bot.add_cog(Giveaway(bot))
