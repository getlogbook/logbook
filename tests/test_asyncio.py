import asyncio

import logbook

ITERATIONS = 100


def test_asyncio_context_management(logger):
    h1 = logbook.TestHandler()
    h2 = logbook.TestHandler()

    async def task(handler, msg):
        for _ in range(ITERATIONS):
            with handler.contextbound():
                logger.info(msg)

            await asyncio.sleep(0)  # allow for context switch

    asyncio.get_event_loop().run_until_complete(
        asyncio.gather(task(h1, "task1"), task(h2, "task2"))
    )

    assert len(h1.records) == ITERATIONS
    assert all(["task1" == r.msg for r in h1.records])

    assert len(h2.records) == ITERATIONS
    assert all(["task2" == r.msg for r in h2.records])
