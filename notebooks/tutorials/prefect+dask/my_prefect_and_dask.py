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

"""Python module for the tutorials, to be shared with the prefect and dask workers.

Implement utility functions and prefect and dask tasks and flows.

WARNING: AFTER EACH MODIFICATION, RESTART THE JUPYTER NOTEBOOK KERNEL !
"""

#
# Example flow and tasks from: https://docs.prefect.io/integrations/prefect-dask/index#connect-to-an-existing-cluster
#

# import dask.dataframe
# import dask.distributed
# from prefect import flow, task
# from prefect_dask import DaskTaskRunner, get_dask_client

import logging
import os
import sys

sys.path.append("./resources")
import my_shared_utils
import utils

gateway = utils.get_dask_gateway(os.environ["DASK_GATEWAY_ADDRESS"])
existing_cluster_name = os.environ["DASK_CLUSTER_NAME"]
cluster = gateway.connect(existing_cluster_name)
client = cluster.get_client()

client.forward_logging()

client.upload_file("./resources/utils.py")
client.upload_file("./resources/my_shared_utils.py")


def inc(x, name):

    # Note that this is run from a dask worker with a different IP than the client,
    # and that the workers also differ between the staging and eopf workers.
    logging.warning(
        f" Worker IP address for {name!r}: {my_shared_utils.get_ip_address()}",
    )

    return x + 1


def add(x, y):
    return x + y


def my_flow(name: str):
    a = client.submit(inc, 10, name)  # calls inc(10) in background thread or process
    b = client.submit(inc, 20, name)  # calls inc(20) in background thread or process
    print(f"a: {a.result()}")
    print(f"b: {b.result()}")

    c = client.submit(add, a, b)  # calls add on the results of a and b
    print(f"c: {c.result()}")

    futures = client.map(inc, range(5), name=name)
    results = client.gather(futures)  # this can be faster
    print(results)


# @task
# def read_data(start: str, end: str) -> dask.dataframe.DataFrame:
#     df = dask.datasets.timeseries(start, end, partition_freq="4w")
#     return df

# @task
# def process_data(df: dask.dataframe.DataFrame) -> dask.dataframe.DataFrame:
#     with get_dask_client():
#         df_yearly_avg = df.groupby(df.index.year).mean()
#         return df_yearly_avg.compute()

# @flow(task_runner=DaskTaskRunner(
#     address="toto://" + cluster.scheduler_address,
#     client_kwargs={"security": cluster.security},
# ))
# def dask_pipeline(start: str, end: str):
#     # df = read_data.submit(start, end)
#     # df_yearly_average = process_data.submit(df)
#     # return df_yearly_average
#     print("hello")


# if __name__ == "__main__":
#     dask_pipeline("1998", "2005")
