from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import re

import pytest
import discord

from cogs.giveaway import Giveaway


@pytest.fixture
def bot():
    return MagicMock(spec=discord.Client)


@pytest.fixture
def cog(bot):
    return Giveaway(bot)


@pytest.fixture
def fake_channel():
    ch = MagicMock(spec=discord.TextChannel)
    ch.send = AsyncMock()
    return ch


@pytest.fixture
def interaction(fake_channel):
    user = MagicMock(spec=discord.Member)
    user.id = 123
    user.mention = "@tester"
    user.display_name = "tester"
    user.display_avatar = MagicMock()
    user.display_avatar.url = "https://example/avatar.png"

    i = MagicMock(spec=discord.Interaction)
    i.user = user
    i.channel = fake_channel
    i.response = MagicMock()
    i.response.send_message = AsyncMock()
    return i


async def _run_cmd(cog, interaction, **kwargs):
    # Call the underlying callback on the AppCommand
    return await cog.giveaway_start.callback(
        cog, interaction, kwargs["prize"], kwargs["duration"], kwargs["winners"]
    )


@pytest.mark.asyncio
async def test_giveaway_rejects_invalid_args(cog, interaction):
    # duration <= 0
    await _run_cmd(cog, interaction, prize="Prize", duration=0, winners=1)
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "must be greater than zero" in args[0]
    assert kwargs.get("ephemeral") is True

    interaction.response.send_message.reset_mock()

    # winners <= 0
    await _run_cmd(cog, interaction, prize="Prize", duration=5, winners=0)
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.await_args
    assert "must be greater than zero" in args[0]
    assert kwargs.get("ephemeral") is True


@pytest.mark.asyncio
async def test_giveaway_happy_path_sets_view_and_message(
    cog, interaction, fake_channel
):
    start = datetime.now(timezone.utc)

    with patch("cogs.giveaway.GiveawayView") as MockView:
        view_instance = MagicMock()
        MockView.return_value = view_instance

        sent_message = MagicMock(spec=discord.Message)
        fake_channel.send.return_value = sent_message

        await _run_cmd(
            cog,
            interaction,
            prize="Fancy Prize",
            duration=3,
            winners=2,
        )

        # 1) Ephemeral confirmation
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.await_args
        assert "Giveaway started!" in args[0]
        assert kwargs.get("ephemeral") is True

        # 2) Channel send with embed + view
        fake_channel.send.assert_awaited_once()
        args, kwargs = fake_channel.send.await_args
        assert "embed" in kwargs and isinstance(kwargs["embed"], discord.Embed)
        assert "view" in kwargs and kwargs["view"] is view_instance

        # 3) Embed fields sanity
        embed: discord.Embed = kwargs["embed"]
        fields = {f.name: f.value for f in embed.fields}
        assert fields["Host"] == interaction.user.mention
        assert fields["Entries"] == "0"
        assert fields["Winners"] == "2"

        # Ends field contains unix ts ~ now+3min
        m = re.search(r"<t:(\d+):R>", fields["Ends"])
        assert m, f"Ends field format unexpected: {fields['Ends']}"
        end_ts = int(m.group(1))
        end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
        delta = end_dt - start
        assert (
            timedelta(minutes=2, seconds=30)
            <= delta
            <= timedelta(minutes=3, seconds=30)
        )

        # 4) GiveawayView constructed with correct args
        _, vkwargs = MockView.call_args
        assert vkwargs["prize"] == "Fancy Prize"
        assert vkwargs["winner_count"] == 2
        assert vkwargs["host"] == interaction.user
        assert vkwargs["end_time"] > start

        # 5) view.message set to the sent message
        assert view_instance.message is sent_message
