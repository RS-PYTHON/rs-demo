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

"""Python module for the tutorials, to be shared with the prefect workers.

Implement utility functions and prefect tasks and flows.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import asyncio
import importlib
import json
import os
import random
import typing

from fastapi.concurrency import run_in_threadpool
from prefect import flow, get_run_logger, task
from prefect.client.orchestration import get_client
from prefect.exceptions import ObjectNotFound
from resources.my_shared_utils import get_ip_address


def hack_for_jupyter(func: typing.Callable, *args, **kwargs) -> asyncio.Task:
    """From Jupyter we need this hack to deploy prefect flows"""
    coroutine = run_in_threadpool(func, *args, **kwargs)
    return asyncio.create_task(coroutine)


async def wait_for_deployment(name: str, wait=1, max_retry=30):
    """Wait for prefect deployment to be finished."""
    # Taken from prefect/cli/deployment.py::inspect
    retry = 0
    async with get_client() as client:
        while True:
            try:
                await client.read_deployment_by_name(name)
                print(f"Finished deploying prefect flow: {name!r}")
                return
            except ObjectNotFound:
                retry += 1
                if retry >= max_retry:
                    raise
                print(f"Wait for deployment of prefect flow: {name!r} ...")
                await asyncio.sleep(wait)


#
# Quickstart flow and tasks from https://docs.prefect.io/v3/get-started/quickstart
#


@flow(log_prints=True)
def flow_show_stars(github_repos: list[str], test_pip: str = None):
    """Flow: Show the number of stars that GitHub repos have"""
    logger = get_run_logger()
    logger.warning(f"Flow IP address: {get_ip_address()}")

    # Test that "pip install xxx" was run in the worker container
    if test_pip:
        importlib.import_module(test_pip)

    for repo in github_repos:
        # Call Task 1
        repo_stats = task_fetch_stats(repo)

        # Call Task 2
        stars = task_get_stars(repo_stats)

        # Print the result
        logger.warning(f"Result for repository {repo!r}: {stars} stars")


@task
def task_fetch_stats(github_repo: str):
    """Task 1: Fetch the statistics for a GitHub repo"""
    get_run_logger().warning(f"'fetch_stats' task IP address: {get_ip_address()}")
    # return httpx.get(f"https://api.github.com/repos/{github_repo}").json()
    # Mock the call to github to avoid flooding them
    return {"github_repo": github_repo, "stargazers_count": random.randint(100, 1000)}


@task
def task_get_stars(repo_stats: dict):
    """Task 2: Get the number of stars from GitHub repo statistics"""
    logger = get_run_logger()
    logger.warning(f"'get_stars' task IP address: {get_ip_address()}")
    try:
        return repo_stats["stargazers_count"]
    except KeyError:
        logger.error(
            f"'stargazers_count' not found in:\n{json.dumps(repo_stats, indent=2)}",
        )
        raise
