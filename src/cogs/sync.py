# src/cogs/sync.py

from discord.ext import commands


class Syncer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, spec: str = None):
        """
        An owner-only command to sync application commands.

        Usage:
        !sync -> Syncs global commands.
        !sync ~ -> Syncs commands to the current guild.
        !sync ^ -> Clears all commands from the current guild and syncs.
        """

        if spec == "~":
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"Synced {len(synced)} commands to this guild.")
            return

        if spec == "^":
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send("Cleared all commands from this guild and re-synced.")
            return

        synced = await self.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands globally.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Syncer(bot))
