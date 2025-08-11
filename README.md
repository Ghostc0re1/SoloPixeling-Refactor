# SoloPixelingBot

SoloPixelingBot is a modular Discord bot designed for the Solo Pixeling community.
It automates server tasks such as welcome messages, giveaways, XP-based leveling, scheduled role pings, and bug reporting—all built on top of [discord.py](https://discordpy.readthedocs.io) with a Supabase backend.

---

## Features

- **Welcome & Role Alerts**
  - Greets new members with custom image banners.
  - Announces role promotions when configured thresholds are reached.

- **XP & Leveling System**
  - Grants XP for messages with cooldowns, configurable ranges, and role rewards.
  - Slash commands: `/rank`, `/leaderboard`.
  - Daily XP leaderboard with automatic role assignment for top earners.
  - Image-based rank cards and level-up banners.

- **Giveaway Management**
  - `/giveaway` command to start weighted giveaways.
  - Interactive entry buttons and automatic winner selection.

- **Scheduled Pings**
  - Time‑zone–aware scheduler to ping roles or purge channels on specific days/times.
  - `/testschedule` command to validate or trigger schedules.

- **Server Configuration**
  - `/config-channels …` group to set welcome or level-up channels and purge messages.
  - `/config-leveling …` group to adjust cooldowns, XP ranges, or manually modify XP.

- **Utility Commands**
  - `/bugreport` opens a modal to send reports to a designated server.

- **Help System**
  - `/help` shows categorized, paginated command listings.

---

## Project Structure

```text
src/
├── bot.py               # Application entry point
├── cogs/                # Discord command modules
│   ├── events.py
│   ├── giveaway.py
│   ├── help.py
│   ├── leveling.py
│   ├── scheduling.py
│   ├── settings.py
│   └── utility.py
├── config.py            # Environment & runtime configuration
├── data/
│   └── database.py      # Supabase interface
├── helpers/             # Support utilities (images, XP math, scheduling, …)
└── views/               # Discord UI components (buttons, modals, views)

assets/                  # Rank card backgrounds, level-up banners
fonts/                   # Bundled Roboto font family
tests/                   # Unit tests (pytest)
```

---

## How It Works

- Uses [discord.py](https://discordpy.readthedocs.io) with a cog-based architecture. Each module under `src/cogs/` contains a related set of slash commands and event listeners.
- `src/bot.py` discovers and loads all cogs on startup, then syncs the slash commands to the target guild and globally.
- `src/config.py` reads environment variables to decide whether the bot runs in development or production mode and to pull in guild/channel IDs and tokens.
- Persistent data such as XP, giveaways, and reports is stored in Supabase through the helper classes under `src/data/`.

---

## Requirements

- Python **3.10+**
- Discord bot token and guild-specific channel IDs
- Supabase project (URL & API key)
- Dependencies listed in `requirements.txt`  
  (development extras in `requirements-dev.txt`)

---

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourname/SoloPixeling-Refactor.git
   cd SoloPixeling-Refactor
   ```

2. **Create a virtual environment & install deps**

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt  # or requirements-dev.txt for development
   ```

3. **Set up a `.env` file**

   The bot reads configuration from environment variables. Create a `.env` file in the project root with values like the following:

   **Development mode** (`ENVIRONMENT=dev`)

   ```env
   ENVIRONMENT=dev
   TEST_TOKEN=your_dev_bot_token
   TEST_GUILD_ID=123456789012345678
   TEST_DEFAULT_WELCOME_CHANNEL_ID=123456789012345678
   TEST_DEFAULT_LEVELUP_CHANNEL_ID=123456789012345678
   TEST_BUG_REPORT_CHANNEL_ID=123456789012345678
   ```

   **Production mode** (`ENVIRONMENT=prod` or unset)

   ```env
   ENVIRONMENT=prod
   TOKEN=your_prod_bot_token
   GUILD_ID=123456789012345678
   DEFAULT_WELCOME_CHANNEL_ID=123456789012345678
   DEFAULT_LEVELUP_CHANNEL_ID=123456789012345678
   BUG_REPORT_CHANNEL_ID=123456789012345678
   ```

   **Common settings**

   ```env
   EXCLUDED_CHANNELS=111,222,333
   REPORT_GUILD_ID=987654321098765432
   SUPABASE_URL=https://project.supabase.co
   SUPABASE_KEY=your_supabase_service_key
   ```

---

## Running the Bot

```bash
python -m src.bot
```

The bot auto-loads all cogs on startup, synchronizes slash commands, and begins processing events.

---

## Development vs Production Modes

`config.py` checks the `ENVIRONMENT` variable to decide which credentials to load:

- `ENVIRONMENT=dev` &rarr; uses the `TEST_` tokens and channel IDs and prints "⚙️ Running in Development mode." on startup.
- `ENVIRONMENT=prod` or unset &rarr; uses the production variables and prints "🚀 Running in Production mode.".

Ensure the corresponding token and IDs are present in the `.env` file before starting the bot.

---

## Testing & Linting

```text
./lint.sh          # Run pylint over src/
./run_checks.sh    # Lint + run pytest
pytest             # Run tests only
```

---

## Contributing

1. Fork the repository and create a feature branch.
2. Ensure all linting/tests pass before submitting a PR.
3. Submit the pull request with a clear description of changes.

---

## License

Released under the [MIT License](LICENSE).  
© 2025 Taylor Berardelli.
