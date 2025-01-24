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
from datetime import datetime
from time import sleep

import boto3
import requests
import rs_common
from dask_gateway import Gateway
from dask_gateway.client import GatewayCluster
from distributed.client import Client as DaskClient
from prefect.filesystems import RemoteFileSystem
from pystac import Asset, Collection, Extent, Item, SpatialExtent, TemporalExtent
from pystac_client import CollectionClient
from rs_client.auxip_client import AuxipClient
from rs_client.cadip_client import CadipClient
from rs_client.rs_client import RsClient
from rs_client.stac_client import StacClient
from rs_common.config import ECadipStation, EDownloadStatus

#
# Variables

# Set logger level to info
rs_common.logging.Logging.level = logging.INFO

# In local mode, all your services are running locally.
# In cluster mode, we use the services deployed on the RS-Server website.
# This configuration is set in an environment variable.
local_mode: bool = os.getenv("RSPY_LOCAL_MODE") == "1"
cluster_mode: bool = not local_mode

# In cluster mode, you need an API key to access the RS-Server services.
apikey: str | None = None

# "headers" field with the api key for HTTP requests
apikey_headers: dict = {}

# RsClient instances
auxip_client: AuxipClient = None
cadip_client: CadipClient = None
stac_client: StacClient = None

# HTTP request session
http_session: requests.Session = requests.Session()

# We use these bucket names that are deployed on the cluster.
# RS-Server has read/write access to these buckets, but as an end-user, you won't manipulate them directly.
# Except in local mode, where we use a local MinIO object storage instance.
# We need to manually create the buckets.
RSPY_TEMP_BUCKET = os.environ["RSPY_TEMP_BUCKET"]
RSPY_CATALOG_BUCKET = os.environ["RSPY_CATALOG_BUCKET"]

# This one is for sharing data between the user, the client (jupyter or terminal) and prefect
PREFECT_SHARE_BUCKET = os.environ["PREFECT_SHARE_BUCKET"]
# Associated prefect block
S3_BLOCK: RemoteFileSystem = None

PREFECT_WORK_POOL = os.environ["PREFECT_WORK_POOL"]

# STAC catalog sample collection name
TEST_COLLECTION: str = "my_test_collection"

# Define a search interval
start_date = datetime(2000, 1, 1)
stop_date = datetime(2030, 1, 1)

# Prefect and dask
dask_gateway_staging: Gateway = None
dask_cluster_staging: GatewayCluster = None
dask_client_staging: DaskClient = None
dask_gateway_eopf: Gateway = None
dask_cluster_eopf: GatewayCluster = None
dask_client_eopf: DaskClient = None

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


def init_rsclient(owner_id=None, cadip_station=ECadipStation.CADIP):
    """Init RsClient instances"""
    global apikey, auxip_client, cadip_client, stac_client

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
    auxip_client = generic_client.get_auxip_client()

    # Or get a Cadip client instance. Pass the cadip station.
    cadip_client = generic_client.get_cadip_client(cadip_station)

    # Or get a Stac client to access the catalog
    stac_client = generic_client.get_stac_client()

    print(f"Auxip service: {auxip_client.href_adgs}")
    print(f"CADIP service: {cadip_client.href_cadip}")
    print(f"Catalog service: {stac_client.href_catalog}")
    return auxip_client, cadip_client, stac_client


def create_test_collection() -> CollectionClient:
    """Create and return a test STAC collection"""

    # Clean the existing collection, if any
    stac_client.remove_collection(TEST_COLLECTION)

    # Add new collection
    response = stac_client.add_collection(
        Collection(
            id=TEST_COLLECTION,
            description=None,  # rs-client will provide a default description for us
            extent=Extent(
                spatial=SpatialExtent(bboxes=[-180.0, -90.0, 180.0, 90.0]),
                temporal=TemporalExtent([start_date, stop_date]),
            ),
        ),
    )
    response.raise_for_status()

    # Return the inserted collection
    inserted_collection = stac_client.get_collection(collection_id=TEST_COLLECTION)
    assert inserted_collection, "Collection was not inserted"
    return inserted_collection


def stage_test_several_items():
    """Stage several Cadip files into the STAC catalog and return it."""
    res = []
    # Get the test collection created from create_test_collection()
    test_collection = stac_client.get_collection(collection_id=TEST_COLLECTION)

    # When searching stations, we can also limit the number of returned results.
    # For this example, let's keep only one file.
    client = cadip_client
    files = client.search_stations(start_date, stop_date, limit=5)

    for count, file in enumerate(files):
        first_filename = file["id"]
        s3_path = f"s3://{RSPY_TEMP_BUCKET}/{client.owner_id}/{client.station_name}"
        temp_s3_file = f"{s3_path}/{first_filename}"
        local_path = None
        # Call the staging service
        client.staging(first_filename, s3_path=s3_path, tmp_download_path=local_path)
        # Then we can check when the staging has finished by calling the check status service
        while True:
            status = client.staging_status(first_filename)
            print(f"Staging status for {first_filename!r}: {status.value}")
            if status in [EDownloadStatus.DONE, EDownloadStatus.FAILED]:
                print("\n")
                break
            sleep(1)
        assert status == EDownloadStatus.DONE, "Staging has failed"

        # Now insert the item into the catalog

        # Simulated values
        if count % 2 == 0:
            WIDTH = 2500
            HEIGHT = 3000
        else:
            WIDTH = 3000
            HEIGHT = 2500

        # Let's use STAC item ID = filename
        item_id = os.path.basename(temp_s3_file)

        # The file path from the temp s3 bucket is given in the assets
        assets = {temp_s3_file.split("/")[-1]: Asset(href=temp_s3_file)}

        # Other hardcoded parameters for this demo
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]],
            ],
        }
        bbox = [-180.0, -90.0, 180.0, 90.0]
        now = datetime.now()
        properties = {
            "gsd": 0.12345,
            "width": WIDTH,
            "height": HEIGHT,
            "datetime": datetime.now(),
            "orientation": "nadir",
        }

        if count == 4:
            properties["proj:epsg"] = 4326
        else:
            properties["proj:epsg"] = 3857

        # Add item to the STAC catalog collection, check status is OK
        # NOTE: in future versions, this pystac Item object will be returned automatically by rs-client-libraries.
        item = Item(
            id=item_id,
            geometry=geometry,
            bbox=bbox,
            datetime=now,
            properties=properties,
            assets=assets,
        )
        response = stac_client.add_item(TEST_COLLECTION, item)
        response.raise_for_status()

        # Return the inserted item
        inserted_item = test_collection.get_item(item_id)
        assert inserted_item, "Item was not inserted"
        res.append(inserted_item)
    return res


def stage_test_item():
    """Stage any Cadip file into the STAC catalog and return it."""

    # Get the test collection created from create_test_collection()
    test_collection = stac_client.get_collection(collection_id=TEST_COLLECTION)

    # When searching stations, we can also limit the number of returned results.
    # For this example, let's keep only one file.
    client = cadip_client
    files = client.search_stations(start_date, stop_date, limit=1)
    assert len(files) == 1

    # We stage by filename = the file ID
    first_filename = files[0]["id"]

    # We must give a temporary S3 bucket path where to copy the file from the station.
    # Use our API key username so avoid conflicts with other users.
    # NOTE: in future versions, this S3 path will be automatically calculated by RS-Server.
    s3_path = f"s3://{RSPY_TEMP_BUCKET}/{client.owner_id}/{client.station_name}"
    temp_s3_file = f"{s3_path}/{first_filename}"

    # We can also download the file locally to the server, but this is useful only in local mode
    local_path = None

    # Call the staging service
    client.staging(first_filename, s3_path=s3_path, tmp_download_path=local_path)

    # Then we can check when the staging has finished by calling the check status service
    while True:
        status = client.staging_status(first_filename)
        print(f"Staging status for {first_filename!r}: {status.value}")
        if status in [EDownloadStatus.DONE, EDownloadStatus.FAILED]:
            print("\n")
            break
        sleep(1)
    assert status == EDownloadStatus.DONE, "Staging has failed"

    # Now insert the item into the catalog

    # Simulated values
    WIDTH = 2500
    HEIGHT = 2500

    # Let's use STAC item ID = filename
    item_id = os.path.basename(temp_s3_file)

    # The file path from the temp s3 bucket is given in the assets
    assets = {temp_s3_file.split("/")[-1]: Asset(href=temp_s3_file)}

    # Other hardcoded parameters for this demo
    geometry = {
        "type": "Polygon",
        "coordinates": [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]],
    }
    bbox = [-180.0, -90.0, 180.0, 90.0]
    now = datetime.now()
    properties = {
        "gsd": 0.12345,
        "width": WIDTH,
        "height": HEIGHT,
        "datetime": datetime.now(),
        "proj:epsg": 3857,
        "orientation": "nadir",
    }

    # Add item to the STAC catalog collection, check status is OK
    # NOTE: in future versions, this pystac Item object will be returned automatically by rs-client-libraries.
    item = Item(
        id=item_id,
        geometry=geometry,
        bbox=bbox,
        datetime=now,
        properties=properties,
        assets=assets,
    )
    response = stac_client.add_item(TEST_COLLECTION, item)
    response.raise_for_status()

    # Return the inserted item
    inserted_item = test_collection.get_item(item_id)
    assert inserted_item, "Item was not inserted"
    return inserted_item


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
            ] = f"http://mockup-station-adgs-svc.processing.svc.cluster.local:8080/Products({feature['properties']['auxip:id']})/$value"
    return items_collection


###########
# Prefect #
###########


async def init_prefect_blocks():
    global S3_BLOCK

    # This is only for local mode.
    # In the cluster, the blocks must be created only once by the admin.
    if not local_mode:
        return

    # Share data between the user, the client (jupyter or terminal) and prefect
    S3_BLOCK = RemoteFileSystem(
        basepath=f"s3://{PREFECT_SHARE_BUCKET}",
        settings={
            "key": os.environ["S3_ACCESSKEY"],
            "secret": os.environ["S3_SECRETKEY"],
            "client_kwargs": {"endpoint_url": os.environ["S3_ENDPOINT"]},
        },
    )
    await S3_BLOCK.save("s3", overwrite=True)


########
# Dask #
########


def get_dask_cluster(
    address: str,
    public_domain: str,
    scale: int = 2,
    image: str = "",
    cluster_name: str = "",
    worker_cores: int = 1,
    worker_memory: float = 2.0,
    namespace="dask-gateway",
) -> tuple[Gateway, GatewayCluster, DaskClient]:
    """Return existing dask cluster or create one"""

    if cluster_mode and ("JUPYTERHUB_API_TOKEN" not in os.environ):
        raise ValueError("JUPYTERHUB_API_TOKEN environment variable is missing")

    # Init dask gateway
    print(f"Connecting to dask gateway for {cluster_name!r}: {address} ...")
    gateway = Gateway(address=address, auth="jupyterhub" if cluster_mode else None)

    # If a cluster has already been initialized, retrieve it
    if clusters := gateway.list_clusters():
        cluster = gateway.connect(clusters[0].name)

    # Else create one
    elif local_mode:
        cluster = gateway.new_cluster()
    else:  # cluster_mode
        cluster = gateway.new_cluster(
            worker_cores=worker_cores,
            worker_memory=worker_memory,
            namespace=namespace,
            image=image,
            cluster_name=cluster_name,
            scheduler_extra_pod_labels={"cluster_name": cluster_name},
        )

    print(
        f"Dask dashboard for {cluster_name!r}: {cluster.dashboard_link.replace(address, public_domain)}",
    )

    # Scale the cluster
    gateway.scale_cluster(cluster.name, scale)

    client = cluster.get_client()
    return gateway, cluster, client


def init_dask_cluster_staging(scale: int, *args, **kwargs):
    """Init existing staging dask cluster or create one"""
    global dask_gateway_staging, dask_cluster_staging, dask_client_staging
    dask_gateway_staging, dask_cluster_staging, dask_client_staging = get_dask_cluster(
        os.environ["DASK_GATEWAY_STAGING_ADDRESS"],
        os.environ["DASK_GATEWAY_STAGING_PUBLIC"],
        scale,
        image="ghcr.io/rs-python/rs-infrastructure-dask-gateway:latest",
        cluster_name="dask-staging",
        *args,
        **kwargs,
    )


def init_dask_cluster_eopf(scale: int, *args, **kwargs):
    """Init existing eopf dask cluster or create one"""
    global dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf
    dask_gateway_eopf, dask_cluster_eopf, dask_client_eopf = get_dask_cluster(
        os.environ["DASK_GATEWAY_EOPF_ADDRESS"],
        os.environ["DASK_GATEWAY_EOPF_PUBLIC"],
        scale,
        image="ghcr.io/rs-python/rs-infrastructure-dask-gateway/eopf:latest",  # TODO: TO BE DEFINED
        cluster_name="dask-eopf",
        *args,
        **kwargs,
    )


def shutdown_dask_clusters(gateway: Gateway):
    """Shutdown all gateway clusters"""
    for cluster_info in gateway.list_clusters():
        try:
            cluster = gateway.connect(cluster_info.name)
            cluster.shutdown()
            print(f"Shutting down cluster {cluster_info.name!r} ...")
        except Exception as e:
            print(f"Error shutting down cluster {cluster_info.name!r}: {e}")


########
# Init #
########


def init_demo(owner_id=None, cadip_station=ECadipStation.CADIP):
    """Init environment before running a demo notebook."""

    # In local mode only: create the s3 buckets, if they do not already exists
    create_s3_buckets()

    # Set OAuth2 authentication in the http request session
    if cluster_mode:
        http_session.cookies.set("session", os.environ["RSPY_OAUTH2_COOKIE"])

    # Default owner_id
    if not owner_id:
        owner_id = (
            os.environ["JUPYTERHUB_USER"]
            if cluster_mode
            else os.environ["RSPY_HOST_USER"]
        )

    # Init RsClient instances
    return init_rsclient(owner_id, cadip_station)
