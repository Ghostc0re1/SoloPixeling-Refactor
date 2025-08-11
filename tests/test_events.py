# tests/test_events.py
from io import BytesIO
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

import config
from cogs.events import Events


@pytest.fixture
def bot(mocker):
    bot = MagicMock(spec=discord.Client)
    # get_guild used in Events.on_ready? (not strictly needed)
    bot.get_guild = MagicMock()
    return bot


@pytest.fixture
def cog(bot):
    return Events(bot)


@pytest.fixture
def fake_channel(mocker):
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 123456
    ch.name = "welcome"
    ch.send = AsyncMock()
    return ch


@pytest.fixture
def fake_guild(fake_channel, mocker):
    g = MagicMock(spec=discord.Guild)
    g.id = 9999
    g.get_channel = MagicMock(return_value=fake_channel)
    return g


@pytest.fixture
def member_factory(fake_guild):
    def _mk(**overrides):
        m = MagicMock(spec=discord.Member)
        m.bot = overrides.get("bot", False)
        m.display_name = overrides.get("display_name", "TestUser")
        m.mention = overrides.get("mention", "@TestUser")
        m.guild = overrides.get("guild", fake_guild)
        m.roles = overrides.get("roles", [])
        m.id = overrides.get("id", 42)
        m.display_avatar = SimpleNamespace(url="https://example.com/avatar.png")
        return m

    return _mk


# ---------- on_ready


@pytest.mark.asyncio
async def test_on_ready_loads_welcome_channels(cog, mocker):
    mock_db = mocker.patch(
        "cogs.events.database.get_all_channel_settings",
        new=AsyncMock(return_value={111: {"welcome": 222}, 333: {"welcome": 444}}),
    )
    await cog.on_ready()
    assert cog.welcome_channels == {111: 222, 333: 444}
    mock_db.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_ready_loads_welcome_channels(cog, mocker):
    mock_db = mocker.patch("cogs.events.database.get_all_channel_settings")
    mock_db.return_value = {111: {"welcome": 222}, 333: {"welcome": 444}}
    await cog.on_ready()
    assert cog.welcome_channels == {111: 222, 333: 444}


# ---------- on_member_join


@pytest.mark.asyncio
async def test_on_member_join_ignores_bots(cog, member_factory, mocker):
    m = member_factory(bot=True)
    await cog.on_member_join(m)
    # nothing should be sent; no exception = pass


@pytest.mark.asyncio
async def test_on_member_join_wrong_guild_ignored(cog, member_factory, mocker):
    mocker.patch.object(config, "GUILD_ID", 5555)
    m = member_factory()
    m.guild.id = 9999  # doesn't match
    await cog.on_member_join(m)


@pytest.mark.asyncio
async def test_on_member_join_channel_not_found(
    cog, member_factory, fake_guild, mocker
):
    mocker.patch.object(config, "GUILD_ID", fake_guild.id)
    # channel id set to something else so get_channel returns None
    cog.welcome_channels[fake_guild.id] = 777777
    fake_guild.get_channel.return_value = None
    m = member_factory(guild=fake_guild)
    await cog.on_member_join(m)


@pytest.mark.asyncio
async def test_on_member_join_uses_default_channel(
    cog, member_factory, fake_guild, fake_channel, mocker
):
    mocker.patch.object(config, "GUILD_ID", fake_guild.id)
    mocker.patch.object(config, "DEFAULT_WELCOME_CHANNEL_ID", fake_channel.id)
    # no explicit setting -> falls back to default
    m = member_factory(guild=fake_guild)
    with patch(
        "cogs.events.image_utils.make_multiline_glow", return_value=BytesIO(b"ok")
    ):
        await cog.on_member_join(m)
    fake_channel.send.assert_awaited()
    args, kwargs = fake_channel.send.await_args
    assert kwargs["content"] == m.mention
    assert kwargs["file"].filename.endswith("welcome.png")


@pytest.mark.asyncio
async def test_on_member_join_image_utils_error_fallback_text(
    cog, member_factory, fake_guild, fake_channel, mocker
):
    mocker.patch.object(config, "GUILD_ID", fake_guild.id)
    mocker.patch.object(config, "DEFAULT_WELCOME_CHANNEL_ID", fake_channel.id)
    with patch(
        "cogs.events.image_utils.make_multiline_glow", side_effect=RuntimeError("boom")
    ):
        m = member_factory(guild=fake_guild)
        await cog.on_member_join(m)
    assert fake_channel.send.await_count >= 1  # fallback attempted


@pytest.mark.asyncio
async def test_on_member_join_fallback_forbidden_is_caught(
    cog, member_factory, fake_guild, fake_channel, mocker
):
    mocker.patch.object(config, "GUILD_ID", fake_guild.id)
    mocker.patch.object(config, "DEFAULT_WELCOME_CHANNEL_ID", fake_channel.id)

    with patch(
        "cogs.events.image_utils.make_multiline_glow", side_effect=Exception("boom")
    ):

        async def raise_forbidden(*args, **kwargs):
            raise discord.errors.Forbidden(MagicMock(), "no perms")

        fake_channel.send.side_effect = [raise_forbidden]
        m = member_factory(guild=fake_guild)
        await cog.on_member_join(m)
    # no exception = pass


# ---------- on_member_update


@pytest.mark.asyncio
async def test_on_member_update_sends_role_alert(
    cog, fake_guild, fake_channel, mocker, member_factory
):
    # configure alert
    role_id = 1234
    ch_id = fake_channel.id
    mocker.patch.object(
        config, "ROLE_ALERTS", [(role_id, ch_id, "🎉 {member} is now a Monarch!")]
    )

    # after gets a new role
    role = MagicMock()
    role.id = role_id

    before = member_factory(guild=fake_guild)
    before.roles = []

    after = member_factory(guild=fake_guild)
    after.roles = [role]

    await cog.on_member_update(before, after)
    fake_channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_member_update_channel_not_found(
    cog, fake_guild, mocker, member_factory
):
    role_id = 1234
    ch_id = 999999
    mocker.patch.object(config, "ROLE_ALERTS", [(role_id, ch_id, "msg {member}")])

    # Override the fixture’s default so this returns None
    fake_guild.get_channel.return_value = None

    role = MagicMock()
    role.id = role_id
    before = member_factory(guild=fake_guild)
    before.roles = []
    after = member_factory(guild=fake_guild)
    after.roles = [role]

    await cog.on_member_update(before, after)  # should not crash


@pytest.mark.asyncio
async def test_on_member_update_forbidden(
    cog, fake_guild, fake_channel, mocker, member_factory
):
    role_id = 1234
    ch_id = fake_channel.id
    mocker.patch.object(config, "ROLE_ALERTS", [(role_id, ch_id, "msg {member}")])

    role = MagicMock()
    role.id = role_id
    before = member_factory(guild=fake_guild)
    before.roles = []
    after = member_factory(guild=fake_guild)
    after.roles = [role]

    fake_channel.send.side_effect = discord.errors.Forbidden(MagicMock(), "no perms")

    await cog.on_member_update(before, after)  # shouldn’t raise
