import secrets


def roll_reward() -> int:
    return secrets.randbelow(5) + 1


def roll_loss() -> int:
    return secrets.randbelow(4) + 2


def roll_candy_win(win_percent: int) -> bool:
    if not 0 <= win_percent <= 100:
        raise ValueError("Porcentaje inválido")
    return secrets.randbelow(100) < win_percent
