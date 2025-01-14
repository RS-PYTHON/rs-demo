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
from prefect import flow, get_run_logger, task
import json
from rs_client.staging_client import StagingClient

@task
def get_jobs(idx):
    """Example task to be used in a prefect flow
    The function simply multiplies two numbers
    This prefect task may be used as start point in creating your own prefect tasks

    Args:
        idx (int): Index of the task
        x (int): First operator
        y (int): Second operator
    """
    logger = get_run_logger()
    logger.info(f"Running task get_jobs index {idx}")
    try:
        rs_client_staging = StagingClient(os.environ["RS_SERVER_STAGING_ADDRESS"], 
                                          os.environ["RS_API_KEY"], 
                                          os.environ["RS_OWNER"], None)
    except KeyError:
        logger.exception(
            "Failed to retrieve the address for the rs-server-staging. No RS_SERVER_STAGING_ADDRESS env var found"
            )
        return "FAILED"
    response = rs_client_staging.get_jobs()
    resp = json.loads(response.content)
    logger.info(f"{resp}")
    return "OK"
    

@flow(name="get_staging_jobs")
def get_staging_jobs():    
    # Prefect flow and task definitions    
    
    
    """Example flow that will be launched to run in a dask cluster

    This prefect flow may be used as start point in creating your own prefect flows. It runs in parallel
    add_numbers and multiply_numbers tasks

    Args:
        name (str): Username to be printed. Default COPERNICUS
        number_of_tasks (int): Number of tasks to be run. Default 5
    """
    logger = get_run_logger()
    logger.info("Running flow get_staging_jobs")
    res = get_jobs.submit(1)
    
    logger.info(f"Task retunrned {res.result()}")    
    

get_staging_jobs()
