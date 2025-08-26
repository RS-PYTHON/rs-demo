import datetime
import time

import rs_client
from prefect import flow, get_run_logger
from rs_workflows.flow_utils import FlowEnv, FlowEnvArgs
from rs_workflows.record_flow_run import record_flow_run


@flow(name="record_flow_")
async def record_flow(
    env: FlowEnvArgs,
    flow_run_type: str = "systematic",
    mission: str = "sentinel-1",
    dpr_processor_name: str = "dpr_processor",
    dpr_processor_version: str = "dpr_processor_version",
    dpr_processor_unit: str = "dpr_processor_unit",
    dpr_processing_input_stac_items: str = "{'dpr_processing_input_stac_items': 'value'}",
):

    logger = get_run_logger()

    flow_env = FlowEnv(env)
    with flow_env.start_span(__name__, "init-pi-database"):
        record_flow_run.fn(start_date=datetime.datetime.now(), status="OK")

        logger.info("=== Flow started ===")
        logger.info(f"flow_run_type = {flow_run_type}")
        logger.info(f"mission = {mission}")
        logger.info(f"dpr_processor_name = {dpr_processor_name}")
        logger.info(f"dpr_processor_version = {dpr_processor_version}")
        logger.info(f"dpr_processor_unit = {dpr_processor_unit}")
        logger.info(
            f"dpr_processing_input_stac_items = {dpr_processing_input_stac_items}",
        )

        logger.info("Sleeping 10 seconds...")
        time.sleep(10)
        record_flow_run.fn(stop_date=datetime.datetime.now(), status="OK")
        logger.info("=== Flow finished ===")
