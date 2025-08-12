# config.py

import os
from pathlib import Path
from dotenv import load_dotenv
from utility.schedule_utils import PingSchedule

load_dotenv()

# === Core Bot Configuration ===


# --- Environment ---
def get_env_int(key: str) -> int | None:
    """Safely loads an integer from environment variables."""
    value = os.getenv(key)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        print(f"⚠️ Warning: Environment variable '{key}' is not a valid integer.")
        return None


environment = os.getenv("ENVIRONMENT", "prod").lower()  # defualt to prod if unset

if environment == "dev":
    print("⚙️ Running in Development mode.")
    TOKEN = os.getenv("TEST_TOKEN")
    guild_id_str = os.getenv("TEST_GUILD_ID")

    DEFAULT_WELCOME_CHANNEL_ID = get_env_int("TEST_DEFAULT_WELCOME_CHANNEL_ID")
    DEFAULT_LEVELUP_CHANNEL_ID = get_env_int("TEST_DEFAULT_LEVELUP_CHANNEL_ID")
    BUG_REPORT_CHANNEL_ID = get_env_int("TEST_BUG_REPORT_CHANNEL_ID")

else:
    print("🚀 Running in Production mode.")
    TOKEN = os.getenv("TOKEN")
    guild_id_str = os.getenv("GUILD_ID")

    DEFAULT_WELCOME_CHANNEL_ID = get_env_int("DEFAULT_WELCOME_CHANNEL_ID")
    DEFAULT_LEVELUP_CHANNEL_ID = get_env_int("DEFAULT_LEVELUP_CHANNEL_ID")
    BUG_REPORT_CHANNEL_ID = get_env_int("BUG_REPORT_CHANNEL_ID")

GUILD_ID = None
try:
    if guild_id_str is not None:
        GUILD_ID = int(guild_id_str)
except (ValueError, TypeError):
    print(f"❌ ERROR: The Guild ID ('{guild_id_str}') is not a valid integer.")

if not TOKEN:
    print("❌ ERROR: The bot token is missing. Check your .env file.")

HERE = Path(__file__).parent
ROOT_DIR = HERE.parent

# === Logging ===
DEFAULT_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"
# === Fonts ===
REGULAR_FONT_PATH = ROOT_DIR / "fonts" / "Roboto" / "static" / "Roboto-Regular.ttf"
BOLD_FONT_PATH = ROOT_DIR / "fonts" / "Roboto" / "static" / "Roboto-Bold.ttf"
ITALIC_FONT_PATH = ROOT_DIR / "fonts" / "Roboto" / "static" / "Roboto-Italic.ttf"
BOLD_ITALIC_FONT_PATH = (
    ROOT_DIR / "fonts" / "Roboto" / "static" / "Roboto-BoldItalic.ttf"
)

if not REGULAR_FONT_PATH.exists():
    raise FileNotFoundError(f"Could not find the font file at {REGULAR_FONT_PATH}")

# --- Asset Paths ---
RANK_CARD_BACKGROUND_PATH = ROOT_DIR / "assets" / "image.png"
LEVELUP_BANNER_PATH = ROOT_DIR / "assets" / "rankup.jpg"
TEMPLATE_PATH = LEVELUP_BANNER_PATH

# === Channel IDs ===
excluded_channels_str = os.getenv("EXCLUDED_CHANNELS", "")
EXCLUDED_CHANNELS = [
    int(channel_id)
    for channel_id in excluded_channels_str.split(",")
    if channel_id.strip()
]

REPORT_GUILD_ID = get_env_int("REPORT_GUILD_ID")

print(f"Excluded channels loaded: {EXCLUDED_CHANNELS}")
WELCOME_IMAGE_BOUNDARY = (300, 380, 1620, 860)

# === Ping & Scheduling ===
PING_SCHEDULES: tuple[PingSchedule, ...] = (
    PingSchedule(
        1388695009712279762, 1396172087764455604, 14, 0, [1, 3, 5], "💎 EU Gem Realm 💎"
    ),
    PingSchedule(
        1388693691421560964, 1396172087764455604, 20, 0, [1, 3, 5], "💎 NA Gem Realm 💎"
    ),
    PingSchedule(
        1396167212766724176, 1396172087764455604, 14, 0, [6], "🔆 NA Guild Tourny 🔆"
    ),
    PingSchedule(
        1396167295461621911, 1396172087764455604, 8, 0, [6], "🔅 EU Guild Tourny 🔅"
    ),
    PingSchedule(
        1396167320052961390, 1396172087764455604, 13, 0, [2, 6], "💵 NA CoP 💵"
    ),
    PingSchedule(
        1396167370338205898, 1396172087764455604, 7, 0, [2, 6], "💶 EU CoP 💶"
    ),
    PingSchedule(
        1219683840306712707,
        1235827891091017739,
        13,
        0,
        [0, 2, 4],
        (
            "\n### Attack mirror number for:"
            "\n3<:star:1394825053111062609> and hold for cleanup or sweep."
            "\n### Or attack them for:"
            "\n1<:star:1394825053111062609> and 2<:star:1394825053111062609>"
            "\n*Example: If you're #5 on the guild side, attack the enemy #5.*",
        ),
        18,
        0,
    ),
    PingSchedule(
        1219683840306712707,
        1235827891091017739,
        20,
        0,
        [0, 2, 4],
        ("Clean up any open bases or sweep."),
        22,
        0,
    ),
    PingSchedule(
        1381417187071230022,
        1381394614233202751,
        13,
        0,
        [0, 2, 4],
        (
            "\n### Unless told otherwise: "
            "\n### Attack one enemy for:"
            "\n3<:star:1394825053111062609> and hold for cleanup or sweep."
            "\n### Or attack them for:"
            "\n1<:star:1394825053111062609> and 2<:star:1394825053111062609>",
        ),
        18,
        0,
    ),
    PingSchedule(
        1381417187071230022,
        1381394614233202751,
        20,
        0,
        [0, 2, 4],
        ("Clean up any open bases or sweep."),
        22,
        0,
    ),
    PingSchedule(
        1308267677680140348,
        1308267362868531311,
        13,
        0,
        [0, 2, 4],
        (
            "\n### Unless told otherwise: "
            "\n### Attack one enemy for:\n3<:star:1394825053111062609> "
            "and hold for cleanup or sweep."
            "\n### Or attack them for:\n1<:star:1394825053111062609> "
            "and 2<:star:1394825053111062609>"
        ),
        18,
        0,
    ),
    PingSchedule(
        1308267677680140348,
        1308267362868531311,
        20,
        0,
        [0, 2, 4],
        ("Clean up any open bases or sweep."),
        22,
        0,
    ),
)

# === Giveaway Configuration ===
ROLE_WEIGHTS = {
    1398825773632196799: 3,  # VIP role
    1397730112744587366: 3,  # VIP role
    1397730097917857895: 3,  # VIP role
    1397730061100257310: 2,  # Premium role
    1397730019660398662: 2,  # Premium role
}
DEFAULT_WEIGHT = 1
GIVEAWAY_CHECK_INTERVAL = 20
# === Leveling System Configuration ===
DB_PATH = os.path.join(HERE, "leveling.db")
DEFAULT_XP_RANGE = (5, 15)
DEFAULT_XP_COOLDOWN = 1
DAILY_XP_ROLE = 1398825773632196799
DAILY_ANNOUNCE_CHANNEL = {956957091803852830: 1402095288939974718}
ROLE_REWARDS = {
    1: 1397729527265886238,
    10: 1397729969530077184,
    25: 1397729992628109443,
    35: 1397730019660398662,
    50: 1397730061100257310,
    75: 1397730097917857895,
    100: 1397730112744587366,
}

# === Rank Card Configuration ===
FONT_SIZE_BIG = 40
FONT_SIZE_SMALL = 24
CARD_BG_COLOR = (54, 57, 63)
CARD_WIDTH = 1600
CARD_HEIGHT = 400
TEXT_GAP = 25
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
MAX_PIXELS = 80_000_000  # ~8k x 10k

# === Role Update Alerts ===
ROLE_ALERTS = [
    (1385466780436271214, 1231665533477453835, "🎉 {member} is now a Monarch! 🎉"),
    (1386037122242318406, 1231665533477453835, "🎉 {member} is now a Commander! 🎉"),
    (1386036619806638212, 1231665533477453835, "🎉 {member} is now a Knight! 🎉"),
]
