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

"""Utility Python module for the tutorials.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

import json
import logging
import os
import pprint
import time
from datetime import datetime
from time import sleep
from typing import Optional

import boto3
import requests
import rs_common
from pystac import (
    Asset,
    Collection,
    Extent,
    Item,
    ItemCollection,
    SpatialExtent,
    TemporalExtent,
)
from pystac_client import CollectionClient
from pystac_client.item_search import DatetimeLike
from resources.prefect_utils import init_prefect_blocks
from rs_client.auxip_client import AuxipClient
from rs_client.cadip_client import CadipClient
from rs_client.catalog_client import CatalogClient
from rs_client.rs_client import RsClient
from rs_client.staging_client import StagingClient
from rs_common.config import EAuxipStation, ECadipStation

# Variables
# Set logger level to info
rs_common.logging.Logging.level = logging.INFO

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

# Is this code run from the ci/cd or manually ? By default: manually.
from_cicd: bool = os.getenv("RSPY_FROM_CICD") == "1"

# In cluster mode, you need an API key to access the RS-Server services.
apikey: str | None = None

# "headers" field with the api key for HTTP requests
apikey_headers: dict = {}

# Client instances
auxip_client: AuxipClient = None
cadip_client: CadipClient = None
catalog_client: CatalogClient = None
staging_client: StagingClient = None

# HTTP request session
http_session: requests.Session = requests.Session()

# We use these bucket names that are deployed on the cluster.
# RS-Server has read/write access to these buckets, but as an end-user, you won't manipulate them directly.
# Except in local mode, where we use a local MinIO object storage instance.
# We need to manually create the buckets.
RSPY_TEMP_BUCKET = os.environ["RSPY_TEMP_BUCKET"]
RSPY_CATALOG_BUCKET = os.environ["RSPY_CATALOG_BUCKET"]

# For local mode only
if local_mode:

    # Username
    RSPY_HOST_USER = os.environ["RSPY_HOST_USER"]

    # Share data between the user, the client (jupyter or terminal) and prefect
    PREFECT_SHARE_BUCKET = os.environ["PREFECT_SHARE_BUCKET"]

OWNER_ID = os.environ["JUPYTERHUB_USER"] if cluster_mode else RSPY_HOST_USER

# STAC catalog sample collection name
TEST_COLLECTION: str = "my_test_collection"

# Define a search interval
start_date = datetime(2000, 1, 1)
stop_date = datetime(2030, 1, 1)

#
# Functions


def pretty_print(any_dict: dict, indent=2):
    """Pretty print any dict e.g. JSON data."""
    print(json.dumps(any_dict, indent=2))


def read_apikey() -> None:
    """
    Read the API key, either from the environment variable or from an interactive input form.

    NOTE: don't return the apikey value because there is a risk that it is displayed in the
    notebook (if this function is called from the last cell line) so this is not secured.
    """
    global apikey, apikey_headers

    # No API key in local mode
    if local_mode:
        return

    # In cluster mode, read it from the user input
    if not apikey:
        import getpass

        apikey = getpass.getpass(f"Enter your API key:")
        os.environ["RSPY_APIKEY"] = apikey

    # Set the header to use in HTTP requests
    apikey_headers = {"headers": {"x-api-key": apikey}}


def get_s3_client():
    """
    Return a boto3 s3 client from the
    S3_ACCESSKEY, S3_SECRETKEY, S3_ENDPOINT, S3_REGION environment variables.
    """
    s3_session = boto3.session.Session()
    return s3_session.client(
        service_name="s3",
        aws_access_key_id=os.environ["S3_ACCESSKEY"],
        aws_secret_access_key=os.environ["S3_SECRETKEY"],
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ["S3_REGION"],
    )


def create_s3_buckets():
    """In local mode only: create the s3 buckets, if they do not already exists."""
    if not local_mode:
        return
    s3_client = get_s3_client()
    for bucket in RSPY_TEMP_BUCKET, RSPY_CATALOG_BUCKET, PREFECT_SHARE_BUCKET:
        try:
            s3_client.create_bucket(Bucket=bucket)
        except (
            s3_client.exceptions.BucketAlreadyExists,
            s3_client.exceptions.BucketAlreadyOwnedByYou,
        ):
            pass  # do nothing if already exists


def init_rsclient(
    owner_id=None,
    cadip_station: str | ECadipStation = "CADIP",
    adgs_station: str | EAuxipStation = "ADGS",
):
    """Init RsClient instances"""
    global apikey, auxip_client, cadip_client, catalog_client, staging_client

    # In local mode, the service URLs are hardcoded in the docker-compose file
    if local_mode:
        rs_server_href = None  # not used
    # In cluster mode, they are set in an environment variables
    else:
        rs_server_href = os.environ["RSPY_WEBSITE"]
    # Init a generic RS-Client instance. Pass the:
    #   - RS-Server website URL
    #   - API key
    #   - ID of the owner of the STAC catalog collections.
    #     By default, this is the user login from the keycloak account, associated to the API key.
    #     Or, in local mode, this is the local system username.
    #     Else, your API Key must give you the rights to read/write on this catalog owner (see next cell).
    #   - Logger (optional, a default one can be used)
    generic_client = RsClient(
        rs_server_href,
        rs_server_api_key=apikey,
        owner_id=owner_id,
        logger=None,
    )

    # From this generic instance, get an Auxip client instance
    auxip_client = generic_client.get_auxip_client(adgs_station)

    # Or get a Cadip client instance. Pass the cadip station.
    cadip_client = generic_client.get_cadip_client(cadip_station)

    # Or get a Stac client to access the catalog
    catalog_client = generic_client.get_catalog_client()

    # Create a client to launch staging
    staging_client = generic_client.get_staging_client()

    print(f"Auxip service: {auxip_client.href_service}")
    print(f"CADIP service: {cadip_client.href_service}")
    print(f"Catalog service: {catalog_client.href_service}")
    print(f"Staging service: {staging_client.href_service}")

    return auxip_client, cadip_client, catalog_client, staging_client


def create_test_collection(collection_id=None) -> CollectionClient:
    """Create and return a test STAC collection"""

    if not collection_id:
        collection_id = TEST_COLLECTION
    # Clean the existing collection, if any
    catalog_client.remove_collection(collection_id)

    # Add new collection
    response = catalog_client.add_collection(
        Collection(
            id=collection_id,
            description=None,  # rs-client will provide a default description for us
            extent=Extent(
                spatial=SpatialExtent(bboxes=[-180.0, -90.0, 180.0, 90.0]),
                temporal=TemporalExtent([start_date, stop_date]),
            ),
        ),
    )
    response.raise_for_status()

    # Return the inserted collection
    inserted_collection = catalog_client.get_collection(collection_id=collection_id)
    assert inserted_collection, "Collection was not inserted"
    return inserted_collection


def truncate_features_by_limit(item_collection, limit):
    """Truncate a response from a station to a limit of files"""
    # Load the dictionary from the file

    total_count = 0  # To keep track of the global count of assets
    truncated_features = []
    truncated_dict = item_collection.to_dict()

    for feature in truncated_dict["features"]:
        assets = feature.get("assets", {})
        asset_count = len(assets)

        if total_count + asset_count <= limit:
            total_count += asset_count
            truncated_features.append(feature)
        else:
            # Truncate assets in the current feature
            allowed_assets = limit - total_count
            feature["assets"] = dict(list(assets.items())[:allowed_assets])
            truncated_features.append(feature)
            break
    # Update the dictionary with the truncated features
    truncated_dict["features"] = truncated_features
    return ItemCollection.from_dict(truncated_dict)


def stage_test_objects(
    client,
    nb_of_objects,
    collection_id=None,
    objects_are_files=True,
    timestamp: Optional[DatetimeLike] = None,
):
    """Stage several files from cadip or auxip into the STAC catalog and return it."""

    catalog_collection_name = collection_id if collection_id else TEST_COLLECTION

    # The search method is based on a time interval
    item_collection = client.search(
        timestamp=timestamp if timestamp else [start_date, stop_date],
        max_items=nb_of_objects,
    )

    assert isinstance(item_collection, ItemCollection)
    if objects_are_files:
        # truncate by number of files. In cadip case, the items are sessions which have more than one file
        item_collection = truncate_features_by_limit(item_collection, nb_of_objects)
    items_id = [item.id for item in item_collection]
    # Start the staging process. The catalog collection is either
    # provided, or the test collection created from create_test_collection() is used
    job_id = staging_client.run_staging(
        item_collection.to_dict(),
        catalog_collection_name,
    )
    timeout = 120
    while timeout > 0:
        if "running" not in job_id["status"]:
            break
        # TODO: to replace with the following commented line after the rs-server-staging update
        ###job_info = staging_client.get_job_info(resp["jobID"])
        job_info = staging_client.get_job_info(job_id["status"]["running"])
        pprint.PrettyPrinter(indent=4).pprint(job_info)
        print("\n")
        if "successful" in job_info["status"]:
            print(" ----- Job COMPLETED \n")
            time.sleep(0.5)
            return ItemCollection(
                list(catalog_client.get_items(catalog_collection_name, items_id)),
            )
        if "failed" in job_info["status"]:
            print("-----Job FAILED \n")
            break
        time.sleep(2)
        timeout -= 2

    return None


def temporary_fix_adgs_feature(items_collection):
    # Disable instruments for moment
    for feature in items_collection["features"]:
        if "instruments" in feature["properties"]:
            del feature["properties"]["instruments"]
    # Update href and title
    for feature in items_collection["features"]:
        for asset in feature["assets"]:
            feature["assets"][asset]["title"] = asset
            feature["assets"][asset][
                "href"
            ] = f"http://mockup-station-adgs.processing.svc.cluster.local:8080/Products({feature['properties']['auxip:id']})/$value"
    return items_collection


########
# Init #
########


def init_demo(owner_id=None, cadip_station: str | ECadipStation = "CADIP"):
    """Init environment before running a demo notebook."""

    # Some kind of workaround for boto3 to avoid checksum being added inside
    # the file contents uploaded to the s3 bucket e.g. x-amz-checksum-crc32:xxx
    # See: https://github.com/boto/boto3/issues/4435
    os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
    os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "when_required"

    # In local mode, create the s3 buckets, if they do not already exists
    if local_mode:
        create_s3_buckets()

    # Init the prefect blocks.
    # In local mode: create them. In cluster mode: read them.
    init_prefect_blocks(_sync=True)

    # Set OAuth2 authentication in the http request session
    if cluster_mode:
        http_session.cookies.set("session", os.environ["RSPY_OAUTH2_COOKIE"])

    # Default owner_id
    if not owner_id:
        owner_id = OWNER_ID

    # Init RsClient instances
    ret = init_rsclient(owner_id, cadip_station)

    # Save the local mode dask authentication in the staging
    if local_mode:
        http_session.post(
            f"{staging_client.href_service}/staging/dask/auth",
            params={
                "local_dask_username": os.environ["LOCAL_DASK_USERNAME"],
                "local_dask_password": os.environ["LOCAL_DASK_PASSWORD"],
            },
        )

    return ret
