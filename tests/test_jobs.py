import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from config.settings import DoorImages, Settings
from halloween.manager import DoorManager
from halloween.models import Language


def manager():
    settings = Settings(
        "test",
        "postgresql://test@localhost/test?sslmode=require",
        {lang: DoorImages() for lang in Language},
    )
    return DoorManager(SimpleNamespace(repo=None, settings=settings))


async def test_duplicate_job_is_not_run_and_shutdown_cancels_work():
    mgr = manager()
    waiting = asyncio.Event()
    work = AsyncMock(side_effect=waiting.wait)
    mgr.start_job("one", work())
    mgr.start_job("one", work())
    await asyncio.sleep(0)
    assert work.await_count == 1
    await mgr.stop_jobs()
    assert not mgr.jobs


async def test_failing_job_can_not_retry_in_tight_loop():
    mgr = manager()
    work = AsyncMock(side_effect=ValueError("Test failure"))
    mgr.start_job("failure", work())
    await asyncio.gather(*list(mgr.jobs.values()), return_exceptions=True)
    mgr.start_job("failure", work())
    await asyncio.sleep(0)
    assert work.await_count == 1
    assert not mgr.jobs
