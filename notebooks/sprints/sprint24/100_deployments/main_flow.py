import asyncio
import random

from prefect import flow, get_run_logger
from prefect.client.schemas.objects import StateType
from prefect.deployments.flow_runs import run_deployment
from resources.dask_utils import get_ip_address


@flow(name="main-flow-deployment")
async def main_flow_deployment():
    logger = get_run_logger()
    logger.info(f"Launching 100 deployed flows... {get_ip_address()!r}")

    tasks = []
    for i in range(10):
        task = run_deployment(
            name="lazy-flow-deployment/lazy_flow_deployment",
            parameters={
                "flow_id": i,
                "should_raise": random.choices([True, False], weights=[30, 70], k=1)[0],
            },
            as_subflow=False,
        )
        tasks.append(task)

    flows = await asyncio.gather(*tasks)
    logger.info("All deployments triggered")
    [
        logger.info(f"Flow B {flow.id} FAILED")
        for flow in flows
        if flow.state.type == StateType.FAILED
    ]
    return
