import os

from dask_gateway import Gateway, JupyterHubAuth
from distributed import Client
from prefect import flow, task
from prefect_dask import DaskTaskRunner


@flow(name="dask_cluster")
def dask_cluster():
    """Prefect flow that is run py a prefect prefect worker in the cluster"""

    print("Entering in dask_cluster")
    # check the auth type, only jupyterhub type supported for now
    auth_type = os.environ["DASK_GATEWAY__AUTH__TYPE"]
    # Handle JupyterHub authentication
    if auth_type == "jupyterhub":
        gateway_auth = JupyterHubAuth(api_token=os.environ["JUPYTERHUB_API_TOKEN"])
    else:
        print(f"Unsupported authentication type: {auth_type}")
        raise RuntimeError(f"Unsupported authentication type: {auth_type}")
    print("Creating dask gateway object")
    gateway = Gateway(
        address=os.environ["DASK_GATEWAY__ADDRESS"],
        auth=gateway_auth,
    )
    print(
        "The dask gateway object was created, getting the list with the present clusters",
    )
    clusters = gateway.list_clusters()
    print(f"The list of clusters: {clusters}")
    cluster = gateway.connect(clusters[0].name)
    print(f"First cluster scheduler address = {cluster.scheduler_address}")
    client = Client(cluster)
    print(f"Dask client = {client}")
    try:
        print(f"{client.get_versions(check=True)}")
        workers = client.scheduler_info()["workers"]
        print(f"Number of running workers: {len(workers)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Dask cluster client failed: {e}")
        raise RuntimeError(f"Dask cluster client failed: {e}") from e
    if len(workers) == 0:
        print("No workers are currently running in the Dask cluster. Scaling up to 1.")
        cluster.scale(1)

    # Prefect flow and task definitions
    @task
    def add_numbers(x, y):
        print("Running task add_numbers")
        return x + y

    @task
    def multiply_numbers(x, y):
        print("Running task multiply_numbers")
        return x * y

    @flow(
        task_runner=DaskTaskRunner(
            address=cluster.scheduler_address,
            client_kwargs={"security": cluster.security},
        ),
    )
    def hello_world():
        sum_result = add_numbers.submit(5, 3)  # Submit tasks to the flow
        product_result = multiply_numbers.submit(5, 3)
        print(f"Sum result: {sum_result.result()}")
        print(f"Product result: {product_result.result()}")

    hello_world()
