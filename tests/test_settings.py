import types
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import discord
from discord.ext import commands

# The module under test
from cogs.settings import SettingsCog


async def call_cmd(cmd, cog, *args, **kwargs):
    return await cmd.callback(cog, *args, **kwargs)


@pytest.fixture
def bot():
    b = MagicMock(spec=commands.Bot)
    # Default: no external cogs unless a test sets them
    b.get_cog.return_value = None
    return b


@pytest.fixture
def guild():
    g = MagicMock(spec=discord.Guild)
    g.id = 123
    g.name = "TestGuild"
    # get_role / get_channel can be customized in specific tests
    return g


@pytest.fixture
def interaction(guild):
    it = MagicMock(spec=discord.Interaction)
    it.guild = guild
    it.user = MagicMock(spec=discord.Member)
    it.user.mention = "@user"

    # --- MOCK CORRECTIONS ---
    # Mock the response object and all its async methods
    it.response = MagicMock()
    it.response.send_message = AsyncMock()
    it.response.defer = AsyncMock()  # This was missing

    # Mock the followup object and its async send method
    it.followup = MagicMock()
    it.followup.send = AsyncMock()  # This was missing

    # original_response() is awaited too
    it.original_response = AsyncMock(return_value=MagicMock(spec=discord.Message))
    return it


@pytest.fixture
def cog(bot):
    return SettingsCog(bot)


# ------------- set-welcome -----------------


@pytest.mark.asyncio
async def test_set_welcome_channel_updates_db_and_cache_and_replies(cog, interaction):
    # fake channel to pass into the command
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 777
    channel.mention = "#welcome"

    # fake Events cog cache
    events_cog = types.SimpleNamespace(welcome_channels={})
    cog.bot.get_cog.return_value = events_cog

    with patch("cogs.settings.database.set_welcome_channel") as set_welcome:
        await call_cmd(SettingsCog.set_welcome_channel_cmd, cog, interaction, channel)

    set_welcome.assert_called_once_with(interaction.guild.id, channel.id)
    assert events_cog.welcome_channels[interaction.guild.id] == channel.id
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert "#welcome" in args[0]
    assert kwargs.get("ephemeral") is True


# ------------- set-levelup -----------------


@pytest.mark.asyncio
async def test_set_levelup_channel_updates_db_and_cache_and_replies(cog, interaction):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 999
    channel.mention = "#levelups"

    leveling_cog = types.SimpleNamespace(guild_levelup_channels={})
    cog.bot.get_cog.return_value = leveling_cog

    with patch("cogs.settings.database.set_levelup_channel") as set_levelup:
        await call_cmd(SettingsCog.set_levelup_channel_cmd, cog, interaction, channel)

    set_levelup.assert_called_once_with(interaction.guild.id, channel.id)
    assert leveling_cog.guild_levelup_channels[interaction.guild.id] == channel.id
    interaction.response.send_message.assert_called_once()


# ------------- purge -----------------


@pytest.mark.asyncio
async def test_purge_messages_sends_confirmation_and_stores_view_message(
    cog, interaction
):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111
    channel.mention = "#target"

    # Patch the view class so we don't rely on the actual implementation
    class FakeView:
        def __init__(self, ch, limit):
            self.channel = ch
            self.limit = limit
            self.message = None

    with patch("cogs.settings.PurgeConfirmationView", FakeView):
        await call_cmd(SettingsCog.purge_messages, cog, interaction, channel, limit=25)

    interaction.response.send_message.assert_called_once()
    # after sending, the view.message is set to original_response()
    # we ensure original_response was awaited/called once
    interaction.original_response.assert_called_once()
    # ensure our fake view got the right limit
    sent_args, sent_kwargs = interaction.response.send_message.call_args
    view = sent_kwargs["view"]
    assert isinstance(view, FakeView)
    assert view.limit == 25


# ------------- cooldown -----------------


@pytest.mark.asyncio
async def test_set_cooldown_rejects_negative(cog, interaction):
    await call_cmd(SettingsCog.set_cooldown, cog, interaction, seconds=-10)
    interaction.followup.send.assert_called_once()
    assert "cannot be negative" in interaction.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_set_cooldown_updates_db_and_cache(cog, interaction):
    leveling_cog = types.SimpleNamespace(guild_cooldowns={})
    cog.bot.get_cog.return_value = leveling_cog

    with patch("cogs.settings.database.set_xp_cooldown") as set_cd:
        await call_cmd(SettingsCog.set_cooldown, cog, interaction, seconds=42)

    set_cd.assert_called_once_with(interaction.guild.id, 42)
    assert leveling_cog.guild_cooldowns[interaction.guild.id] == 42
    interaction.followup.send.assert_called_once()


# ------------- xprange -----------------


@pytest.mark.asyncio
async def test_set_xprange_rejects_invalid(cog, interaction):
    await call_cmd(SettingsCog.set_xprange, cog, interaction, min_xp=10, max_xp=5)
    interaction.followup.send.assert_called_once()
    assert "Invalid XP range" in interaction.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_set_xprange_updates_db_and_cache(cog, interaction):
    leveling_cog = types.SimpleNamespace(guild_xp_ranges={})
    cog.bot.get_cog.return_value = leveling_cog

    with patch("cogs.settings.database.update_xp_range") as upd:
        await call_cmd(SettingsCog.set_xprange, cog, interaction, min_xp=1, max_xp=3)

    upd.assert_called_once_with(interaction.guild.id, 1, 3)
    assert leveling_cog.guild_xp_ranges[interaction.guild.id] == (1, 3)
    interaction.followup.send.assert_called_once()


# ------------- removeallxp -----------------


@pytest.mark.asyncio
async def test_removeallxp_no_xp(cog, interaction):
    member = MagicMock(spec=discord.Member)
    member.mention = "@mem"
    member.roles = []
    with patch("cogs.settings.database.get_user", return_value=None):
        await call_cmd(SettingsCog.removeallxp, cog, interaction, member)
    interaction.followup.send.assert_called_once()
    assert "no XP" in interaction.followup.send.call_args[0][0]


@pytest.mark.asyncio
async def test_removeallxp_clears_db_and_removes_roles(cog, interaction, monkeypatch):
    member = MagicMock(spec=discord.Member)
    member.mention = "@mem"
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.id = 55
    # They had high level role before
    r = MagicMock(spec=discord.Role)
    r.id = 9001
    r.name = "Elite"
    member.roles = [r]

    # config ROLE_REWARDS mapping
    monkeypatch.setattr("cogs.settings.config.ROLE_REWARDS", {10: r.id}, raising=True)

    # DB: user had xp+level
    with patch("cogs.settings.database.get_user", return_value=(1234, 10)), patch(
        "cogs.settings.database.set_user_xp_and_level"
    ) as set_user, patch("cogs.settings.build_xp_status") as build_status:

        # new status after wipe
        status = MagicMock()
        status.total_xp = 0
        status.level = 0
        status.xp_into_level = 0
        status.xp_to_next = 100
        build_status.return_value = status

        # guild.get_role returns our role
        interaction.guild.get_role.return_value = r

        await call_cmd(SettingsCog.removeallxp, cog, interaction, member)

    set_user.assert_called_once_with(member.id, interaction.guild.id, 0, 0)
    # removed role since threshold crossed downward
    member.remove_roles.assert_called_once()
    interaction.followup.send.assert_called_once()


# ------------- addxp -----------------


@pytest.mark.asyncio
async def test_addxp_awards_roles_and_updates_db(cog, interaction, monkeypatch):
    member = MagicMock(spec=discord.Member)
    member.mention = "@mem"
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.id = 99
    # make the role to award
    role = MagicMock(spec=discord.Role)
    role.id = 222
    role.name = "Champion"
    interaction.guild.get_role.return_value = role

    monkeypatch.setattr("cogs.settings.config.ROLE_REWARDS", {5: role.id}, raising=True)

    with patch("cogs.settings.database.get_user", return_value=(10, 0)), patch(
        "cogs.settings.database.set_user_xp_and_level"
    ) as set_user, patch("cogs.settings.build_xp_status") as build_status, patch(
        "cogs.settings.level_from_xp", return_value=1
    ):

        # new status will say level 5 achieved
        status = MagicMock()
        status.total_xp = 999
        status.level = 5
        status.xp_into_level = 10
        status.xp_to_next = 100
        build_status.return_value = status

        await call_cmd(SettingsCog.addxp, cog, interaction, member, amount=989)

    set_user.assert_called_once_with(member.id, interaction.guild.id, 999, 5)
    member.add_roles.assert_called_once()
    interaction.followup.send.assert_called_once()


# ------------- removexp -----------------


@pytest.mark.asyncio
async def test_removexp_drops_roles_and_updates_db(cog, interaction, monkeypatch):
    member = MagicMock(spec=discord.Member)
    member.mention = "@mem"
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.id = 77
    member.mention = "@m"
    # they currently have the role we'll drop
    role = MagicMock(spec=discord.Role)
    role.id = 333
    role.name = "Gold"
    member.roles = [role]
    interaction.guild.get_role.return_value = role

    monkeypatch.setattr("cogs.settings.config.ROLE_REWARDS", {3: role.id}, raising=True)

    with patch("cogs.settings.database.get_user", return_value=(250, 3)), patch(
        "cogs.settings.database.set_user_xp_and_level"
    ) as set_user, patch("cogs.settings.build_xp_status") as build_status, patch(
        "cogs.settings.level_from_xp", return_value=3
    ):

        # after removal, status shows level fell to 2
        status = MagicMock()
        status.total_xp = 100
        status.level = 2
        status.xp_into_level = 20
        status.xp_to_next = 50
        build_status.return_value = status

        await call_cmd(SettingsCog.removexp, cog, interaction, member, amount=150)

    set_user.assert_called_once_with(member.id, interaction.guild.id, 100, 2)
    member.remove_roles.assert_called_once()
    interaction.followup.send.assert_called_once()
