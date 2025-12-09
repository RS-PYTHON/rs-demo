# Copyright 2025 Airbus, CS Group
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import random

from prefect import flow, get_run_logger
from rs_common.prefect_utils import get_ip_address


@flow(name="lazy-flow-asyncio")
async def lazy_flow(flow_id: int, should_raise: bool):
    logger = get_run_logger()
    logger.info(f"Hello from flow B {flow_id} {get_ip_address()!r}")
    sleep_time = random.randint(1, 10)
    logger.info(f"Flow B {flow_id} will sleep {sleep_time} seconds")
    await asyncio.sleep(sleep_time)
    if should_raise:
        raise RuntimeError(f"Flow B {flow_id} failed")
    return


@flow(name="main-flow-asyncio")
async def main_flow_asyncio():
    logger = get_run_logger()
    logger.info(f"Hello from main flow A {get_ip_address()!r}")

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
