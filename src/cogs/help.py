import inspect
import discord
from discord.ext import commands
from discord import app_commands
from helpers.logging_helper import get_logger
from views.help_view import HelpView

log = get_logger("help")


async def user_can_run(
    cmd: app_commands.Command | app_commands.Group, interaction: discord.Interaction
) -> bool:
    # 1) DM vs Guild
    if interaction.guild is None:
        # If command disallows DMs, hide it
        if hasattr(cmd, "dm_permission") and cmd.dm_permission is False:
            return False
    else:
        # In a guild: enforce default member permissions if present
        required = getattr(cmd, "default_permissions", None) or getattr(
            cmd, "default_member_permissions", None
        )
        if required is not None:
            req_bits = (
                int(required.value) if hasattr(required, "value") else int(required)
            )
            if (interaction.user.guild_permissions.value & req_bits) != req_bits:
                return False

    # 2) NSFW
    if getattr(cmd, "nsfw", False):
        ch = interaction.channel
        if not (hasattr(ch, "is_nsfw") and ch.is_nsfw()):
            return False

    # 3) Custom checks (@app_commands.checks.*)
    for check in getattr(cmd, "checks", ()):
        try:
            res = check(interaction)
            if inspect.isawaitable(res):
                await res
        except app_commands.CommandOnCooldown:
            # Still show the command; user just can't use it right now
            pass
        except app_commands.CheckFailure:
            return False
        except Exception:
            # If a check explodes, err on the side of hiding it
            return False

    return True


class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help", description="Shows a list of commands you can use here."
    )
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            categorized: dict[str, list[str]] = {}

            async def add_entry(category: str, text: str):
                categorized.setdefault(category, []).append(text)

            for command in self.bot.tree.get_commands():
                # Handle groups by filtering each subcommand
                if isinstance(command, app_commands.Group):
                    # First-level subcommands
                    visible = []
                    for sub in command.commands:
                        if await user_can_run(sub, interaction):
                            cat = (
                                sub.binding.__class__.__name__.replace("Cog", "")
                                if getattr(sub, "binding", None)
                                else "General"
                            )
                            visible.append(
                                (
                                    cat,
                                    f"`/{command.name} {sub.name}` - {sub.description or '…' }",
                                )
                            )
                    # Optionally handle nested groups (group -> group -> command)
                    for sub in command.commands:
                        if isinstance(sub, app_commands.Group):
                            for subsub in sub.commands:
                                if await user_can_run(subsub, interaction):
                                    cat = (
                                        subsub.binding.__class__.__name__.replace(
                                            "Cog", ""
                                        )
                                        if getattr(subsub, "binding", None)
                                        else "General"
                                    )
                                    visible.append(
                                        (
                                            cat,
                                            f"`/{command.name} {sub.name} {subsub.name}` - {subsub.description or '…'}",
                                        )
                                    )
                    for cat, line in visible:
                        await add_entry(cat, line)
                else:
                    # Regular command
                    if await user_can_run(command, interaction):
                        cat = (
                            command.binding.__class__.__name__.replace("Cog", "")
                            if getattr(command, "binding", None)
                            else "General"
                        )
                        await add_entry(
                            cat, f"`/{command.name}` - {command.description or '…'}"
                        )

            if not categorized:
                return await interaction.followup.send(
                    "No commands available to you here.", ephemeral=True
                )

            # Build paginated embeds
            embeds = []
            for category, lines in sorted(categorized.items()):
                embed = discord.Embed(
                    title=f"{category} Commands",
                    description="\n".join(lines),
                    color=discord.Color.blurple(),
                )
                embeds.append(embed)

            for i, e in enumerate(embeds, start=1):
                e.set_footer(text=f"Page {i}/{len(embeds)}")

            view = HelpView(embeds)
            view.update_buttons()
            msg = await interaction.followup.send(
                embed=embeds[0], view=view, ephemeral=True
            )
            view.message = msg

        except Exception:
            log.exception("Error in /help")
            await interaction.followup.send(
                "An unexpected error occurred while showing help.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
