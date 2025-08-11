# tests/test_leveling.py
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch
import types
import pytest
import discord

from cogs.leveling import Leveling
from helpers.level_utils import XpResult


@pytest.fixture
def bot():
    return MagicMock(spec=discord.Client)


@pytest.fixture
def cog(bot, monkeypatch):
    # tame config defaults
    import config

    monkeypatch.setattr(config, "DEFAULT_XP_RANGE", (5, 5), False)
    monkeypatch.setattr(config, "DEFAULT_XP_COOLDOWN", 10, False)
    monkeypatch.setattr(config, "EXCLUDED_CHANNELS", set(), False)
    monkeypatch.setattr(config, "DEFAULT_LEVELUP_CHANNEL_ID", 1111, False)
    monkeypatch.setattr(config, "ROLE_REWARDS", {3: 2222}, False)
    monkeypatch.setattr(
        config, "REGULAR_FONT_PATH", "fonts/Roboto/static/Roboto-Regular.ttf", False
    )
    monkeypatch.setattr(
        config,
        "BOLD_ITALIC_FONT_PATH",
        "fonts/Roboto/static/Roboto-BoldItalic.ttf",
        False,
    )
    monkeypatch.setattr(config, "LEVELUP_BANNER_PATH", "assets/rankup.jpg", False)
    monkeypatch.setattr(config, "DAILY_XP_ROLE", 3333, False)
    # map guild id -> announce channel id
    monkeypatch.setattr(config, "DAILY_ANNOUNCE_CHANNEL", {1234: 4444}, False)
    return Leveling(bot)


# ---------- _process_xp_gain ----------
@pytest.mark.asyncio
async def test_process_xp_gain_respects_cooldown(cog, monkeypatch):
    msg = MagicMock(spec=discord.Message)
    msg.author.id = 55
    msg.author.bot = False
    msg.guild.id = 777
    msg.channel.id = 999

    cog.guild_cooldowns[msg.guild.id] = 10
    cog._last_xp[(msg.guild.id, msg.author.id)] = 1000.0
    monkeypatch.setattr("time.time", lambda: 1005.0)

    res = await cog._process_xp_gain(msg)  # ← await
    assert res is None


@pytest.mark.asyncio
async def test_process_xp_gain_happy_path_updates_db(cog, monkeypatch):
    msg = MagicMock(spec=discord.Message)
    msg.author.id = 55
    msg.author.bot = False
    msg.guild.id = 777
    msg.channel.id = 999

    cog.guild_cooldowns[msg.guild.id] = 0
    cog.guild_xp_ranges[msg.guild.id] = (5, 5)

    monkeypatch.setattr("time.time", lambda: 1000.0)
    monkeypatch.setattr("random.randint", lambda a, b: 5)

    # ← patch the *same path used by the cog* and use AsyncMock
    monkeypatch.setattr(
        "cogs.leveling.database.get_user", AsyncMock(return_value=(10, 1))
    )
    set_user = AsyncMock()
    inc_daily = AsyncMock()
    monkeypatch.setattr("cogs.leveling.database.set_user_xp_and_level", set_user)
    monkeypatch.setattr("cogs.leveling.database.increment_daily_xp", inc_daily)

    res = await cog._process_xp_gain(msg)  # ← await
    assert res is not None
    set_user.assert_awaited_once()
    inc_daily.assert_awaited_once()


# ---------- on_message ----------


@pytest.mark.asyncio
async def test_on_message_ignores_bots_or_no_guild_or_excluded(cog, monkeypatch):
    import config

    # bot author
    m1 = MagicMock(spec=discord.Message)
    m1.author.bot = True
    m1.guild = MagicMock()
    m1.channel.id = 1

    # no guild
    m2 = MagicMock(spec=discord.Message)
    m2.author.bot = False
    m2.guild = None
    m2.channel.id = 1

    # excluded channel
    m3 = MagicMock(spec=discord.Message)
    m3.author.bot = False
    m3.guild = MagicMock()
    m3.channel.id = 123
    config.EXCLUDED_CHANNELS = {123}

    with patch.object(cog, "_process_xp_gain", return_value=None) as proc, patch.object(
        cog, "_announce_levelup", new_callable=AsyncMock
    ) as announce:
        await cog.on_message(m1)
        await cog.on_message(m2)
        await cog.on_message(m3)

        proc.assert_not_called()
        announce.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_triggers_announce_when_leveled(cog):
    m = MagicMock(spec=discord.Message)
    m.author.bot = False
    m.guild = MagicMock()
    m.channel.id = 1
    with patch.object(
        cog, "_process_xp_gain", return_value=XpResult(True, 3, 2)
    ), patch.object(cog, "_announce_levelup", new_callable=AsyncMock) as announce:
        await cog.on_message(m)
        announce.assert_awaited_once_with(m, 3)


# ---------- _announce_levelup ----------


@pytest.mark.asyncio
async def test_announce_levelup_no_channel_configured(cog):
    msg = MagicMock(spec=discord.Message)
    msg.guild.id = 999
    # channel id falls back to default; simulate missing default => None
    with patch("cogs.leveling.config.DEFAULT_LEVELUP_CHANNEL_ID", None):
        # should just no-op
        await cog._announce_levelup(msg, new_level=3)


@pytest.mark.asyncio
async def test_announce_levelup_no_role_reward(cog):
    import config

    guild = MagicMock(spec=discord.Guild)
    ch = MagicMock(spec=discord.TextChannel)
    ch.send = AsyncMock()

    guild.get_channel.return_value = ch
    msg = MagicMock(spec=discord.Message)
    msg.guild = guild
    msg.author.mention = "@u"
    msg.author.display_name = "u"

    # no role for this level
    with patch.dict("cogs.leveling.config.ROLE_REWARDS", {}, clear=True):
        await cog._announce_levelup(msg, 9)
        ch.send.assert_awaited_once()  # only the "leveled up" text


@pytest.mark.asyncio
async def test_announce_levelup_full_flow(cog):
    import config

    guild = MagicMock(spec=discord.Guild)

    lvl_channel = MagicMock(spec=discord.TextChannel)
    lvl_channel.send = AsyncMock()
    guild.get_channel.return_value = lvl_channel

    role = MagicMock(spec=discord.Role)
    role.name = "Champion"
    guild.get_role.return_value = role

    member = MagicMock(spec=discord.Member)
    member.display_name = "Alice"
    member.mention = "@Alice"
    member.add_roles = AsyncMock()

    msg = MagicMock(spec=discord.Message)
    msg.guild = guild
    msg.author = member

    # image utils returns a BytesIO-like
    with patch("cogs.leveling.image_utils.make_multiline_glow") as glow:
        glow.return_value = MagicMock()

        await cog._announce_levelup(msg, 3)

        # sent the plain text + the banner
        assert lvl_channel.send.await_count == 2
        member.add_roles.assert_awaited_once()


# ---------- /rank ----------


@pytest.fixture
def interaction():
    i = MagicMock(spec=discord.Interaction)
    i.response = MagicMock()
    i.response.defer = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()
    i.user = MagicMock(spec=discord.Member)
    i.user.id = 7
    i.guild = MagicMock(spec=discord.Guild)
    i.guild.id = 42
    return i


async def _call_app_command(fn, cog, *args, **kwargs):
    # app_commands methods become AppCommand objects; call their callback
    return await fn.callback(cog, *args, **kwargs)


@pytest.mark.asyncio
async def test_rank_no_data(monkeypatch):
    from cogs.leveling import Leveling

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = 1
    interaction.user = MagicMock()
    interaction.user.id = 7
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    monkeypatch.setattr("cogs.leveling.database.get_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "cogs.leveling.database.get_user_rank", AsyncMock(return_value=None)
    )

    cog = Leveling(MagicMock())
    await cog.rank.callback(cog, interaction)  # ← use .callback

    interaction.followup.send.assert_awaited()
    assert "no XP yet" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_rank_happy_path(monkeypatch):
    from cogs.leveling import Leveling

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = 1
    interaction.user = MagicMock()
    interaction.user.id = 7
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    monkeypatch.setattr(
        "cogs.leveling.database.get_user", AsyncMock(return_value=(125, 3))
    )
    monkeypatch.setattr(
        "cogs.leveling.database.get_user_rank", AsyncMock(return_value=2)
    )
    monkeypatch.setattr(
        "cogs.leveling.database.get_user_profile",
        AsyncMock(
            return_value={
                "primary_color": "#ffffff",
                "accent_color": "#ffaa00",
                "banner_path": None,
            }
        ),
    )
    monkeypatch.setattr(
        "cogs.leveling.fetch_banner_bytes", AsyncMock(return_value=None)
    )
    fake = discord.File(fp=BytesIO(b"img"), filename="rank.png")
    monkeypatch.setattr(
        "cogs.leveling.image_utils.generate_rank_card", AsyncMock(return_value=fake)
    )

    cog = Leveling(MagicMock())
    await cog.rank.callback(cog, interaction)  # ← use .callback

    interaction.followup.send.assert_awaited()


# ---------- /leaderboard ----------


@pytest.mark.asyncio
async def test_leaderboard_empty(monkeypatch):
    from cogs.leveling import Leveling

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = 1
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    monkeypatch.setattr(
        "cogs.leveling.database.get_leaderboard", AsyncMock(return_value=[])
    )

    cog = Leveling(MagicMock())
    await cog.leaderboard.callback(cog, interaction)  # ← use .callback

    interaction.followup.send.assert_awaited()
    assert "No leaderboard data yet" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_leaderboard_happy_path(monkeypatch):
    from cogs.leveling import Leveling

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = 1
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    rows = [(111, 5, 1234), (222, 4, 900)]
    monkeypatch.setattr(
        "cogs.leveling.database.get_leaderboard", AsyncMock(return_value=rows)
    )

    class DummyView:
        def __init__(self, *_):
            pass

        def update_buttons(self):
            pass

        async def generate_embed(self):
            return discord.Embed(title="LB")

    with patch("cogs.leveling.LeaderboardView", DummyView):
        cog = Leveling(MagicMock())
        await cog.leaderboard.callback(cog, interaction)  # ← use .callback

    interaction.followup.send.assert_awaited()


# ---------- daily_award_task ----------


@pytest.mark.asyncio
async def test_daily_award_task_assigns_and_announces(cog):
    # bot with one guild
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1234
    # role with existing members to remove
    role = MagicMock


@pytest.fixture(autouse=True)
def disable_daily_loop(monkeypatch):
    from cogs.leveling import Leveling

    orig_init = Leveling.__init__

    def wrapped(self, bot):
        orig_init(self, bot)
        self.daily_award_task.start = lambda: None
        self.daily_award_task.cancel = lambda: None

    monkeypatch.setattr(Leveling, "__init__", wrapped)
