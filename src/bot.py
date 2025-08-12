# bot.py

import os
import asyncio
import discord
from discord.ext import commands

import config

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

bot = commands.Bot(command_prefix="!", intents=intents)
logger = get_logger("bot")
coglog = get_logger("bot.cogs")


@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("%s", "-" * 20)

    try:
        cmd_names = [cmd.name for cmd in bot.tree.get_commands()]
        logger.info("Commands in tree: %s", cmd_names)
    except Exception:
        logger.exception("Failed to list commands in tree")

    try:
        guild = discord.Object(id=config.GUILD_ID)
        bot.tree.copy_global_to(guild=guild)

        synced = await bot.tree.sync()
        logger.info("Synced %s command(s) globally", len(synced))
    except Exception as e:
        logger.exception("Failed to sync commands: %s", e)


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
