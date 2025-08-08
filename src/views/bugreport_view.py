import traceback

#
import discord
from discord import ui, TextStyle

#
import config


class BugReportModal(ui.Modal, title="Submit a Bug Report"):
    summary = ui.TextInput(
        label="Short Summary of the Bug",
        placeholder="e.g., Rank command shows negative XP",
        style=TextStyle.short,
        required=True,
        max_length=100,
    )

    steps = ui.TextInput(
        label="Steps to Reproduce",
        placeholder="Please be as detailed as possible."
        "\n1. Run the /rank command..."
        "\n2. Observe the XP value...",
        style=TextStyle.paragraph,
        required=True,
        max_length=1024,
    )

    expected = ui.TextInput(
        label="Expected Behavior (Optional)",
        placeholder="The rank card should show my current XP progress correctly.",
        style=TextStyle.paragraph,
        required=False,
        max_length=1024,
    )

    async def on_submit(
        self, interaction: discord.Interaction
    ):  # pylint: disable=arguments-differ
        target_guild = interaction.client.get_guild(config.REPORT_GUILD_ID)
        if not target_guild:
            return await interaction.response.send_message(
                "❌ Bot isn’t in the report server!", ephemeral=True
            )

        report_channel = target_guild.get_channel(config.BUG_REPORT_CHANNEL_ID)
        if not report_channel:
            return await interaction.response.send_message(
                "❌ Could not find the report channel in target server!", ephemeral=True
            )

        embed = discord.Embed(
            title=f"New Bug Report: {self.summary.value}",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=interaction.user, icon_url=interaction.user.display_avatar.url
        )
        embed.add_field(
            name="Steps to Reproduce",
            value=f"```\n{self.steps.value}\n```",
            inline=False,
        )

        if self.expected.value:
            embed.add_field(
                name="Expected Behavior",
                value=f"```\n{self.expected.value}\n```",
                inline=False,
            )

        embed.set_footer(
            text=f"Submitted from: {interaction.guild.name} | User ID: {interaction.user.id}"
        )

        await report_channel.send(embed=embed)

        await interaction.response.send_message(
            "Thank you! Your bug report has been submitted successfully.",
            ephemeral=True,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ):  # pylint: disable=arguments-differ
        traceback.print_exc()
        await interaction.response.send_message(
            "Oops! Something went wrong while submitting your report.", ephemeral=True
        )
