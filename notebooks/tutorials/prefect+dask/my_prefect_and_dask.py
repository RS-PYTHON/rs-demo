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
# Example flow and tasks from: https://docs.prefect.io/integrations/prefect-dask/index#connect-to-an-existing-cluster
#

# import dask.dataframe
# import dask.distributed

import logging
import os
import sys

from dask.distributed import worker_client
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner, get_dask_client

sys.path.append("./resources")
import dask_utils

gateway = dask_utils.get_dask_gateway(os.environ["DASK_GATEWAY_ADDRESS"])
existing_cluster_name = os.environ["DASK_CLUSTER_NAME"]
cluster = gateway.connect(existing_cluster_name)
client = cluster.get_client()

client.forward_logging()

client.upload_file("./resources/dask_utils.py")

logging.warning(f" IP address outside of functions: {dask_utils.get_ip_address()}")


@task
def inc(x):
    logger = get_run_logger()
    logger.warning(f" IP address for 'inc': {dask_utils.get_ip_address()}")

    return x + 1


@task
def add(x, y):
    logger = get_run_logger()
    logger.warning(f" IP address for 'add': {dask_utils.get_ip_address()}")
    return x + y


@flow(
    task_runner=DaskTaskRunner(
        address=cluster.scheduler_address,
        client_kwargs={"security": cluster.security},
    ),
)
def my_flow():
    logger = get_run_logger()
    logger.warning(f" IP address for 'my_flow': {dask_utils.get_ip_address()}")

    a = client.submit(inc, 10)  # calls inc(10) in background thread or process
    b = client.submit(inc, 20)  # calls inc(20) in background thread or process
    logger.warning(f"a: {a.result()}")
    logger.warning(f"b: {b.result()}")

    c = client.submit(add, a, b)  # calls add on the results of a and b
    logger.warning(f"c: {c.result()}")

    futures = client.map(inc, range(5))
    results = client.gather(futures)  # this can be faster
    logger.warning(results)


# From: https://github.com/PrefectHQ/prefect/issues/12971

import dask
from dask.distributed import worker_client


@task
def calling_compute_in_a_task():
    logger = get_run_logger()
    logger.warning(f" IP address for 'task': {dask_utils.get_ip_address()}")
    with worker_client() as client:
        logger.warning(f" IP address for 'task': {dask_utils.get_ip_address()}")
        df = dask.datasets.timeseries("2000", "2001", partition_freq="2w")
        summary_df = df.describe()
        client.compute(summary_df)
        return summary_df


@flow(
    task_runner=DaskTaskRunner(
        address=cluster.scheduler_address,
        client_kwargs={"security": cluster.security},
    ),
)
def test_flow():
    logger = get_run_logger()
    logger.warning(f" IP address for 'flow': {dask_utils.get_ip_address()}")
    ret = calling_compute_in_a_task.submit()
    return ret  # .result()
