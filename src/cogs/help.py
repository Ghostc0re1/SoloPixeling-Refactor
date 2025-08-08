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

            category = cog.__class__.__name__.replace("Cog", "") if cog else "General"

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

        embeds = []
        # Sort categories alphabetically for a consistent order
        for category, commands_list in sorted(categorized_commands.items()):
            embed = discord.Embed(
                title=f"**{category} Commands**",
                description="\n".join(commands_list),
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"Page {len(embeds) + 1}/{len(categorized_commands)}")
            embeds.append(embed)

        if not embeds:
            return await interaction.response.send_message(
                "No commands found.", ephemeral=True
            )

        view = HelpView(embeds)
        view.update_buttons()

        await interaction.response.send_message(
            embed=embeds[0], view=view, ephemeral=True
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
