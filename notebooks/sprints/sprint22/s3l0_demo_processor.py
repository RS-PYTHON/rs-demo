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

"""First L0 processor"""

import ast
import copy
import os
import os.path as osp
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact
from prefect_dask import DaskTaskRunner
from pystac import Asset, Item, ItemCollection
from rs_client.rs_client import RsClient

# My local "./resources" folder contains my utility modules.
# I want to be able to use the same "from dask_utils import ..." line on both client, prefect and dask workers.
# For this, I'm updating my PYTHONPATH.
sys.path.append("./resources")
import dask_utils
import prefect_utils

# Convert the prefect blocks into environment variables for the S3 bucket and authentication.
prefect_utils.blocks_to_env_vars(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
dask_cluster_eopf_name = os.environ["DASK_CLUSTER_EOPF_NAME"]
dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = (
    dask_utils.get_existing_cluster(
        os.environ["DASK_GATEWAY_EOPF_ADDRESS"],
        dask_cluster_eopf_name,
    )
)

# Now I need to upload my local utility module that will be used by the dask tasks
dask_client_eopf.upload_file("./resources/prefect_utils.py")

# Save the caller (=the prefect) env vars and variables, to be used by the dask tasks.
# These lines of code is not called by the dask workers.
caller_env = os.environ
local_mode = prefect_utils.local_mode

# In local mode, the service URLs are hardcoded in the docker-compose file
if local_mode:
    rs_server_href = None  # not used
    rs_server_api_key = None
# In cluster mode, they are set in an environment variables
else:
    rs_server_href = os.environ["RSPY_WEBSITE"]
    rs_server_api_key = os.environ["RSPY_APIKEY"]

# TEMP: EOPF changes the number of dask workers but we want to keep the current number
# See: https://gitlab.eopf.copernicus.eu/cpm/eopf-cpm/-/issues/680
worker_count = len(dask_client_eopf.scheduler_info()["workers"])


##########################
# Prefect tasks and flow #
##########################


@flow
def s3l0_demo_processor(
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
    owner_id: str,
    collection_name: str,
    cadip_stac_filter: str,
    auxip_cql2_filter: dict,
    staging_timeout: int,
):
    """
    Prefect flow to trigger an EOPF L0 processing pipeline for CADIP and AUXIP data.

    This flow orchestrates multiple tasks to perform:
        - Data discovery on CADIP and AUXIP stations
        - Staging of the selected items into an accessible S3 location
        - Configuration generation for the EOPF processor
        - Execution of the processing logic via a Dask cluster
        - Publishing results back to a STAC catalog

    Args:
        input_config_dir (str): Directory containing base configuration templates.
        payload_file (str): File path to the payload file specifying the processor module and unit.
        output_data_dir (str): Directory where processed outputs will be written.
        owner_id (str): Owner ID used for catalog and staging operations.
        collection_name (str): Name of the target collection in the catalog.
        cadip_stac_filter (str): STAC filter for querying CADIP data.
        auxip_cql2_filter (dict): CQL2 filter used for AUXIP data querying.
        staging_timeout (int): Timeout in seconds for staging tasks to complete.

    Returns:
        None

    Raises:
        RuntimeError: If any of the following occur:
            - No CADIP data is found
            - No AUXIP data is found
            - Staging of CADIP or AUXIP data fails
            - Configuration file creation fails
            - Publishing to the catalog fails
    """
    logger = get_run_logger()

    module, processing_unit = extract_module_and_processing_unit(payload_file)
    if not module or not processing_unit:
        return

    generic_client = RsClient(
        rs_server_href,
        rs_server_api_key,
        owner_id,
        None,
    )
    auxip_client = generic_client.get_auxip_client()
    cadip_client = generic_client.get_cadip_client()
    catalog_client = generic_client.get_catalog_client()

    cadip_search_future = cadip_search.submit(
        cadip_client,
        cadip_stac_filter,
    )

    # Retrieve cql2 from processor (currently the dpr processor is not working)
    auxip_cql2_future = start_processor_dask_for_aux_search(
        module,
        processing_unit,
    )

    logger.info(f" ### CQL2 : {auxip_cql2_filter}")
    # for now, the eopf search is not working, so hard-code it
    auxip_search_future = auxip_search.submit(
        auxip_client,
        auxip_cql2_future,
        auxip_cql2_filter,
    )

    # wait for results
    cadip_data = cadip_search_future.result()
    auxip_data = auxip_search_future.result()

    # protection against a searching failure
    if not cadip_data:
        logger.error("No cadip data found")
        raise RuntimeError("No cadip data found")
    if not auxip_data:
        logger.error("No auxip data found")
        raise RuntimeError("No auxip data found")

    catalog_item_ids = []
    for item in cadip_data:
        catalog_item_ids.append(item.id)
    for item in auxip_data:
        catalog_item_ids.append(item.id)
    logger.info(f"CATALOG items: {catalog_item_ids}")

    # call the staging

    # NOTE: maybe we could init a generic RsClient object from the flow and pass it to the tasks.
    # But I think (to be confirmed) that it will be serialized/deserialized so this is not optimized.

    cadip_job_staging_monitor_task = job_staging_monitor.submit(
        rs_server_api_key,
        owner_id,
        cadip_data,
        collection_name,
        staging_timeout,
    )

    auxip_job_staging_monitor_task = job_staging_monitor.submit(
        rs_server_api_key,
        owner_id,
        auxip_data,
        collection_name,
        staging_timeout,
    )

    # wait for results
    staging_cadip_res = cadip_job_staging_monitor_task.result()
    staging_auxip_res = auxip_job_staging_monitor_task.result()

    if not staging_cadip_res or not staging_auxip_res:
        logger.error("Failed to stage all the needed files. Exiting")
        raise RuntimeError("Failed to stage all the needed files. Exiting")
    # get the staged files from the catalog
    catalog_res = ItemCollection(
        list(catalog_client.get_items(collection_name, catalog_item_ids)),
    )
    # logger.info(f"catalog_res = {catalog_res.to_dict()}")

    config_file_task = config_file.submit(
        catalog_res,
        input_config_dir,
        payload_file,
        output_data_dir,
        # Use wait_for to show arrows between tasks in prefect dashboard
        wait_for=[cadip_job_staging_monitor_task, auxip_job_staging_monitor_task],
    )

    payload_file = config_file_task.result()
    if not payload_file:
        logger.error(
            "Failed to create the configuration file nedeed by the eopf processor",
        )
        raise RuntimeError(
            "Failed to create the configuration file nedeed by the eopf processor",
        )

    # Run the EOPF task with .submit in a dask node
    eopf_result = s3l0_demo_processor_dask(
        input_config_dir,
        payload_file,
        output_data_dir,
    )

    # Call dummy catalog task
    catalog_result = publish_to_catalog.submit(
        catalog_client,
        collection_name,
        eopf_result,
        output_data_dir,
    )
    if not catalog_result.result():
        raise RuntimeError("Failed to publish to catalog")


def extract_module_and_processing_unit(payload_file: str):
    """Extract module and processing unit from the payload file."""
    logger = get_run_logger()

    with open(os.path.join("l0", "config", payload_file), "r") as file:
        payload = yaml.safe_load(file)

    workflow = payload.get("workflow", [])
    for step in workflow:
        if "name" not in step:
            continue
        module = step.get("module")
        processing_unit = step.get("processing_unit")
        if not module:
            logger.error(
                f"Missing 'module' in processor payload configuration: {step['name']}",
            )
            return None, None
        if not processing_unit:
            logger.error(
                f"Missing 'processing_unit' in processor payload configuration: {step['name']}",
            )
            return None, None
        logger.info(
            f"For {step['name']} found module: {module} and processing_unit: {processing_unit}",
        )
        return module, processing_unit

    logger.error(
        f"No processor defined in the workflow of payload file {payload_file}.",
    )
    return None, None


@task(name="job-staging-monitor")
def job_staging_monitor(
    rs_server_api_key,
    owner_id,
    data_to_be_staged,
    collection_name,
    timeout=120,
    poll_interval=2,
):
    logger = get_run_logger()
    generic_client = RsClient(
        rs_server_href,
        rs_server_api_key,
        owner_id,
        None,
    )

    staging_client = generic_client.get_staging_client()
    job_status = staging_client.run_staging(
        data_to_be_staged.to_dict(),
        collection_name,
    )

    try:
        status_type, job_identifier = job_status["status"], job_status["jobID"]
        if not job_identifier:
            logger.error("Job identifier is missing.")
            return False

        while timeout > 0 and status_type not in {"successful", "failed", "dismissed"}:
            job_status = staging_client.get_job_info(job_identifier)
            logger.info(f"job_status = {job_status}")
            status_type = job_status.get("status")
            logger.info(
                f"----- Staging job for {job_identifier}: {status_type.upper()} \n",
            )
            time.sleep(poll_interval)
            timeout -= poll_interval

    except Exception as e:
        logger.exception(f"Exception while monitoring job: {e}")
        return False

    if status_type == "successful":
        logger.info(f"----- Staging job for {job_identifier}: COMPLETED \n")
        return True
    else:
        logger.info(f"----- Staging job for {job_identifier}: FAILED \n")
        return False


@task(name="auxip-search")
def auxip_search(auxip_client, cql2_from_processor: str, cql2_hardcoded):
    """Auxip search."""
    logger = get_run_logger()
    logger.info("Start auxip search.")

    logger.info(f"CQL2 from processor : {cql2_from_processor}")

    cql2 = cql2_hardcoded

    try:
        found = auxip_client.search(
            method="POST",
            stac_filter=cql2.get("filter"),
            max_items=cql2.get("limit"),
            sortby=cql2.get("sortby"),
        )
        logger.info(f"Auxip Client search found: {len(found)} results")
    except Exception as e:
        logger.error("An error occurred in auxip_search: %s", e)
        return {}

    logger.info("End auxip search.")
    return found


@task(name="cadip-search")
def cadip_search(
    cadip_client,
    cadip_filter: str,
):
    """Cadip search."""
    logger = get_run_logger()
    logger.info("Start cadip search")

    try:
        found = cadip_client.search(method="GET", stac_filter=cadip_filter)
        logger.info(f"Cadip Client search found: {len(found)} results")

    except Exception as e:
        logger.error("An error occurred in cadip_search: %s", e)
        return {}

    logger.info("End cadip search")
    return found


@task(name="config-file")
async def config_file(
    items_list,
    input_config_dir,
    payload_file,
    output_data_dir,
):
    """Config file writing for the processor"""

    logger = get_run_logger()
    logger.info("Start config file")

    # Read the payload file from the local config directory
    local_payload_path = os.path.join("l0", "config", payload_file)
    try:
        with open(local_payload_path, "r", encoding="utf-8") as f:
            try:
                payload = yaml.safe_load(f)
            except yaml.YAMLError as ye:
                logger.error(f"Error parsing YAML file {local_payload_path}: {ye}")
                return False
    except FileNotFoundError as fnf_error:
        logger.error(f"Payload file not found at {local_payload_path}: {fnf_error}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error reading {local_payload_path}: {e}")
        return False

    # Retrieve a default template from the existing input_products if available;
    # otherwise, use a minimal default.
    if payload.get("I/O", {}).get("input_products"):
        default_template = copy.deepcopy(payload["I/O"]["input_products"][0])
    else:
        default_template = {"id": None, "path": None}

    # Retrieve a default template from the existing output_products if available;
    # otherwise, use a minimal default.
    if payload.get("I/O", {}).get("output_products"):
        default_template_out = copy.deepcopy(payload["I/O"]["output_products"][0])
    else:
        default_template_out = {"id": None, "path": None}
    output_ids = {}
    try:
        for wf in payload.get("workflow", []):
            outputs = wf.get("outputs", {})
            if outputs:
                # Merge outputs from all workflows; keys are not used here, only the values (output IDs)
                output_ids.update(outputs)
            else:
                logger.error(f"At least on output should be in outputs workflow")
                return False
    except Exception as e:
        logger.error(f"Missing outputs in workflow when reading payload structure: {e}")
        return False

    new_input_products = []
    workflow_inputs = {}
    cadip_index = 1
    auxip_index = 1

    logger.info(f"Items from CATALOG: {items_list}")

    # For each staged item in the catalog collection
    for item in items_list:
        if len(item.assets) == 0:
            logger.error(f"Fatal: there are no assets in item {item.id}")
            return False
        try:
            first_asset = list(item.assets.items())[0][1]
            logger.info(f"first_asset = {first_asset}")
            full_s3_href = (
                first_asset.extra_fields.get("alternate", {}).get("s3", {}).get("href")
            )
            if full_s3_href:
                session_s3_href = "/".join(full_s3_href.split("/")[:-1])
                logger.info(f"Session {item.id} has S3_HREF: {session_s3_href}")

                # Create a new input product using the default template.
                new_product = copy.deepcopy(default_template)
                new_product["id"] = item.id
                new_product["path"] = session_s3_href

                if "cadip:id" in item.properties:
                    new_product["store_type"] = "cadu"
                if "auxip:id" in item.properties:
                    new_product["store_type"] = "aux"

                new_input_products.append(new_product)

                if "cadip:id" in item.properties:
                    workflow_inputs[f"CADU{cadip_index}"] = item.id
                    cadip_index += 1
                if "auxip:id" in item.properties:
                    workflow_inputs[f"AUX{auxip_index}"] = item.id
                    auxip_index += 1
            else:
                logger.error(f"S3 HREF not found in extra fields for item {item.id}")
                return False
        except KeyError as ke:
            logger.error(
                f"Failed to load from item {item.id}. The key {ke} is missing from the dictionary.",
            )
            return False
        except Exception as e:
            logger.error(f"Unexpected error processing item {item.id}: {e}")
            return False

    # Build a new output_products list using the default template for each output
    new_output_products = []
    for key, output_id in output_ids.items():
        # Create a new entry from the default template
        product_entry = copy.deepcopy(default_template_out)
        # Update the id and path accordingly
        product_entry["id"] = output_id
        product_entry["path"] = f"{output_data_dir}"  # with /{output_id} ?
        new_output_products.append(product_entry)

    # Update payload with new input products and workflow inputs
    try:
        payload["I/O"]["input_products"] = new_input_products
        for wf in payload.get("workflow", []):
            wf["inputs"] = workflow_inputs
        payload["I/O"]["output_products"] = new_output_products
    except Exception as e:
        logger.error(f"Error updating payload structure: {e}")
        return False

    # Write back the payload contents
    try:
        with open(local_payload_path, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.error(f"Error writing to file {local_payload_path}: {e}")
        return False

    try:
        with open(local_payload_path, "r", encoding="utf-8") as f:
            payload_after = f.read()
        logger.info("Payload file AFTER config_file:\n" + payload_after)
    except Exception as e:
        logger.error(f"Error reading back the file {local_payload_path}: {e}")
        return False

    # Upload the new config payload file back to S3
    new_payload_file = osp.join(
        osp.dirname(payload_file),
        "s3_l0_demo_payload_dpr_mockup_run.yaml",
    )
    s3_payload_path = f"{input_config_dir}/{new_payload_file}"
    try:
        await prefect_utils.s3_upload_file(local_payload_path, s3_payload_path)
    except Exception as e:
        logger.error(f"Error uploading file to S3 ({s3_payload_path}): {e}")
        return False

    logger.info("End config file")
    return new_payload_file


@task(name="publish-to-catalog")
def publish_to_catalog(catalog_client, collection_name, eopf_result, output_data_dir):
    """Dummy catalog call to save results"""
    logger = get_run_logger()
    logger.info("Start catalog saving")
    # logger.info(f"eopf_result = {eopf_result}")
    # eopf_features = []
    try:
        for feature_dict in eopf_result:
            item = Item(
                id=feature_dict["stac_discovery"]["id"],
                geometry=feature_dict["stac_discovery"]["geometry"],
                bbox=feature_dict["stac_discovery"]["bbox"],
                datetime=datetime.fromisoformat(
                    feature_dict["stac_discovery"]["properties"]["datetime"],
                ),
                properties=feature_dict["stac_discovery"]["properties"],
            )
            asset = Asset(href=f"{output_data_dir}/{item.id}.zarr.zip")
            item.assets = {f"{item.id}.zarr.zip": asset}
            catalog_client.add_item(collection_name, item)
    except Exception as e:
        logger.error(f"Exception in publishing to catalog: {e}")
        return False
    # items = [Item(**eopf_feature) for eopf_feature in eopf_features]
    # for item in items:
    # for asset in item.assets:
    #    logger.info(f" asset  : {asset}")
    #    item.assets[asset].href = f"{output_data_dir}/{item.id}.zarr"
    #    logger.info(f" Updated Item  : {item.to_dict()}")
    # catalog_client.add_item(collection_name, item)

    collections = catalog_client.get_collections()
    logger.info(f"\nCollections response:")
    for collection in collections:
        logger.info(f"ID: {collection.id}, Title: {collection.title}")

    logger.info(f"End catalog saving:")
    return True


#######################
# Dask tasks and flow #
#######################
@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster_eopf.scheduler_address,
        client_kwargs={"security": dask_cluster_eopf.security},
    ),
)
def start_processor_dask_for_aux_search(
    module: str,
    processing_unit: str,
):
    """
    Dask flow used to call tasks in dask workers.
    Used only to retrieve CQL2 filter from processor.
    """
    result = eopf_aux_data_search.submit(module, processing_unit)
    return result


@task(name="eopf-aux-data-search")
async def eopf_aux_data_search(
    module: str,
    processing_unit: str,
):
    """
    Retrieve CQL2 filter.
    See https://gitlab.eopf.copernicus.eu/cpm/eopf-cpm/-/blob/main/docs/source/processor-orchestration-guide/tasktables.rst
    """
    logger = get_run_logger()

    logger.info(
        f" Retrieve CQL2 filter for module : {module}, processing_unit : {processing_unit}",
    )

    command = ["eopf", "trigger", "tasktable", module, processing_unit]
    result = {}
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e.stderr}")

    # auxip_cql2_filter hardcoded value of CQL2 filter is used until the L0 V1 is ready
    return result


#######################
@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster_eopf.scheduler_address,
        client_kwargs={"security": dask_cluster_eopf.security},
    ),
)
def s3l0_demo_processor_dask(
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    """
    Dask flow used to call tasks in dask workers.
    """
    return main_dask_task.submit(
        input_config_dir,
        payload_file,
        output_data_dir,
    )


@task(name="eopf-dask-task")
async def main_dask_task(
    input_config_dir: str,
    payload_file: str,
    output_data_dir: str,
):
    # NOTE: not sure this is useful so I'm removing it
    # with worker_client(separate_thread=False)

    logger = get_run_logger()

    # Output report dir
    report_dirname = "reports"

    # Use env vars from the caller
    for key in [
        "S3_ACCESSKEY",
        "S3_SECRETKEY",
        "S3_ENDPOINT",
        "S3_REGION",
        "S3_BUCKET_NAME",
        "S3_BUCKET_FOLDER",
        "DASK_GATEWAY_EOPF_ADDRESS",
        "DASK_CLUSTER_EOPF_NAME",
        "AWS_REQUEST_CHECKSUM_CALCULATION",
        "AWS_RESPONSE_CHECKSUM_VALIDATION",
    ] + (
        ["LOCAL_DASK_USERNAME", "LOCAL_DASK_PASSWORD"]
        if local_mode
        else ["JUPYTERHUB_API_TOKEN"]
    ):
        os.environ[key] = caller_env[key]

    # Also save the given output dir as an env var
    os.environ["OUTPUT_DIR"] = output_data_dir

    # Payload parent dir and filename
    payload_dir = osp.dirname(payload_file)
    payload_name = osp.basename(payload_file)

    logger.info(f"payload_file = {payload_file}")
    logger.info(f"payload_dir = {payload_dir}")
    logger.info(f"payload_name = {payload_name}")

    # Download the input config dir locally
    # NOTE: maybe we should only download the payload file + only necessary config files
    # rather than the whole directory.
    local_config_dir = "config"
    payload_abs_path = osp.join("/", os.getcwd(), local_config_dir, payload_file)
    logger.info(f"payload_abs_path = {payload_abs_path}")
    await prefect_utils.s3_download_dir(input_config_dir, local_config_dir)

    # Change working directory
    os.chdir(osp.join(local_config_dir, payload_dir))

    # Create the reports dir
    os.makedirs(report_dirname, exist_ok=True)

    # Trigger EOPF processing, catch output
    p = subprocess.Popen(
        ["python3.11", "DPR_processor_mock.py", "-p", payload_abs_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd="/src/DPR",
    )

    # Log contents
    log_str = ""
    return_response = {}
    # Write output to a log file and string + redirect to the prefect logger
    with open(
        osp.join(report_dirname, Path(payload_file).with_suffix(".log").name),
        "w+",
    ) as log_file:
        while (line := p.stdout.readline()) != "":

            # The log prints password in clear e.g 'key': '<my-secret>'... hide them with a regex
            for key in (
                "key",
                "secret",
                "endpoint_url",
                "region_name",
                "api_token",
                "password",
            ):
                line = re.sub(rf"(\W{key}\W)[^,}}]*", r"\1: ***", line)

            # Write to log file and string
            log_file.write(line)
            log_str += line

            # Write to prefect logger if not empty
            line = line.rstrip()
            if line:
                logger.info(line)

        logger.info(f"log_str = {log_str}")
        # search for the JSON-like part, parse it, and ignore the rest.
        match = re.search(r"(\[\s*\{.*\}\s*\])", log_str, re.DOTALL)
        if not match:
            raise ValueError("No valid data structure found in the output.")

        payload_str = match.group(1)

        # Use `ast.literal_eval` to safely evaluate the structure
        try:
            # payload_str is a string that looks like a JSON, extracted from the dpr mockup's raw output.
            # ast.literal_eval() parses that string and returns the actual Python object (not just the string).
            return_response = ast.literal_eval(payload_str)
        except Exception as e:
            raise ValueError(f"Failed to parse data structure: {e}")

    try:
        # Wait for the execution to finish
        status_code = p.wait()

        # Raise exception if the status code is != 0
        if status_code:
            raise Exception("EOPF error, please see the log.")

    # In all cases, upload the reports dir to the s3 bucket.
    finally:
        try:
            await prefect_utils.s3_upload_dir(
                report_dirname,
                osp.join(output_data_dir, report_dirname),
            )
        except Exception as exception:
            logger.error(exception)

        # Save log str into a markdown artifact
        create_markdown_artifact(
            key="logging",
            markdown=f"```\n{log_str}\n```",
            description="L0 processing logging",
        )

    # Dummy output for prefect
    return return_response
