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

"""DPR processor example"""

import logging
import os
import sys
from importlib import reload
from pathlib import Path

from distributed import worker_client
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner
from resources import dask_utils
from resources.dask_utils import get_ip_address
from rs_common import prefect_utils

# Read prefect blocks into env vars
prefect_utils.read_prefect_blocks(_sync=True)

# Get the existing dask cluster info from the env vars passed by the client.
reload(dask_utils)  # reload global vars from env vars
dask_gateway, dask_cluster, dask_client = dask_utils.get_existing_cluster(
    os.environ["DASK_GATEWAY_ADDRESS"],
    os.environ["DASK_CLUSTER_NAME"],
)

# Now I need to upload my local utility module that will be used by the dask tasks
dask_client.upload_file("./resources/dask_utils.py")

# NOTE: the main code outside the functions is run by both the client and prefect workers,
# but NOT by the dask workers.
# But this log won't show when run from a prefect worker because get_run_logger() is not available yet.
# The dask workers will do the imports and run the tasks, but won't run the flow or code outside functions.
logging.warning(
    f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (main code)",
)
# You can test to write an empty file to check that it is written only on the client
# and prefect workers filesystems, not on the dask workers filesystem.
Path("/tmp/.empty").touch()

# But the global variables are still passed to the dask workers.
# Init the S3 configuration so the dask workers can write to the bucket
# with the env variables from the client or prefect.
S3_CONFIG = {
    "key": os.environ["S3_ACCESSKEY"],
    "secret": os.environ["S3_SECRETKEY"],
    "client_kwargs": {
        "endpoint_url": os.environ["S3_ENDPOINT"],
        "region_name": os.environ["S3_REGION"],
    },
}

# NOTE: the tasks are called only by the dask workers, not by the client or prefect.


@task
def all_my_eopf_code(s3_folder: str, s3_filename: str):
    """
    EOPF is installed only in the dask workers, so put all the "import eopf ..." lines in the task, not outside.

    Dummy DPR processor, taken from:
    https://gitlab.eopf.copernicus.eu/cpm/eopf-cpm/-/blob/main/docs/source/developer-guide/simple_processor_module/simple_processor_example.py
    """
    from typing import Any, Dict, Optional, cast

    import dask.array as da
    import eopf.common.constants
    import numpy as np
    from eopf.common.file_utils import AnyPath
    from eopf.computing.abstract import (
        AuxiliaryDataFile,
        EOProcessingStep,
        EOProcessingUnit,
    )
    from eopf.logging import EOLogging

    # EOPF libraries
    from eopf.product.eo_product import EOGroup, EOProduct
    from eopf.product.eo_variable import EOVariable
    from eopf.product.utils.eoobj_utils import copy_variable

    # The first thing to do is importing the desired Store
    from eopf.store.zarr import EOZarrStore
    from xarray.core.datatree import DataTree

    # Implementation of the processing steps
    class ProcessVariablesStep(EOProcessingStep):
        def __init__(self):
            # Apply your eopf-cpm logging configuration if necessary
            self._log = EOLogging().get_logger(name="proto_s3_olci")

        def apply(self, sensor1: np.ndarray, sensor2: np.ndarray) -> np.ndarray:  # type: ignore
            """
            Here we implement avery basic computation as an example: both sensor values are added together
            """
            result = sensor1 + sensor2
            return result

    # Implementation of the processing units
    class RechunkingUnit(EOProcessingUnit):
        """Processing unit responsible of re-chunking all EOProduct variables"""

        def run(
            self,
            inputs: dict[str, EOProduct | DataTree],
            adfs: Optional[dict[str, AuxiliaryDataFile]] = None,
            **kwargs: Any,
        ) -> dict[str, EOProduct | DataTree]:
            try:
                eoproduct = inputs["l1"]
                chunks = kwargs.get("chunks", None)

            except KeyError as e:
                raise TypeError(f"Missing parameter: {e}")

            return {"l1_rechunked": self.rechunk_all_variables(eoproduct, chunks)}

        def rechunk_all_variables(self, my_eoproduct: EOProduct, chunks: Dict) -> EOProduct:  # type: ignore
            """
            re-chunk all variables of a given EOProduct using the new dimensions provided within chunks dict.
            """
            # loop over all groups of the eocontainer
            for _, group in my_eoproduct.groups:
                # do the same thing for all sub-groups
                self.rechunk_all_variables(group, chunks)
                # re-chunk all concerned variables
                for _, var in group.variables:
                    new_chunks = {}
                    for dim, chunk in chunks.items():
                        if dim in var.dims:
                            new_chunks[dim] = chunk
                    # re-chunk the variable
                    if len(new_chunks) > 0:
                        var.chunk(new_chunks)

            return my_eoproduct

    class ProcessVariablesUnit(EOProcessingUnit):
        """
        Processing unit responsible of perform a computation on two EOVariables
        """

        def run(
            self,
            inputs: dict[str, EOProduct | DataTree],
            adfs: Optional[dict[str, AuxiliaryDataFile]] = None,
            **kwargs: Any,
        ) -> dict[str, EOProduct | DataTree]:
            try:
                my_eoproduct = inputs["l1_rechunked"]

            except KeyError as e:
                raise TypeError(f"Missing parameter: {e}")

            # Get the variables we want to use for the computation
            sensor1_data = cast(
                da.Array,
                my_eoproduct.measurements.image.sensor1.data.data,
            )
            sensor2_data = cast(
                da.Array,
                my_eoproduct.measurements.image.sensor2.data.data,
            )

            # Instanciate your processing step
            process_variable_step = ProcessVariablesStep()
            final_data = da.map_blocks(
                process_variable_step.apply,
                sensor1_data,
                sensor2_data,
                dtype=np.dtype("int16"),
            ).compute()
            # Creation of the output product for this processing unit
            result = EOProduct("my_eoproduct_after_processvariable_unit")

            measurements = result["measurements"] = EOGroup()  # noqa
            image = result["measurements/image"] = EOGroup()
            coordinates = result["coordinates"] = EOGroup()  # noqa

            # Copy measurements from sensor1 and sensor2
            copy_variable(my_eoproduct.measurements.image.sensor1, image, name="sensor1")  # type: ignore
            copy_variable(my_eoproduct.measurements.image.sensor2, image, name="sensor2")  # type: ignore

            # Add a new variable for the new processed data
            result.measurements.image["final_sensor"] = EOVariable("", data=final_data)

            return {"l1_sum_data": result}

    # Implementation of the processor
    class MyNewProcessor(EOProcessingUnit):
        def __init__(self):
            # Get a logger from your logging configuration
            self._log = EOLogging().get_logger(name="proto_s3_olci")

        def run(
            self,
            inputs: dict[str, EOProduct | DataTree],
            adfs: Optional[dict[str, AuxiliaryDataFile]] = None,
            **kwargs: Any,
        ) -> dict[str, EOProduct | DataTree]:
            try:
                new_eoproduct = inputs["l1"]  # noqa
                chunks = kwargs.get("chunks", None)
                context = kwargs.get("context", {})  # noqa

            except KeyError as e:
                raise TypeError(f"Missing parameter: {e}")

            # Processing unit 1: we apply a data rechunking
            rechunking_unit = RechunkingUnit()
            rechunked_data = rechunking_unit.run(
                inputs=inputs,
                adfs=None,
                chunks=chunks,
            )

            # Processing unit 2: Add two EOVariables together
            process_variable_unit = ProcessVariablesUnit()
            final_data = process_variable_unit.run(inputs=rechunked_data)
            return final_data

    # Create a new EOProduct
    # Create an EOProduct and give it a name
    name = "eoproduct.zarr"
    # Create product, strict will create all mandatory group for a valid EOProduct according to the PDFS
    new_eoproduct = EOProduct(name=name, strict=True)

    # Add variable inside the group(s)
    new_eoproduct["measurements/image/oa1_radiance"] = EOVariable(
        "oa1_radiance",
        data=da.from_array(np.random.randint(0, 65535, (1024, 1024))),
    )
    new_eoproduct["measurements/orphans/orphans_oa01_radiance"] = EOVariable(
        "orphans_oa01_radiance",
        data=da.from_array(np.random.randint(0, 65535, (1024, 1024))),
    )

    # Create two  EOvariables (Dask arrays) that will be used inside the processor
    new_eoproduct["measurements/image/sensor1"] = EOVariable(
        "sensor1",
        data=da.from_array(np.random.randint(0, 100, (1024, 1024))),
    )
    new_eoproduct["measurements/image/sensor2"] = EOVariable(
        "sensor2",
        data=da.from_array(np.random.randint(0, 100, (1024, 1024))),
    )

    # Check if your new product is valid (it should be the case if it contains the necessary groups)
    new_eoproduct.is_valid()

    # write an EOProduct in zarr format
    with EOZarrStore(
        AnyPath(s3_folder, **S3_CONFIG),
    ).open(
        mode=eopf.common.constants.OpeningMode.CREATE_OVERWRITE,
        delayed_writing=False,
    ) as st:
        # Actually write the product to the store in DIR_TO_WRITE_YOUR_PRODUCT/new_zarr_product.zarr
        st[s3_filename] = new_eoproduct
        # the store will be automatically closed as it is a context manager
        # but you can manually use st.close()

    # Instantiate and run your new processor
    processor = MyNewProcessor()
    chunks = {"dim_0": 10, "dim_1": -1}
    final_product = processor.run(
        inputs={"l1": new_eoproduct},
        adfs=None,
        chunks=chunks,
    )
    return final_product["l1_sum_data"]._repr_html_()


@task
def single_dpr_task(s3_folder: str, s3_filename: str):
    """
    Call the EOPF code.
    """
    with worker_client(separate_thread=False):  # as client:
        logger = get_run_logger()

        # Say hello from the dask task
        logger.warning(
            f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (task {s3_filename!r})",
        )

        ret = all_my_eopf_code(s3_folder, s3_filename)

        logger.warning(
            f"Goodbye from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (task {s3_filename!r})",
        )
        return ret


@flow(
    task_runner=DaskTaskRunner(
        address=dask_cluster.scheduler_address,
        client_kwargs={"security": dask_cluster.security},
    ),
)
def dpr_flow(s3_folder: str, s3_filenames: list[str]):
    """
    Main flow. Called only by the client or prefect worker (depending on how we call prefect),
    not by the dask workers.

    Args:
        s3_folder: S3 folder where to write output zarr products as 's3://<bucket-name>/sub/folder
        s3_filenames: output generated zarr filenames: 1 per output product.
    """
    logger = get_run_logger()
    logger.warning(
        f"Hello from {os.environ['HELLO_FROM']!r} {get_ip_address()!r} (flow)",
    )

    # Call the task for each output filename
    futures = [
        single_dpr_task.submit(
            s3_folder,
            filename,
        )
        for filename in s3_filenames
    ]

    # We should do this
    return [future.result(timeout=10) for future in futures]

    # # Workaround to try several times... to be removed
    # results = []
    # for future in futures:
    #     tries = 0
    #     while True:
    #         try:
    #             tries += 1
    #             logger.info(f"Try #{tries}")
    #             results.append(future.result(timeout=10))
    #             break
    #         except Exception as exception:
    #             if tries >= 5:
    #                 raise
    #             logger.error(exception)

    return results
