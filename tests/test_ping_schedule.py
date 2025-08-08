import pytest
from helpers.schedule_utils import PingSchedule


def test_valid_schedule_ok():
    s = PingSchedule(
        role_id=1,
        ch_id=2,
        ping_hour=9,
        ping_min=30,
        days=[0, 2, 4],
        msg="hi",
        delete_hour=None,
        delete_min=None,
    )
    assert tuple(s.days) == (0, 2, 4)


@pytest.mark.parametrize("days", [[], (), ()])
def test_days_cannot_be_empty(days):
    with pytest.raises(ValueError, match="days cannot be empty"):
        PingSchedule(1, 2, 9, 0, days, "x")


@pytest.mark.parametrize("bad_day", [-1, 7, 99])
def test_day_out_of_range(bad_day):
    with pytest.raises(ValueError, match="out of range"):
        PingSchedule(1, 2, 9, 0, [bad_day], "x")


@pytest.mark.parametrize(("h", "m"), [(-1, 0), (24, 0), (0, -1), (0, 60)])
def test_invalid_ping_time(h, m):
    with pytest.raises(ValueError, match="invalid ping time"):
        PingSchedule(1, 2, h, m, [1], "x")


def test_delete_time_both_or_none_required():
    # only hour set
    with pytest.raises(ValueError, match="both be set or both be None"):
        PingSchedule(1, 2, 9, 0, [1], "x", delete_hour=10, delete_min=None)
    # only minute set
    with pytest.raises(ValueError, match="both be set or both be None"):
        PingSchedule(1, 2, 9, 0, [1], "x", delete_hour=None, delete_min=15)


@pytest.mark.parametrize(("dh", "dm"), [(-1, 0), (24, 0), (0, -1), (0, 60)])
def test_delete_time_out_of_range(dh, dm):
    with pytest.raises(ValueError, match="delete_"):
        PingSchedule(1, 2, 9, 0, [1], "x", delete_hour=dh, delete_min=dm)
