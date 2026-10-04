from utils.cooldowns import Cooldowns


def test_remaining_and_independent_commands_and_users():
    now = [100.0]
    cd = Cooldowns(clock=lambda: now[0])
    assert cd.take(1, 10, "dulces") == 0
    now[0] += 13
    assert cd.take(1, 10, "dulces") == 17
    assert cd.take(1, 10, "doces") == 0
    assert cd.take(1, 11, "dulces") == 0
    now[0] += 17
    assert cd.take(1, 10, "dulces") == 0


def test_failed_command_releases_cooldown():
    cd = Cooldowns()
    cd.take(1, 10, "dulces")
    cd.release(1, 10, "dulces")
    assert cd.take(1, 10, "dulces") == 0
