import secrets


def roll_reward() -> int:
    return secrets.randbelow(5) + 1
