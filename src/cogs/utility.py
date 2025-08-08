import discord
from discord.ext import commands
from discord import app_commands
from views.bugreport_view import BugReportModal


class UtilityCog(commands.Cog, name="Utility"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="bugreport", description="Submit a bug report to the developers."
    )
    async def bug_report(self, interaction: discord.Interaction):
        # This command opens the modal
        await interaction.response.send_modal(BugReportModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
