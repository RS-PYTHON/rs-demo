from prefect import flow, get_run_logger
from prefect.deployments.flow_runs import run_deployment
from prefect.client.schemas.objects import StateType
import asyncio
import random

@flow
async def main():
    logger = get_run_logger()
    logger.info("Launching 100 deployed flows...")

    tasks = []
    for i in range(10):
        task = run_deployment(
            name="lazy-flow/lazy_flow",
            parameters={"flow_id": i, "should_raise": random.choice([True, False])},
            as_subflow = False
        )
        tasks.append(task)

    flows = await asyncio.gather(*tasks)
    logger.info("All deployments triggered")
    [logger.info(f"Flow B {flow.id} FAILED") for flow in flows if flow.state.type == StateType.FAILED]
    return