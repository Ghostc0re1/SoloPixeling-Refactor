import discord
from discord.ext import commands
import config
from data import database
from helpers.logging_helper import add_throttle, get_logger
from utility import image_utils

log = get_logger("events")
join_log = get_logger("events.join")
add_throttle(join_log, 60)


class Events(commands.Cog, name="Events"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.welcome_channels = {}

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            all_settings = await database.get_all_channel_settings()
            for guild_id, settings in all_settings.items():
                if settings and settings.get("welcome"):
                    self.welcome_channels[guild_id] = settings["welcome"]
                log.info(
                    "Loaded welcome channel settings for %d guilds.",
                    len(self.welcome_channels),
                )
        except Exception:
            log.exception("Failed to load welcome channel settings")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        if member.guild.id != config.GUILD_ID:
            return

        # throttled heatbeat for joins
        join_log.debug("Join: guild=%s user=%s", member.guild.id, member.id)

        channel_id = self.welcome_channels.get(
            member.guild.id, config.DEFAULT_WELCOME_CHANNEL_ID
        )
        if not channel_id:
            log.warning("No welcome channel configured for guild %s.", member.guild.id)
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            log.error(
                "Could not find welcome channel with ID %s in guild %s.",
                channel_id,
                member.guild.id,
            )
            return

        try:
            log.info("Generating welcome image for %s...", member.display_name)

            lines = [
                [
                    ("Congratulations ", config.REGULAR_FONT_PATH),
                    (f"{member.display_name} ", config.BOLD_ITALIC_FONT_PATH),
                    ("on becoming a ", config.REGULAR_FONT_PATH),
                    ("Player.", config.BOLD_ITALIC_FONT_PATH),
                ],
            ]

            buf = image_utils.make_multiline_glow(
                config.TEMPLATE_PATH,
                lines,
                max_font_size=50,
                glow_radii=(20, 40, 80),
                v_pad=8,
            )

            # Ensure buffer is at the beginning
            buf.seek(0)

            await channel.send(
                content=member.mention,
                file=discord.File(fp=buf, filename="welcome.png"),
            )
            log.info("Sent welcome image for %s", member.display_name)

        except Exception:
            log.exception(
                "Failed to generate welcome image for %s", member.display_name
            )
            try:
                await channel.send(f"Welcome to the server, {member.mention}")
            except discord.errors.Forbidden:
                log.error(
                    "Failed to send fallback welcome message in %s due to missing permissions.",
                    channel.name,
                )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return

        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}

        # Check if any new roles match our configured role alerts
        newly_added_roles = after_ids - before_ids
        if not newly_added_roles:
            return

        for role_id, ch_id, msg in config.ROLE_ALERTS:
            if role_id in newly_added_roles:
                channel = after.guild.get_channel(ch_id)
                if channel:
                    try:
                        await channel.send(msg.format(member=after.mention))
                    except discord.errors.Forbidden:
                        log.error(
                            "Could not send role alert to #%s due to missing permissions.",
                            channel.name,
                        )
                else:
                    log.warning("Could not find channel %s for role alert.", ch_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
