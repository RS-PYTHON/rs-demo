import asyncio
import random

from prefect import flow, get_run_logger


@flow(name="lazy-flow")
async def lazy_flow(flow_id: int, should_raise: bool):
    logger = get_run_logger()
    logger.info(f"Hello from flow B {flow_id}")
    sleep_time = random.randint(1, 10)
    logger.info(f"Flow B {flow_id} will sleep {sleep_time} seconds")
    await asyncio.sleep(sleep_time)
    if should_raise:
        raise RuntimeError(f"Flow B {flow_id} failed")
    return


@flow
async def main():
    logger = get_run_logger()
    logger.info("Hello from main flow A")

    # Launch 100 flows concurrently, each as separate async tasks
    tasks = [
        asyncio.create_task(
            lazy_flow(
                flow_id=i,
                should_raise=random.choices([True, False], weights=[5, 95], k=1)[0],
            ),
        )
        for i in range(100)
    ]

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All flows triggered and completed")
