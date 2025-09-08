# Copyright 2024 CS Group
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
"""Module that implements a prefect flow to be launched in a dask cluster"""

import os
from importlib import reload

from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner
from resources import dask_utils
from rs_common import prefect_utils

# Read prefect blocks into env vars
prefect_utils.read_prefect_blocks(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
reload(dask_utils)  # reload global vars from env vars
dask_gateway, dask_cluster, dask_client = dask_utils.get_existing_cluster(
    os.environ["DASK_GATEWAY_ADDRESS"],
    os.environ["DASK_CLUSTER_INSTANCE"],
)

# Now I need to upload my local utility module to the dask workers
dask_client.upload_file("./resources/dask_utils.py")


# Prefect flow and task definitions
@task
def add_numbers(logger, idx, x, y):
    """Example task to be used in a prefect flow
    The function simply adds two numbers
    This prefect task may be used as start point in creating your own prefect tasks

    Args:
        idx (int): Index of the task
        x (int): First operator
        y (int): Second operator
    """
    logger.info(f"Running task add_numbers index {idx}")
    return x + y


@task
def multiply_numbers(logger, idx, x, y):
    """Example task to be used in a prefect flow
    The function simply multiplies two numbers
    This prefect task may be used as start point in creating your own prefect tasks

    Args:
        idx (int): Index of the task
        x (int): First operator
        y (int): Second operator
    """
    logger.info(f"Running task multiply_numbers index {idx}")
    return x * y


@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster.scheduler_address,
        client_kwargs={"security": dask_cluster.security},
    ),
)
def hello_world(number_of_tasks=5):
    """Example flow that will be launched to run in a dask cluster

    The Prefect servers spawns a kubernetes pod for the prefect workers pool
    and runs this prefect flow in this pod.

    This prefect flow may be used as start point in creating your own prefect flows. It runs in parallel
    add_numbers and multiply_numbers tasks

    Args:
        name (str): Username to be printed. Default COPERNICUS
        number_of_tasks (int): Number of tasks to be run. Default 5
    """
    logger = get_run_logger()
    add_numbers_tasks = []
    multiply_numbers_tasks = []
    for idx in range(0, number_of_tasks):
        add_numbers_tasks.append(add_numbers.submit(logger, idx, idx + 5, idx + 3))
        multiply_numbers_tasks.append(
            multiply_numbers.submit(logger, idx, idx + 5, idx + 3),
        )
    for t in add_numbers_tasks:
        logger.info(f"Sum result: {t.result()}")
    for t in multiply_numbers_tasks:
        logger.info(f"Product result: {t.result()}")
