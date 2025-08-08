import logging
import discord
from discord.ext import commands
from discord import app_commands
from views.help_view import HelpView


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help", description="Shows a list of all available commands."
    )
    async def help(self, interaction: discord.Interaction):
        # Defer the response to handle cases where command processing might be slow.
        await interaction.response.defer(ephemeral=True)
        try:
            categorized_commands = {}

            for command in self.bot.tree.get_commands():
                cog = None
                if isinstance(command, app_commands.Group):
                    # For a group, get the cog from its first subcommand, if it exists
                    if command.commands:
                        cog = command.commands[0].binding
                else:
                    # For a regular command, get the cog directly
                    cog = command.binding

                # Use the cog's name for the category, default to "General"
                category = (
                    cog.__class__.__name__.replace("Cog", "") if cog else "General"
                )

                if category not in categorized_commands:
                    categorized_commands[category] = []

                if isinstance(command, app_commands.Group):
                    sub_commands = [
                        f"`/{command.name} {sub.name}` - {sub.description}"
                        for sub in command.commands
                    ]
                    categorized_commands[category].extend(sub_commands)
                else:
                    categorized_commands[category].append(
                        f"`/{command.name}` - {command.description}"
                    )

            if not categorized_commands:
                await interaction.followup.send("No commands found.", ephemeral=True)
                return

            embeds = []
            # Sort categories alphabetically for a consistent order
            for category, commands_list in sorted(categorized_commands.items()):
                embed = discord.Embed(
                    title=f"**{category} Commands**",
                    description="\n".join(commands_list),
                    color=discord.Color.blue(),
                )
                embeds.append(embed)

            # Add page numbers to the footer of each embed
            for i, embed in enumerate(embeds):
                embed.set_footer(text=f"Page {i + 1}/{len(embeds)}")

            view = HelpView(embeds)
            view.update_buttons()

            message = await interaction.followup.send(
                embed=embeds[0], view=view, ephemeral=True
            )
            view.message = message

        except Exception as e:
            logging.error("Error in /help command: %s", e)
            await interaction.followup.send(
                "An unexpected error occurred while trying to show the help menu.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
