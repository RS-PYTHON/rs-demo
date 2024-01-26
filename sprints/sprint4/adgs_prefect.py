# We'll use boto3 to monitor the s3 bucket.
# Note: the S3_ACCESSKEY, S3_SECRETKEY and S3_ENDPOINT are given in the docker-compose.yml file.
import boto3
import os
from prefect import flow, task
import requests
import asyncio
from pathlib import Path

s3_session = boto3.session.Session()
s3_client = s3_session.client(
    service_name="s3",
    aws_access_key_id="minio",
    aws_secret_access_key="Strong#Pass#1234",
    endpoint_url="http://localhost:9000",
)


# Define some variables
endpoint="http://localhost:8000/cadip/CADIP/cadu" # rs-server host = the container name
start="2014-01-01T12:00:00.000Z"
stop="2023-12-30T12:00:00.000Z"
bucket_name = "test-data"
local_download_dir = "/local/download"

@task(name='search_cadu_task')
def search_cadu(date_start: str, date_end: str):
    print(f"Searching products between {date_start} and {date_end}")
    data = requests.get(f"{endpoint}/list", {"start_date": start, "stop_date": stop})
    products = data.json()["CADIP"]
    print(f"Here is the list of products found: {products}")
    product_names = [name for id, name in products]
    return product_names

@task(name='download_one_task')
async def download_one(name: str, save_to_s3: bool):
    params = {"name": name, "local": local_download_dir}
    # obs = the bucket URL, if requested
    if save_to_s3:
        print(f"pushing {name} to the bucket {bucket_name} ...")
        params["obs"] = f"s3://{bucket_name}/Cadip_products"
    data = requests.get(endpoint, params)
    assert data.status_code == 200

@task(name='print_status_task')
async def print_status(product_names: list):
    # Wait a second if the staus need to be passed 
    # from DONE to NOT_STARTED if we download several times.
    await asyncio.sleep(1)
    all_done = False
    while not all_done: 
        # Count the number of products not started, in progres etc ...
        all_status = {"NOT_STARTED": 0, "IN_PROGRESS": 0, "FAILED": 0, "DONE": 0}
        for name in product_names:           
            # Call the "status" endpoint
            data = requests.get(f"{endpoint}/status", {"name": name})
            assert data.status_code == 200
            all_status[(data.json())["status"]] += 1
        # Print result
        print (" / ".join ([f"{status}:{count}" for status, count in all_status.items()]))
        if all_status["DONE"] == len(product_names):
            all_done = True
        else:
            await asyncio.sleep(1)

    
@task(name='download_all_task')
async def download_all(save_to_s3: bool, product_names: list):
    async with asyncio.TaskGroup() as group:
        group.create_task (print_status.fn(product_names))
        for name in product_names:
            print(f"Downloading {name}")
            group.create_task(download_one.fn(name, save_to_s3))
            print(f"{name} has been downloaded !")

@task(name='download_cadu_task')
async def download_cadu(save_to_s3: bool, product_names: list):
    # S3 bucket name
    bucket_name = "test-data"
    # Check if the s3 bucket already exist
    if bucket_name in [bucket["Name"] for bucket in s3_client.list_buckets()["Buckets"]]:
        print(f"The bucket {bucket_name} already exists, removing the existing products from it ...")
        bucket_content = s3_client.list_objects(Bucket=bucket_name)
        print(f"Bucket {bucket_name} is clear !")
        # Check if the bucket is not empty
        if 'Contents' in bucket_content:
            all_s3_filenames = [key["Key"] for key in s3_client.list_objects(Bucket=bucket_name)['Contents']]
            # Remove the existing products from it
            for file in all_s3_filenames:
                s3_client.delete_object(Bucket=bucket_name, Key=file)
    # Else create the bucket
    else:
        print(f"The bucket {bucket_name} does not exists, creating the bucket {bucket_name} ...")
        s3_client.create_bucket(Bucket=bucket_name)
        print(f"The bucket {bucket_name} has beeen created !")
    # Remove all local files if they exist
    print("Removing all local files if they exist ...")
    for name in product_names:
        file = Path (local_download_dir) / name
        if file.is_file():
            file.unlink()
    print("local download directory is clear !")
    await download_all.fn(save_to_s3, product_names)
    await asyncio.sleep(1)
    # If value save_to_s3 is True, download all the products and upload it on the bucket s3
    if save_to_s3:
        await asyncio.sleep(1)
        all_s3_filenames = [key["Key"] for key in s3_client.list_objects(Bucket=bucket_name)['Contents']]
        for name in product_names:
            is_missing = True
            for filename in all_s3_filenames:
                if name in filename:
                    is_missing = False
            if is_missing:
                raise RuntimeError (f"{name} is missing from the S3 bucket")
            print (f"s3://{bucket_name}/{name} exists")
    # If value save_to_s3 is False, download all the products locally
    else:
        for name in product_names:
            file = Path (local_download_dir) / name    
            print(file)
            if not file.is_file():
                raise RuntimeError (f"{name} is missing locally")
            print (f"{file} exists")

@flow(name='main_flow', log_prints=True)
def working(save_to_s3: bool= True, date_start: str = "2014-01-01T12:00:00.000Z", date_end: str = "2023-12-30T12:00:00.000Z"):
    print(f"Save to S3: {save_to_s3}.")
    product_names = search_cadu(date_start, date_end)
    download_cadu(save_to_s3, product_names)

#working.serve(name="my-first-deployment")
working(True, start, stop)