
from prefect import flow, task


@flow(name="staging")
def staging():
    print("Launch staging flow...")
