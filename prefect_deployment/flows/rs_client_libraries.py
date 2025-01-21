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
""" Module that implements a prefect flow that is launched in a prefect worker """
import json
import os

from prefect import flow, get_run_logger, task
from rs_client.staging_client import StagingClient


@task
def get_jobs():
    """Example task to be used in a prefect flow
    This prefect task may be used as start point in creating your own prefect tasks. It creates
    the rs-client-staging object used to call the rs-server-staging get_jobs endpoint only

    Args:
        None
    """
    logger = get_run_logger()
    logger.info("Running task get_jobs ")
    try:
        rs_client_staging = StagingClient(
            os.environ["RS_SERVER_STAGING_ADDRESS"],
            os.environ["RS_API_KEY"],
            os.environ["RS_OWNER"],
            None,
        )
    except KeyError:
        logger.exception(
            "Failed to retrieve the address for the rs-server-staging. No RS_SERVER_STAGING_ADDRESS env var found",
        )
        return "FAILED"
    response = rs_client_staging.get_jobs()

    resp = json.loads(response.content)
    logger.info(f"{resp}")
    return "OK"


@flow(name="get_staging_jobs")
def get_staging_jobs():
    # Prefect flow and task definitions

    """Flow that will be launched in a prefect worker

    This prefect flow may be used as start point in creating your own prefect flows. It runs
    a task that creates the rs-client-staging object used to call the rs-server-staging endpoints
    Args:
        None
    """
    logger = get_run_logger()
    logger.info("Running flow get_staging_jobs")
    res = get_jobs.submit()

    logger.info(f"Task retunrned {res.result()}")


get_staging_jobs()
