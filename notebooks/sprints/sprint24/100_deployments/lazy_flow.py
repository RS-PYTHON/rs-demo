import random
import time

from prefect import flow, get_run_logger
from resources.prefect_utils import get_ip_address


@flow(name="lazy-flow")
def lazy_flow(flow_id: int, should_raise: bool):
    logger = get_run_logger()
    logger.info(f"Hello from flow B {flow_id} {get_ip_address()!r}")
    sleep_time = random.randint(1, 10)
    logger.info(f"Flow B {flow_id} will sleep {sleep_time} seconds")
    time.sleep(sleep_time)
    if should_raise:
        raise RuntimeError(f"Flow B {flow_id} failed")
    return
