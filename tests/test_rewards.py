from halloween.rewards import roll_reward


def test_rewards_always_in_range():
    rewards = {roll_reward() for _ in range(1000)}
    assert rewards <= {1, 2, 3, 4, 5}
    assert min(rewards) >= 1
    assert max(rewards) <= 5
