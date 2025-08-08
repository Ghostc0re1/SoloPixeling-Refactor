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

```
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

3. **Set up a `.env` file** (example values):
   ```env
   ENVIRONMENT=prod                 # or "dev"
   TOKEN=your_bot_token             # use TEST_TOKEN in dev mode
   GUILD_ID=123456789012345678
   DEFAULT_WELCOME_CHANNEL_ID=123456789012345678
   DEFAULT_LEVELUP_CHANNEL_ID=123456789012345678
   BUG_REPORT_CHANNEL_ID=123456789012345678
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

## Testing & Linting

```
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
