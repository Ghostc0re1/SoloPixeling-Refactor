import re
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

# -------- Fixtures --------


@pytest.fixture
def bot():
    # Use commands.Bot-ish spec so add_cog/add_view exist if needed
    mock = MagicMock(spec=discord.Client)
    mock.get_channel = MagicMock()
    mock.get_guild = MagicMock()
    return mock


@pytest.fixture
def guild():
    g = MagicMock(spec=discord.Guild)
    g.id = 999
    g.get_member = MagicMock()
    return g


@pytest.fixture
def channel():
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 1234
    ch.send = AsyncMock()
    ch.fetch_message = AsyncMock()
    return ch


@pytest.fixture
def user():
    u = MagicMock(spec=discord.Member)
    u.id = 42
    u.mention = "<@42>"
    u.display_name = "Tester"
    u.roles = []
    return u


@pytest.fixture
def interaction(channel, user):
    i = MagicMock(spec=discord.Interaction)
    i.user = user
    i.channel = channel
    i.response = MagicMock()
    i.response.send_message = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()
    return i


@pytest.fixture
def sent_message(channel):
    m = MagicMock(spec=discord.Message)
    m.id = 777
    m.channel = channel
    m.embeds = []
    m.edit = AsyncMock()
    m.reply = AsyncMock()
    return m


@pytest.fixture
def giveaway_row(channel, guild):
    return {
        "message_id": 777,
        "channel_id": channel.id,
        "guild_id": guild.id,
        "prize": "Fancy Prize",
        "end_time": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "winner_count": 2,
        "is_active": True,
    }


# -------- Helpers --------


async def _run_cmd(cog, interaction, **kwargs):
    return await cog.giveaway_start.callback(
        cog, interaction, kwargs["prize"], kwargs["duration"], kwargs["winners"]
    )


# -------- Tests for command --------


@pytest.mark.asyncio
async def test_giveaway_rejects_invalid_args(bot, interaction):
    from cogs.giveaway import Giveaway

    cog = Giveaway(bot)

    await _run_cmd(cog, interaction, prize="Prize", duration=0, winners=1)
    interaction.response.send_message.assert_awaited()
    msg, kw = interaction.response.send_message.await_args
    assert "greater than zero" in msg[0]
    assert kw["ephemeral"] is True

    interaction.response.send_message.reset_mock()
    await _run_cmd(cog, interaction, prize="Prize", duration=5, winners=0)
    interaction.response.send_message.assert_awaited()
    msg, kw = interaction.response.send_message.await_args
    assert "greater than zero" in msg[0]
    assert kw["ephemeral"] is True


@pytest.mark.asyncio
async def test_giveaway_happy_path(bot, interaction, channel, sent_message):
    from cogs.giveaway import Giveaway

    with patch("cogs.giveaway.GiveawayView") as MockView, patch(
        "cogs.giveaway.db.create_giveaway", new=AsyncMock()
    ) as mock_create:
        MockView.return_value = MagicMock()
        channel.send.return_value = sent_message

        cog = Giveaway(bot)
        start = datetime.now(timezone.utc)
        await _run_cmd(cog, interaction, prize="Fancy Prize", duration=3, winners=2)

        interaction.response.send_message.assert_awaited()
        channel.send.assert_awaited()
        args, kwargs = channel.send.await_args
        assert isinstance(kwargs["embed"], discord.Embed)
        assert kwargs["view"] is MockView.return_value

        # check embed fields
        embed = kwargs["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert fields["Host"] == interaction.user.mention
        assert fields["Entries"] == "0"
        assert fields["Winners"] == "2"

        m = re.search(r"<t:(\d+):R>", fields["Ends"])
        assert m
        end_dt = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
        delta = end_dt - start
        assert (
            timedelta(minutes=2, seconds=30)
            <= delta
            <= timedelta(minutes=3, seconds=30)
        )

        mock_create.assert_awaited_once()


# -------- Tests for GiveawayView (embed safety + enter button) --------


@pytest.mark.asyncio
async def test_view_update_entry_count_adds_embed_and_field(monkeypatch, sent_message):
    from views.giveaway_view import GiveawayView

    # No embeds to start with
    sent_message.embeds = []
    # DB returns count
    monkeypatch.setattr(
        "views.giveaway_view.db.get_entry_count", AsyncMock(return_value=5)
    )
    view = GiveawayView()
    await view._update_entry_count(sent_message)
    sent_message.edit.assert_awaited()
    args, kwargs = sent_message.edit.await_args
    embed = kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Entries"] == "5"


@pytest.mark.asyncio
async def test_view_update_entry_count_updates_existing_field(
    monkeypatch, sent_message
):
    from views.giveaway_view import GiveawayView

    e = discord.Embed()
    e.add_field(name="Entries", value="0", inline=True)
    sent_message.embeds = [e]
    monkeypatch.setattr(
        "views.giveaway_view.db.get_entry_count", AsyncMock(return_value=9)
    )
    view = GiveawayView()
    await view._update_entry_count(sent_message)
    args, kwargs = sent_message.edit.await_args
    embed = kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Entries"] == "9"


@pytest.mark.asyncio
async def test_enter_button_success_updates_count(monkeypatch, user, channel):
    from views.giveaway_view import GiveawayView

    msg = MagicMock(spec=discord.Message)
    msg.id = 777
    msg.embeds = []
    msg.edit = AsyncMock()

    inter = MagicMock(spec=discord.Interaction)
    inter.user = user
    inter.message = msg
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()

    # NEW: the view checks the giveaway is still active
    monkeypatch.setattr(
        "views.giveaway_view.db.get_giveaway_by_id",
        AsyncMock(return_value={"is_active": True}),
    )
    monkeypatch.setattr(
        "views.giveaway_view.db.add_entry", AsyncMock(return_value=(True, "ok"))
    )
    monkeypatch.setattr(
        "views.giveaway_view.db.get_entry_count", AsyncMock(return_value=1)
    )

    view = GiveawayView()
    button = next(ch for ch in view.children if isinstance(ch, discord.ui.Button))
    await button.callback(inter)

    inter.response.send_message.assert_awaited()
    msg.edit.assert_awaited()


@pytest.mark.asyncio
async def test_enter_button_duplicate(monkeypatch, user):
    from views.giveaway_view import GiveawayView

    msg = MagicMock(spec=discord.Message)
    msg.id = 777
    msg.embeds = []
    msg.edit = AsyncMock()

    inter = MagicMock(spec=discord.Interaction)
    inter.user = user
    inter.message = msg
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()

    # NEW: still active, but duplicate add
    monkeypatch.setattr(
        "views.giveaway_view.db.get_giveaway_by_id",
        AsyncMock(return_value={"is_active": True}),
    )
    monkeypatch.setattr(
        "views.giveaway_view.db.add_entry", AsyncMock(return_value=(False, "already"))
    )

    view = GiveawayView()
    button = next(ch for ch in view.children if isinstance(ch, discord.ui.Button))
    await button.callback(inter)

    inter.response.send_message.assert_awaited()
    msg.edit.assert_not_awaited()


# -------- Tests for ending logic --------


@pytest.mark.asyncio
async def test_process_ended_giveaway_short_circuit_when_already_ended(
    monkeypatch, bot, channel, guild, giveaway_row
):
    from cogs.giveaway import Giveaway

    cog = Giveaway(bot)
    bot.get_channel.return_value = channel
    bot.get_guild.return_value = guild

    # end_giveaway returns False => do nothing
    monkeypatch.setattr("cogs.giveaway.db.end_giveaway", AsyncMock(return_value=False))
    await cog.process_ended_giveaway(giveaway_row)
    channel.fetch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_ended_giveaway_no_entrants_updates_embed(
    monkeypatch, bot, channel, guild, sent_message, giveaway_row
):
    from cogs.giveaway import Giveaway

    cog = Giveaway(bot)
    bot.get_channel.return_value = channel
    bot.get_guild.return_value = guild
    channel.fetch_message.return_value = sent_message

    base = discord.Embed(title="🎉 Giveaway: Fancy Prize 🎉")
    base.add_field(name="Host", value="<@42>", inline=True)
    sent_message.embeds = [base]

    monkeypatch.setattr("cogs.giveaway.db.end_giveaway", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "cogs.giveaway.db.get_giveaway_entrants", AsyncMock(return_value=[])
    )

    await cog.process_ended_giveaway(giveaway_row)

    sent_message.edit.assert_awaited()
    _, kwargs = sent_message.edit.await_args
    assert kwargs["view"] is None
    emb = kwargs["embed"]
    assert emb.title == "🎉 Giveaway Ended! 🎉"
    fields = {f.name: f.value for f in emb.fields}
    assert fields["Prize"] == "Fancy Prize"
    # New code puts the “no winners” message into the Winners field
    assert "no one" in fields["Winners"].lower()


@pytest.mark.asyncio
async def test_process_ended_giveaway_picks_winners(
    monkeypatch, bot, channel, guild, sent_message, giveaway_row
):
    from cogs.giveaway import Giveaway, config

    cog = Giveaway(bot)
    bot.get_channel.return_value = channel
    bot.get_guild.return_value = guild
    channel.fetch_message.return_value = sent_message

    base = discord.Embed(title="🎉 Giveaway: Fancy Prize 🎉")
    base.add_field(name="Winners", value="TBD", inline=False)
    sent_message.embeds = [base]

    # Entrant members
    def _mk(uid):
        m = MagicMock(spec=discord.Member)
        m.id = uid
        m.mention = f"<@{uid}>"
        m.roles = []
        return m

    members = {1: _mk(1), 2: _mk(2), 3: _mk(3)}

    monkeypatch.setattr("cogs.giveaway.db.end_giveaway", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "cogs.giveaway.db.get_giveaway_entrants", AsyncMock(return_value=[1, 2, 3])
    )

    # NEW: resolve entrants via fetch_member_safe (used inside _get_valid_entrants)
    async def _fake_fetch_member_safe(guild_obj, uid):
        return members.get(uid)

    monkeypatch.setattr("cogs.giveaway.fetch_member_safe", _fake_fetch_member_safe)

    monkeypatch.setattr(config, "DEFAULT_WEIGHT", 1, raising=False)
    monkeypatch.setattr(config, "ROLE_WEIGHTS", {}, raising=False)

    await cog.process_ended_giveaway(giveaway_row)

    sent_message.edit.assert_awaited()
    _, kwargs = sent_message.edit.await_args
    emb = kwargs["embed"]
    assert emb.title == "🎉 Giveaway Ended! 🎉"
    winners_field = next((f for f in emb.fields if f.name == "Winners"), None)
    assert winners_field and "<@" in winners_field.value
    sent_message.reply.assert_awaited()


# -------- Loop trigger test --------


@pytest.mark.asyncio
async def test_check_giveaways_loop_triggers_processing(monkeypatch, bot, giveaway_row):
    from cogs.giveaway import Giveaway

    cog = Giveaway(bot)
    # NEW: loop queries due giveaways
    monkeypatch.setattr(
        "cogs.giveaway.db.get_due_giveaways", AsyncMock(return_value=[giveaway_row])
    )
    proc = AsyncMock()
    cog.process_ended_giveaway = proc

    await cog.check_giveaways_loop.coro(cog)

    proc.assert_awaited_once_with(giveaway_row)


@pytest.mark.asyncio
async def test_process_xp_gain_happy_path_updates_db(monkeypatch):
    from cogs.leveling import Leveling
    from data import database as db

    bot = MagicMock(spec=discord.Client)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10
    author = MagicMock(spec=discord.Member)
    author.id = 99
    author.bot = False
    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.guild = guild
    msg.channel = channel

    # mock DB calls as AsyncMock (these are awaited in the cog)
    monkeypatch.setattr(
        "cogs.leveling.database.get_user", AsyncMock(return_value=(0, 0))
    )
    su = AsyncMock()
    inc = AsyncMock()
    monkeypatch.setattr("cogs.leveling.database.set_user_xp_and_level", su)
    monkeypatch.setattr("cogs.leveling.database.increment_daily_xp", inc)

    cog = Leveling(bot)
    # avoid randomness for determinism
    monkeypatch.setattr("random.randint", lambda a, b: 5)

    # call
    res = await cog._process_xp_gain(msg)

    assert res is not None and res.new_level >= 0
    su.assert_awaited_once()  # <- was False before
    inc.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_xp_gain_respects_cooldown(monkeypatch):
    from cogs.leveling import Leveling

    bot = MagicMock(spec=discord.Client)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 10
    author = MagicMock(spec=discord.Member)
    author.id = 99
    author.bot = False
    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.guild = guild
    msg.channel = channel

    # DB reads/writes
    monkeypatch.setattr(
        "cogs.leveling.database.get_user", AsyncMock(return_value=(0, 0))
    )
    monkeypatch.setattr("cogs.leveling.database.set_user_xp_and_level", AsyncMock())
    monkeypatch.setattr("cogs.leveling.database.increment_daily_xp", AsyncMock())

    cog = Leveling(bot)
    cog.guild_cooldowns[guild.id] = 60  # 60s cooldown

    # first call awards XP
    r1 = await cog._process_xp_gain(msg)
    assert r1 is not None

    # second call immediately should be skipped
    r2 = await cog._process_xp_gain(msg)  # <- you weren’t awaiting this
    assert r2 is None
