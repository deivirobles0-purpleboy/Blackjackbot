import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from database.repositories import Repository
from halloween.models import ClaimStatus, DropStatus, Language

pytestmark = pytest.mark.postgres
GUILD = 900001
STAFF = 900002
CHANNEL = 900003


async def ready(repo, language=Language.ES, channel=CHANNEL):
    await repo.set_channel(GUILD, language, channel, STAFF)
    await repo.set_minutes(GUILD, language, 1, 1, STAFF)


async def door(repo, language=Language.ES, *, is_test=True, real=True):
    await ready(repo, language)
    if not is_test:
        await repo.set_enabled(GUILD, True, STAFF)
        await repo.pool.execute(
            "UPDATE event_config SET next_drop_at=now()-interval '1 second' WHERE guild_id=$1 AND language=$2",
            GUILD,
            language,
        )
    drop = await repo.prepare_drop(GUILD, language, CHANNEL, is_test=is_test, rewards_enabled=real)
    await repo.bind_message(drop.id, int(drop.id.int % 10**16) + 100)
    return await repo.drop(drop.id)


async def claim(repo, drop, user_id, eligible=True):
    return await repo.claim(
        drop.id,
        user_id,
        eligible,
        guild_id=GUILD,
        channel_id=CHANNEL,
        message_id=drop.message_id,
        language=drop.language,
    )


async def test_simultaneous_claims_max_two_and_no_role_no_slot(repo):
    drop = await door(repo)
    rejected = await asyncio.gather(*(claim(repo, drop, 100 + i, False) for i in range(20)))
    assert all(result.status == ClaimStatus.UNREGISTERED for result in rejected)
    assert await repo.winners(drop.id) == []
    results = await asyncio.gather(*(claim(repo, drop, 200 + i) for i in range(40)))
    assert sum(result.status == ClaimStatus.ACCEPTED for result in results) == 2
    winners = await repo.winners(drop.id)
    assert len(winners) == 2
    assert len({w["user_id"] for w in winners}) == 2
    assert (await repo.drop(drop.id)).status == DropStatus.PROCESSING
    ranks = await repo.ranking(GUILD, Language.ES)
    assert sorted((r["user_id"], r["candies"]) for r in ranks) == sorted(
        (w["user_id"], w["candies"]) for w in winners
    )


async def test_duplicate_claims_and_restart_are_idempotent(repo):
    drop = await door(repo)
    results = await asyncio.gather(*(claim(repo, drop, 11) for _ in range(20)))
    assert sum(r.status == ClaimStatus.ACCEPTED for r in results) == 1
    restarted = Repository(repo.pool)
    assert (await claim(restarted, drop, 11)).status == ClaimStatus.DUPLICATE
    assert (await claim(restarted, drop, 12)).status == ClaimStatus.ACCEPTED
    before = [dict(row) for row in await repo.ranking(GUILD, Language.ES)]
    await restarted.finish(drop.id)
    await restarted.finish(drop.id)
    assert (await claim(restarted, drop, 13)).status == ClaimStatus.CLOSED
    assert [dict(row) for row in await repo.ranking(GUILD, Language.ES)] == before
    assert (await repo.drop(drop.id)).status == DropStatus.FINISHED


async def test_db_constraints_enforce_two_unique_slots(repo):
    drop = await door(repo)
    await claim(repo, drop, 11)
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.pool.execute(
            "INSERT INTO door_winners (drop_id,user_id,slot,candies) VALUES ($1,12,3,2)", drop.id
        )
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.pool.execute(
            "INSERT INTO door_winners (drop_id,user_id,slot,candies) VALUES ($1,12,1,2)", drop.id
        )


async def test_simulated_test_preserves_ranking_and_auto_timer(repo):
    await ready(repo)
    await repo.set_enabled(GUILD, True, STAFF)
    before = await repo.config(GUILD, Language.ES)
    drop = await door(repo, real=False)
    await claim(repo, drop, 11)
    await claim(repo, drop, 12)
    await repo.finish(drop.id)
    after = await repo.config(GUILD, Language.ES)
    assert await repo.ranking(GUILD, Language.ES) == []
    assert before.next_drop_at == after.next_drop_at
    assert before.last_drop_at == after.last_drop_at
    assert len(await repo.winners(drop.id)) == 2


async def test_auto_creation_race_and_current_configuration_schedule(repo):
    await ready(repo)
    await repo.set_enabled(GUILD, True, STAFF)
    await repo.pool.execute(
        "UPDATE event_config SET next_drop_at=now()-interval '1 second' WHERE guild_id=$1", GUILD
    )
    drops = await asyncio.gather(*(repo.prepare_drop(GUILD, Language.ES) for _ in range(12)))
    assert sum(drop is not None for drop in drops) == 1
    drop = next(d for d in drops if d)
    await repo.bind_message(drop.id, 12345)
    await repo.set_minutes(GUILD, Language.ES, 7, 7, STAFF)
    await repo.finish(drop.id)
    cfg = await repo.config(GUILD, Language.ES)
    delay = (cfg.next_drop_at - datetime.now(timezone.utc)).total_seconds()
    assert 415 < delay <= 420
    assert cfg.last_drop_at == drop.created_at
    persisted = cfg.next_drop_at
    await repo.set_enabled(GUILD, True, STAFF)
    assert (await repo.config(GUILD, Language.ES)).next_drop_at == persisted
    await repo.set_enabled(GUILD, False, STAFF)
    assert (await repo.config(GUILD, Language.ES)).next_drop_at is None
    assert await repo.prepare_drop(GUILD, Language.ES) is None


async def test_rankings_isolated_stable_top15_and_audit(repo):
    for user_id in range(1, 21):
        await repo.adjust(GUILD, user_id, Language.ES, "add", 5, STAFF)
    await repo.adjust(GUILD, 1, Language.BR, "add", 60, STAFF)
    assert [r["user_id"] for r in await repo.ranking(GUILD, Language.ES)] == list(range(1, 16))
    assert (await repo.ranking(GUILD, Language.BR))[0]["candies"] == 60
    assert await repo.adjust(GUILD, 1, Language.ES, "remove", 10, STAFF) == 0
    assert await repo.adjust(GUILD, 1, Language.BR, "reset", 0, STAFF) == 0
    assert (
        await repo.pool.fetchval("SELECT count(*) FROM admin_logs WHERE admin_id=$1", STAFF) == 23
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.pool.execute("UPDATE user_candies SET candies=-1 WHERE guild_id=$1", GUILD)


async def test_atomic_rollback_if_reward_write_fails(repo):
    drop = await door(repo)
    await repo.adjust(GUILD, 11, Language.ES, "add", 9223372036854775807, STAFF)
    with pytest.raises(asyncpg.NumericValueOutOfRangeError):
        await claim(repo, drop, 11)
    assert await repo.winners(drop.id) == []
    assert (await repo.drop(drop.id)).status == DropStatus.OPEN


async def test_claim_rejects_wrong_message_and_language(repo):
    drop = await door(repo)
    result = await repo.claim(
        drop.id,
        11,
        True,
        guild_id=GUILD,
        channel_id=CHANNEL,
        message_id=drop.message_id + 1,
        language=Language.ES,
    )
    assert result.status == ClaimStatus.CLOSED
    result = await repo.claim(
        drop.id,
        11,
        True,
        guild_id=GUILD,
        channel_id=CHANNEL,
        message_id=drop.message_id,
        language=Language.BR,
    )
    assert result.status == ClaimStatus.CLOSED
    assert await repo.winners(drop.id) == []


async def test_independent_language_schedule_and_test_real_rewards(repo):
    await ready(repo, Language.ES)
    await ready(repo, Language.BR, CHANNEL + 1)
    await repo.set_minutes(GUILD, Language.BR, 10, 10, STAFF)
    await repo.set_enabled(GUILD, True, STAFF)
    es, br = await repo.config(GUILD, Language.ES), await repo.config(GUILD, Language.BR)
    assert br.next_drop_at - es.next_drop_at > timedelta(minutes=8)
    drop = await door(repo, real=True)
    await claim(repo, drop, 11)
    await claim(repo, drop, 12)
    await repo.finish(drop.id)
    assert len(await repo.ranking(GUILD, Language.ES)) == 2
    assert await repo.ranking(GUILD, Language.BR) == []
    assert (await repo.config(GUILD, Language.ES)).next_drop_at == es.next_drop_at


async def test_connection_replacement_keeps_claims_and_balances(repo):
    drop = await door(repo)
    first = await claim(repo, drop, 11)
    await repo.pool.expire_connections()
    restarted = Repository(repo.pool)
    assert (await claim(restarted, drop, 11)).status == ClaimStatus.DUPLICATE
    assert (await claim(restarted, drop, 12)).status == ClaimStatus.ACCEPTED
    rows = await restarted.ranking(GUILD, Language.ES)
    assert next(row["candies"] for row in rows if row["user_id"] == 11) == first.candies
    assert len(await restarted.winners(drop.id)) == 2


async def test_only_one_scheduler_can_own_session_lock(repo):
    from config.constants import INSTANCE_LOCK_KEY

    async with repo.pool.acquire() as first, repo.pool.acquire() as second:
        try:
            assert await first.fetchval("SELECT pg_try_advisory_lock($1)", INSTANCE_LOCK_KEY)
            assert not await second.fetchval("SELECT pg_try_advisory_lock($1)", INSTANCE_LOCK_KEY)
        finally:
            await first.execute("SELECT pg_advisory_unlock_all()")
        try:
            assert await second.fetchval("SELECT pg_try_advisory_lock($1)", INSTANCE_LOCK_KEY)
        finally:
            await second.execute("SELECT pg_advisory_unlock_all()")


async def test_startup_config_summary_is_scoped_and_read_only(repo):
    await ready(repo, Language.ES)
    await ready(repo, Language.BR)
    before = await repo.config(GUILD, Language.ES)
    assert await repo.guild_configs([]) == []
    assert await repo.guild_configs([GUILD + 1]) == []
    rows = await repo.guild_configs([GUILD])
    assert {cfg.language for cfg in rows} == {Language.ES, Language.BR}
    assert await repo.config(GUILD, Language.ES) == before
