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
import socket
import typing

import httpx
from fastapi.concurrency import run_in_threadpool
from prefect import flow, get_run_logger, task


def get_ip_address() -> str:
    """Return IP address, see: https://stackoverflow.com/a/166520"""
    return socket.gethostbyname(socket.gethostname())


def hack_for_jupyter(func: typing.Callable, *args, **kwargs) -> asyncio.Task:
    """From Jupyter we need this hack to deploy prefect flows"""
    coroutine = run_in_threadpool(func, *args, **kwargs)
    return asyncio.create_task(coroutine)


@flow(log_prints=True)
def flow_show_stars(github_repos: list[str]):
    """Flow: Show the number of stars that GitHub repos have"""
    logger = get_run_logger()
    logger.warning(f"Flow IP address: {get_ip_address()}")

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
    return httpx.get(f"https://api.github.com/repos/{github_repo}").json()


@task
def task_get_stars(repo_stats: dict):
    """Task 2: Get the number of stars from GitHub repo statistics"""
    get_run_logger().warning(f"'get_stars' task IP address: {get_ip_address()}")
    return repo_stats["stargazers_count"]
