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

import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

# Read the .env file that contains env vars
load_dotenv(Path(__file__).parent.parent.parent / "local-mode" / ".env")

os.environ["RSPY_HOST_USER"] = getpass.getuser()

os.environ["RSPY_LOCAL_MODE"] = "1"
# rs-server urls
os.environ["RSPY_HOST_ADGS"] = "http://localhost:8001"
os.environ["RSPY_HOST_CADIP"] = "http://localhost:8002"
os.environ["RSPY_HOST_CATALOG"] = "http://localhost:8003"
os.environ["RSPY_HOST_STAGING"] = "http://localhost:8004"
os.environ["RSPY_HOST_DPR_SERVICE"] = "http://localhost:6003"
# s3 bucket
os.environ["S3_ENDPOINT"] = "http://localhost:9100"
# prefect
os.environ["PREFECT_URL"] = os.environ["RSPY_PREFECT_URL"] = "http://localhost:4200"
os.environ["PREFECT_API_URL"] = os.environ["PREFECT_URL"] + "/api"
# dask
os.environ["DASK_GATEWAY_STAGING_ADDRESS"] = os.environ[
    "DASK_GATEWAY_STAGING_PUBLIC"
] = "http://localhost:8701"
os.environ["DASK_GATEWAY_EOPF_ADDRESS"] = os.environ["DASK_GATEWAY_EOPF_PUBLIC"] = (
    "http://localhost:8702"
)
os.environ["DASK_GATEWAY_EOPF_MOCKUP_ADDRESS"] = os.environ[
    "DASK_GATEWAY_EOPF_MOCKUP_PUBLIC"
] = "http://localhost:8703"
# opentelemetry
os.environ["LOKI_ENDPOINT"] = "http://localhost:3100/loki/api/v1/push"
os.environ["TEMPO_ENDPOINT"] = "http://localhost:4317"

os.environ["RSPY_OAUTH2_COOKIE"] = "dummy-cookie"
