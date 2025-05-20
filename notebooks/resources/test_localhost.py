# Copyright 2025 CS Group
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

"""
For testing: if we are running a Jupyter notebook from localhost, not from docker-compose,
then modify all the env vars to call the services from localhost.

Use with this at the top of your notebook:
import sys
sys.path.insert(0, "/path/to/parent/of/resources/dir")
import resources.test_localhost
"""

import os

os.environ["RSPY_HOST_USER"] = "localhost-user"
os.environ["RSPY_LOCAL_MODE"] = "1"
os.environ["RSPY_HOST_ADGS"] = "http://localhost:8001"
os.environ["RSPY_HOST_CADIP"] = "http://localhost:8002"
os.environ["RSPY_HOST_CATALOG"] = "http://localhost:8003"
os.environ["RSPY_HOST_STAGING"] = "http://localhost:8004"
os.environ["RSPY_HOST_DPR_SERVICE"] = "http://localhost:6003"
os.environ["S3_ACCESSKEY"] = "minio"
os.environ["S3_SECRETKEY"] = "Strong#Pass#1234"
os.environ["S3_ENDPOINT"] = "http://localhost:9100"
os.environ["S3_REGION"] = "sbg"
os.environ["RSPY_TEMP_BUCKET"] = "rs-cluster-temp"
os.environ["RSPY_CATALOG_BUCKET"] = "rs-cluster-catalog"

os.environ["PREFECT_URL"] = os.environ["RSPY_PREFECT_URL"] = "http://localhost:4200"
os.environ["PREFECT_API_URL"] = os.environ["PREFECT_URL"] + "/api"
os.environ["PREFECT_WORK_POOL_STAGING"] = "pefect-pool-staging"
os.environ["PREFECT_WORK_POOL_EOPF"] = "pefect-pool-eopf"

os.environ["DASK_GATEWAY_STAGING_ADDRESS"] = os.environ[
    "DASK_GATEWAY_STAGING_PUBLIC"
] = "http://localhost:8701"
os.environ["DASK_GATEWAY_EOPF_ADDRESS"] = os.environ["DASK_GATEWAY_EOPF_PUBLIC"] = (
    "http://localhost:8702"
)
os.environ["DASK_GATEWAY_EOPF_MOCKUP_ADDRESS"] = os.environ[
    "DASK_GATEWAY_EOPF_MOCKUP_PUBLIC"
] = "http://localhost:8703"

os.environ["RSPY_OAUTH2_COOKIE"] = "dummy-cookie"
