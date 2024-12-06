from prefect import flow, task


@flow(name="staging")
def staging():
    print("Launch staging flow...")

@flow(name="staging_local")
def staging_local():
    """
    Launch staging process
    """
    
    # Do necessary imports for this flow
    import getpass
    import os
    import pprint
    import sys
    from datetime import datetime
    from typing import Any

    import boto3
    import botocore
    import requests
    from pystac import Collection, Extent, SpatialExtent, TemporalExtent

    from rs_client.rs_client import RsClient
    from rs_common.config import ECadipStation
    from rs_common.logging import Logging
    pp = pprint.PrettyPrinter(indent=2, width=80, sort_dicts=False, compact=True)

    from rs_workflows.new_staging import RsStagingClient

    from dotenv import load_dotenv
    
    
    # Loading environment variables
    load_dotenv()

    # staging.run_staging()
    print("Launch staging flow...")
    
    TIMEOUT = 10
    CATALOG_BUCKET = "rs-cluster-catalog"
    APIKEY_HEADER = "x-api-key"
    COLLECTION_ID = "cadip_s1A"
    STAC_OUTPUT_COLL_NAME = "cadip_s1A_staged"
    APIKEY_VALUE = None  # "x-api-key" ### TODO: get apikey from frontend page
    APIKEY_HEADERS: dict = {"headers": {APIKEY_HEADER: APIKEY_VALUE}} if APIKEY_VALUE else {}
    user = os.getenv("RSPY_HOST_USER", default=getpass.getuser())
    local_mode = os.getenv("RSPY_LOCAL_MODE") == "1"
    rs_server_href = "" if local_mode else os.getenv("RSPY_WEBSITE")

    # Get client instances from the generic client
    generic_client = RsClient(
        rs_server_href,
        rs_server_api_key=APIKEY_VALUE,
        owner_id=user,
        logger=None,
    )
    stac_client = generic_client.get_stac_client()
    cadip_station = ECadipStation.CADIP  # you can also have: INS, MPS, MTI, NSG, SGS
    cadip_client = generic_client.get_cadip_client(cadip_station)
    logger = Logging.default(__name__)

    # ----- Step 1 - Create the output STAC collection if it doesn't alredy exists
    logger.info(f"Creating a new collection {STAC_OUTPUT_COLL_NAME} in the STAC catalog...")
    try:
        create_coll_response = stac_client.get_collection(STAC_OUTPUT_COLL_NAME)
        logger.info(
            f"Collection {STAC_OUTPUT_COLL_NAME} already exists -> staging process will use the existing one",
        )
    except: # pylint: disable=bare-except
        create_coll_response = stac_client.add_collection(
            Collection(
                id=STAC_OUTPUT_COLL_NAME,
                description=None,  # rs-client will provide a default description for us
                extent=Extent(
                    spatial=SpatialExtent(bboxes=[-180.0, -90.0, 180.0, 90.0]),
                    temporal=TemporalExtent(
                        [datetime(2000, 1, 1), datetime(2030, 1, 1)],
                    ),
                ),
            ),
        )
        logger.info(
            f"Resp status: {create_coll_response.status_code} | Message: {create_coll_response.reason}",
        )

    # ----- Step 2 - Create a bucket to store staged data
    PREFIX = "stream/"
    s3_session = boto3.session.Session()
    s3_client = s3_session.client(
        service_name="s3",
        aws_access_key_id=os.environ["S3_ACCESSKEY"],
        aws_secret_access_key=os.environ["S3_SECRETKEY"],
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ["S3_REGION"],
    )
    try:
        s3_client.head_bucket(Bucket=CATALOG_BUCKET)
        logger.info(f"The bucket {CATALOG_BUCKET} already exists")
    except botocore.client.ClientError as error:
        if int(error.response["Error"]["Code"]) == 404:
            try:
                s3_client.create_bucket(Bucket=CATALOG_BUCKET)
            except botocore.exceptions.ClientError as e:
                logger.info(f"Bucket CATALOG_BUCKET error: {e}")
                sys.exit(-1)
        else:
            logger.info("PANIC: Could not get bucket info. Exiting")
            sys.exit(-1)
    # Delete all existing objects from rs-server-catalog
    if PREFIX:
        response = s3_client.list_objects_v2(Bucket=CATALOG_BUCKET, Prefix=PREFIX)
        if response.get("Contents", None):
            for elem in response["Contents"]:
                logger.info(f"Deleting {elem['Key']}")
                s3_client.delete_object(Bucket=CATALOG_BUCKET, Key=elem["Key"])

    # Apply a request to get information about sessions that you want to stage
    session = requests.Session()
    search_result = session.get(f"{os.getenv('RSPY_HOST_CADIP')}/cadip/collections/{COLLECTION_ID}/items").json()
    
    # Create necessary clients to perform catalog search and staging opeation
    staging_client = RsStagingClient()
    
    
    # Launch staging process
    staging_client.run_staging(APIKEY_HEADERS, search_result, STAC_OUTPUT_COLL_NAME, TIMEOUT)

    # Check created sessions 
    result = session.get(f"{os.getenv('RSPY_HOST_CATALOG')}/catalog/collections/{STAC_OUTPUT_COLL_NAME}/items")
    catalog_collection = result.json()
    assert catalog_collection.get("type") == "FeatureCollection"
    assert len(catalog_collection.get("features")) == 4
    for item in catalog_collection.get("features"):
        print(f"Item {item.get('id')} has {len(item.get('assets'))} assets") 
    
    # Delete the whole collection
    logger.info("Deleting the collection...")
    result = session.delete(f"{os.getenv('RSPY_HOST_CATALOG')}/catalog/collections/{STAC_OUTPUT_COLL_NAME}")
    assert result.json()["deleted collection"] == STAC_OUTPUT_COLL_NAME
    pp.pprint(result.json())
    


#if __name__ == "__main__":
    # Creates a deployment from your flow and immediately begins listening for scheduled runs to execute
    # staging.serve(name="my-first-deployment", cron="* * * * *")

    # Create a deployment: here’s an example of a deployment that uses a work pool and bakes the code into a Docker image
    # staging.deploy(
    #     name="my-second-deployment",
    #     work_pool_name="my-work-pool",
    #     image="my-image",
    #     push=False,
    #     cron="* * * * *",
    # )