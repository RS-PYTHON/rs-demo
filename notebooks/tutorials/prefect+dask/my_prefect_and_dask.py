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

"""Python module for the tutorials, to be shared with the prefect and dask workers.

Implement utility functions and prefect and dask tasks and flows.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

#
# Example flow and tasks from: https://github.com/PrefectHQ/prefect/issues/12971
#

import logging
import os
import sys
from pathlib import Path

import dask
from dask_expr._collection import DataFrame
from distributed.client import Future
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner

# My local "./resources" folder contains my utility modules.
# I want to be able to use the same "from dask_utils import ..." line on both client, prefect and dask workers.
# For this, I'm updating my PYTHONPATH.
sys.path.append("./resources")
import dask_utils
import prefect_utils
from dask_utils import get_ip_address

# Convert the prefect blocks into environment variables
prefect_utils.blocks_to_env_vars(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
dask_gateway, dask_cluster, dask_client = dask_utils.get_existing_cluster(
    os.environ["DASK_GATEWAY_ADDRESS"],
    os.environ["DASK_CLUSTER_NAME"],
)

# Now I need to upload my local utility module to the dask workers
dask_client.upload_file("./resources/dask_utils.py")

# NOTE: the main code outside the functions is run by both the client and prefect workers,
# but NOT by the dask workers.
# But this log won't show when run from a prefect worker because get_run_logger() is not available yet.
# The dask workers will do the imports and run the tasks, but won't run the flow or code outside functions.
logging.warning(
    f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (main code)",
)
# You can test to write an empty file to check that it is written only on the client
# and prefect workers filesystems, not on the dask workers filesystem.
Path("/tmp/.empty").touch()

# NOTE: the tasks are called only by the dask workers, not by the client or prefect.


@task
def calling_compute_in_a_task(logger, start: str, end: str, freq: str) -> DataFrame:
    """Compute dataframe in a dask task."""
    # Say hello from the dask task
    logger.warning(
        f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (task)",
    )

    # Create timeseries dataframe with random data
    df: DataFrame = dask.datasets.timeseries(start, end, partition_freq=freq)

    # Generate descriptive statistics
    # https://docs.dask.org/en/latest/generated/dask.dataframe.DataFrame.describe.html
    summary_df: DataFrame = df.describe()

    # Compute this DataFrame
    # https://docs.dask.org/en/stable/generated/dask.dataframe.DataFrame.compute.html
    summary_df.compute()
    return summary_df


@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster.scheduler_address,
        client_kwargs={"security": dask_cluster.security},
    ),
)
def my_flow(start: str, end: str, freq: str) -> DataFrame:
    """
    Main flow. Called only by the client or prefect worker (depending on how we call prefect),
    not by the dask workers.
    """
    logger = get_run_logger()
    logger.warning(
        f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (flow)",
    )

    future: Future = dask_client.submit(
        calling_compute_in_a_task,
        logger,
        start,
        end,
        freq,
        pure=False,  # use pure=False to disable cache
    )
    result: DataFrame = future.result()
    logger.warning(f"\nResults:\n{result}")
    return result
