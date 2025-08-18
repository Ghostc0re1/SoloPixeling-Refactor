# bot.py

import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands

import config

from data.database import authenticate_bot
from helpers.logging_helper import get_logger, setup_logging
from utility.logging_utils import CogLogging

# --- Set up basic logging ---
setup_logging(
    CogLogging.from_env(),
    http_log_path="logs/http.log",
    http_level="INFO",
    http_propagate=False,
)
log = get_logger("bootstrap")

HERE = os.path.dirname(os.path.abspath(__file__))
COGS_DIR = os.path.join(HERE, "cogs")

# Define intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    owner_ids={264085720820482048, 194357840176087049},
)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """A global error handler for all slash commands."""

    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "🚫 You lack the required permissions to use this command.", ephemeral=True
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ This command is on cooldown. Please try again in {error.retry_after:.2f} seconds.",
            ephemeral=True,
        )
    else:
        # Generic fallback for other errors
        log.error("Unhandled command error: %s", error)
        if interaction.response.is_done():
            await interaction.followup.send(
                "An unexpected error occurred. Please try again later.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.", ephemeral=True
            )


logger = get_logger("bot")
coglog = get_logger("bot.cogs")


@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Bot is ready and online!")
    log.info("%s", "-" * 20)
    ok = await authenticate_bot()
    if ok:
        log.info("✅ Bot authenticated with Supabase")
    else:
        log.error("❌ Bot failed to authenticate with Supabase")


async def load_cogs():
    """Finds and loads all cogs in the 'cogs' directory."""
    for filename in os.listdir(COGS_DIR):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        ext = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(ext)
            coglog.info("Loaded cog: %s", filename)
        except Exception:
            coglog.exception("Failed to load cog %s", filename)


async def main():
    """Main function to load cogs and run the bot."""
    async with bot:
        logger.info("Database initialized.")

        await load_cogs()
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
