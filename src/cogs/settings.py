from typing import Optional

#
import discord
from discord.ext import commands
from discord import app_commands

#
import config
from data import database
from helpers.level_utils import level_from_xp, build_xp_status
from views.purge_confirmation_view import PurgeConfirmationView


class SettingsCog(commands.Cog, name="Settings"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Command Group for Channel Settings ---
    channel_group = app_commands.Group(
        name="config-channels", description="Configure channels for bot announcements."
    )

    @channel_group.command(
        name="set-welcome", description="[Admin] Sets the channel for welcome messages."
    )
    @app_commands.describe(channel="The text channel to send welcome messages to.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_welcome_channel_cmd(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        guild_id = interaction.guild.id
        database.set_welcome_channel(guild_id, channel.id)

        events_cog = self.bot.get_cog("Events")
        if events_cog:
            events_cog.welcome_channels[guild_id] = channel.id

        await interaction.response.send(
            f"✅ Welcome messages will now be sent to {channel.mention}.",
            ephemeral=True,
        )

    @channel_group.command(
        name="set-levelup",
        description="[Admin] Sets the channel for level-up announcements.",
    )
    @app_commands.describe(channel="The text channel to send level-up messages to.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_levelup_channel_cmd(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        guild_id = interaction.guild.id

        database.set_levelup_channel(guild_id, channel.id)

        leveling_cog = self.bot.get_cog("Leveling")
        if leveling_cog:
            leveling_cog.guild_levelup_channels[guild_id] = channel.id

        await interaction.response.send(
            f"✅ Level-up announcements will now be sent to {channel.mention}.",
            ephemeral=True,
        )

    @channel_group.command(
        name="purge-messages",
        description="[Admin] Purge messages from a selected channel on-demand.",
    )
    @app_commands.describe(
        channel="The text channel to purge.",
        limit="Number of messages to delete. Leave blank to delete all.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_messages(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: Optional[int] = None,
    ):
        try:
            if limit:
                purge_amount_text = f"the last **{limit}** messages"
            else:
                purge_amount_text = "**all** messages"

            view = PurgeConfirmationView(channel, limit)

            await interaction.response.send(
                (
                    f"Are you sure you want to permanently delete {purge_amount_text} "
                    f"in {channel.mention}?"
                ),
                view=view,
                ephemeral=True,
            )

            view.message = await interaction.original_response()

        except Exception as e:
            print(f"Error in /purge-messages command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )

    # --- Command Group for Leveling Mechanics ---
    leveling_group = app_commands.Group(
        name="config-leveling", description="Configure the leveling system mechanics."
    )

    @leveling_group.command(
        name="cooldown", description="[Admin] Set the XP gain cooldown."
    )
    @app_commands.describe(seconds="The cooldown time in seconds.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_cooldown(self, interaction: discord.Interaction, seconds: int):
        await interaction.response.defer(ephemeral=True)
        try:
            if seconds < 0:
                await interaction.followup.send(
                    "Cooldown cannot be negative.", ephemeral=True
                )
                return

            guild_id = interaction.guild.id
            database.set_xp_cooldown(guild_id, seconds)
            leveling_cog = self.bot.get_cog("Leveling")
            if leveling_cog:
                leveling_cog.guild_cooldowns[guild_id] = seconds

            await interaction.followup.send(
                f"✅ XP cooldown set to **{seconds}** seconds.", ephemeral=True
            )
        except Exception as e:
            print(f"Error in /set-cooldown command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )

    @leveling_group.command(
        name="xprange", description="[Admin] Set the min/max XP gain per message."
    )
    @app_commands.describe(min_xp="Minimum XP.", max_xp="Maximum XP.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_xprange(
        self, interaction: discord.Interaction, min_xp: int, max_xp: int
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if min_xp < 0 or max_xp <= min_xp:
                await interaction.followup.send(
                    "Invalid XP range. Ensure min < max and both are non-negative.",
                    ephemeral=True,
                )
                return

            guild_id = interaction.guild.id
            database.update_xp_range(guild_id, min_xp, max_xp)
            leveling_cog = self.bot.get_cog("Leveling")
            if leveling_cog:
                leveling_cog.guild_xp_ranges[guild_id] = (min_xp, max_xp)

            await interaction.followup.send(
                f"XP range set to {min_xp}-{max_xp}.", ephemeral=True
            )
        except Exception as e:
            print(f"Error in /xprange command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )

    @leveling_group.command(
        name="removeallxp", description="[Admin] Remove all XP from a member."
    )
    @app_commands.describe(member="The member to remove XP from.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def removeallxp(
        self, interaction: discord.Interaction, member: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            user_data = database.get_user(member.id, interaction.guild.id)
            old_total_xp, old_level = user_data if user_data else (0, 0)

            if old_total_xp == 0:
                await interaction.followup.send(
                    f"{member.mention} has no XP to remove.", ephemeral=True
                )
                return

            database.set_user_xp_and_level(member.id, interaction.guild.id, 0, 0)
            new_status = build_xp_status(0)

            removed = []
            for threshold, role_id in config.ROLE_REWARDS.items():
                if old_level >= threshold > new_status.level:
                    role = interaction.guild.get_role(role_id)
                    if role and role in member.roles:
                        await member.remove_roles(
                            role, reason="XP dropped below threshold"
                        )
                        removed.append(role.name)

            msg = (
                f"❌ Removed **{old_total_xp} XP** from {member.mention}.\n"
                f"• Level: {old_level} → **{new_status.level}**\n"
                f"• Total XP: **{new_status.total_xp}**\n"
            )
            if removed:
                msg += "⚠️ Roles removed: " + ", ".join(removed)

            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            print(f"Error in /removeallxp command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )

    @leveling_group.command(name="addxp", description="[Admin] Add XP to a member.")
    @app_commands.describe(
        member="The member to grant XP to.", amount="The amount of XP to add."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def addxp(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            user_data = database.get_user(member.id, interaction.guild.id)
            current_xp = user_data[0] if user_data else 0
            old_level = level_from_xp(current_xp)

            new_total_xp = current_xp + amount
            new_status = build_xp_status(new_total_xp)
            database.set_user_xp_and_level(
                member.id, interaction.guild.id, new_total_xp, new_status.level
            )

            awarded = []
            for threshold, role_id in config.ROLE_REWARDS.items():
                if old_level < threshold <= new_status.level:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        await member.add_roles(role, reason="Reached level threshold")
                        awarded.append(role.name)

            msg = (
                f"✅ Added **{amount} XP** to {member.mention}.\n"
                f"• Level: **{old_level} → {new_status.level}**\n"
                f"• Total XP: **{new_status.total_xp}**\n"
            )
            if awarded:
                msg += "🎉 Roles awarded: " + ", ".join(awarded)
            await interaction.followup.send(msg)
        except Exception as e:
            print(f"Error in /addxp command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )

    @leveling_group.command(
        name="removexp", description="[Admin] Remove XP from a member."
    )
    @app_commands.describe(
        member="The member to remove XP from.", amount="The amount of XP to remove."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def removexp(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            user_data = database.get_user(member.id, interaction.guild.id)
            current_xp = user_data[0] if user_data else 0
            old_level = level_from_xp(current_xp)

            new_total_xp = max(0, current_xp - amount)
            new_status = build_xp_status(new_total_xp)
            database.set_user_xp_and_level(
                member.id, interaction.guild.id, new_total_xp, new_status.level
            )

            removed = []
            for threshold, role_id in config.ROLE_REWARDS.items():
                if old_level >= threshold > new_status.level:
                    role = interaction.guild.get_role(role_id)
                    if role and role in member.roles:
                        await member.remove_roles(
                            role, reason="XP dropped below threshold"
                        )
                        removed.append(role.name)

            msg = (
                f"❌ Removed **{amount} XP** from {member.mention}.\n"
                f"• Level: **{old_level} → {new_status.level}**\n"
                f"• Total XP: **{new_status.total_xp}**\n"
            )
            if removed:
                msg += "⚠️ Roles removed: " + ", ".join(removed)

            await interaction.followup.send(msg)

        except Exception as e:
            print(f"Error in /removexp command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred. Please check the logs.",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))
