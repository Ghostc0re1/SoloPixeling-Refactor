# bot.py

import os
import logging
import asyncio
import discord
from discord.ext import commands

import config

# --- Set up basic logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

HERE = os.path.dirname(os.path.abspath(__file__))
COGS_DIR = os.path.join(HERE, "cogs")

# Define intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    logging.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logging.info("%s", "-" * 20)

    logging.info(
        "Commands found in tree: %s",
        [command.name for command in bot.tree.get_commands()],
    )

    try:
        guild = discord.Object(id=config.GUILD_ID)
        bot.tree.copy_global_to(guild=guild)

        synced = await bot.tree.sync(guild=guild)
        allsynced = await bot.tree.sync()
        logging.info("Synced %s command(s) to %s", len(synced), guild)
        logging.info("Synced %s command(s) globally", len(allsynced))
    except Exception as e:
        logging.error("Failed to sync commands: %s", e)


async def load_cogs():
    """Finds and loads all cogs in the 'cogs' directory."""
    for filename in os.listdir(COGS_DIR):
        if filename.endswith(".py"):
            # --- Added error handling for loading ---
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                logging.info("Loaded cog: %s", filename)
            except Exception as e:
                logging.error("Failed to load cog %s: %s", filename, e)


async def main():
    """Main function to load cogs and run the bot."""
    async with bot:
        # --- Initialize database before bot starts ---
        logging.info("Database initialized.")

        await load_cogs()
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
