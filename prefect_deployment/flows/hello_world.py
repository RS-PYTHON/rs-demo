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
""" Module that implements a prefect flow to be launched in a dask cluster """
import os

from dask_gateway import Gateway, JupyterHubAuth
from distributed import Client
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner


@flow(name="dask_cluster")
def dask_cluster():
    """The Prefect servers spawns a kubernetes pod for the prefect workers pool
    and runs this prefect flow in this pod
    """

    logger = get_run_logger()
    logger.info("Entering in dask_cluster")
    # check the auth type, only jupyterhub type supported for now
    auth_type = os.environ["DASK_GATEWAY__AUTH__TYPE"]
    # Handle JupyterHub authentication
    if auth_type == "jupyterhub":
        gateway_auth = JupyterHubAuth(api_token=os.environ["JUPYTERHUB_API_TOKEN"])
    else:
        logger.exception(f"Unsupported authentication type: {auth_type}")
        raise RuntimeError(f"Unsupported authentication type: {auth_type}")
    logger.info("Creating dask gateway object")
    gateway = Gateway(
        address=os.environ["DASK_GATEWAY__ADDRESS"],
        auth=gateway_auth,
    )
    logger.info(
        "The dask gateway object was created, getting the list with the present clusters",
    )
    clusters = gateway.list_clusters()
    logger.info(f"The list of clusters: {clusters}")
    cluster = gateway.connect(clusters[0].name)
    logger.info(f"First cluster scheduler address = {cluster.scheduler_address}")
    client = Client(cluster)
    logger.info(f"Dask client = {client}")
    try:
        logger.info(f"{client.get_versions(check=True)}")
        workers = client.scheduler_info()["workers"]
        logger.info(f"Number of running workers: {len(workers)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception(f"Dask cluster client failed: {e}")
        raise RuntimeError(f"Dask cluster client failed: {e}") from e
    if len(workers) == 0:
        logger.info(
            "No workers are currently running in the Dask cluster. Scaling up to 1.",
        )
        cluster.scale(1)

    # Prefect flow and task definitions
    @task
    def add_numbers(idx, x, y):
        """Example task to be used in a prefect flow
        The function simply adds two numbers
        This prefect task may be used as start point in creating your own prefect tasks

        Args:
            idx (int): Index of the task
            x (int): First operator
            y (int): Second operator
        """
        logger = get_run_logger()
        logger.info(f"Running task add_numbers index {idx}")
        return x + y

    @task
    def multiply_numbers(idx, x, y):
        """Example task to be used in a prefect flow
        The function simply multiplies two numbers
        This prefect task may be used as start point in creating your own prefect tasks

        Args:
            idx (int): Index of the task
            x (int): First operator
            y (int): Second operator
        """
        logger = get_run_logger()
        logger.info(f"Running task multiply_numbers index {idx}")
        return x * y

    @flow(
        task_runner=DaskTaskRunner(
            address=cluster.scheduler_address,
            client_kwargs={"security": cluster.security},
        ),
    )
    def hello_world(number_of_tasks=5):
        """Example flow that will be launched to run in a dask cluster

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
            add_numbers_tasks.append(add_numbers.submit(idx, idx + 5, idx + 3))
            multiply_numbers_tasks.append(
                multiply_numbers.submit(idx, idx + 5, idx + 3),
            )
        for t in add_numbers_tasks:
            logger.info(f"Sum result: {t.result()}")
        for t in multiply_numbers_tasks:
            logger.info(f"Product result: {t.result()}")

    hello_world()
