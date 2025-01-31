# Taken from: https://gitlab.eopf.copernicus.eu/cpm/eopf-cpm/-/blob/main/docs/source/developer-guide/simple_processor_module/simple_processor_example.py


import os
import sys

from dask.distributed import worker_client
from prefect import flow, get_run_logger, task
from prefect_dask import DaskTaskRunner

sys.path.append("./resources")
import dask_utils

gateway = dask_utils.get_dask_gateway(os.environ["DASK_GATEWAY_ADDRESS"])
existing_cluster_name = os.environ["DASK_CLUSTER_NAME"]
cluster = gateway.connect(existing_cluster_name)
client = cluster.get_client()

client.forward_logging()

client.upload_file("./resources/dask_utils.py")

# DEFINE CONFIGURATION TO ACCESS DATA FROM YOUR S3 BUCKET
S3_CONFIG = {
    "key": os.environ["S3_ACCESSKEY"],  # EDIT WITH YOUR S3 KEY
    "secret": os.environ["S3_SECRETKEY"],  # EDIT WITH YOUR S3 SECRET KEY
    "client_kwargs": {
        "endpoint_url": os.environ["S3_ENDPOINT"],
        "region_name": os.environ["S3_REGION"],
    },  # EDIT WITH YOUR CLIENT_KWARGS
}


@task
def single_dpr_task(PATH_TO_WRITE_YOUR_PRODUCT: str):
    logger = get_run_logger()
    logger.warning(f" IP address for task: {dask_utils.get_ip_address()}")

    import os.path as osp
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

    # Write the input product on disk on zarr format
    # EDIT THE FOLLOWING PATH
    # PATH_TO_WRITE_YOUR_PRODUCT = osp.abspath(os.path.join(os.getcwd(), "docs", "build"))
    os.makedirs(PATH_TO_WRITE_YOUR_PRODUCT, exist_ok=True)
    # write an EOProduct in zarr format
    # Edit url with an existing path to make it work
    # Edit the opening mode
    # with new_eoproduct.open(
    #     storage_driver=EOZarrStore,
    #     url=osp.join(PATH_TO_WRITE_YOUR_PRODUCT, "new_zarr_product.zarr"),
    #     mode=eopf.common.constants.OpeningMode.CREATE_OVERWRITE,
    # ):
    #     # Actually write the product to the store
    #     new_eoproduct.write()
    #     # the product will be automatically closed as it is a context manager
    #     # but you can manually use new_eoproduct.close()
    with EOZarrStore(
        # url=PATH_TO_WRITE_YOUR_PRODUCT
        AnyPath("s3://prefect-share/myzarr/", **S3_CONFIG),
    ).open(
        mode=eopf.common.constants.OpeningMode.CREATE_OVERWRITE,
    ) as st:
        # Actually write the product to the store in DIR_TO_WRITE_YOUR_PRODUCT/new_zarr_product.zarr
        st["new_zarr_product"] = new_eoproduct
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
    final_product["l1_sum_data"].tree()


@flow(
    task_runner=DaskTaskRunner(
        address=cluster.scheduler_address,
        client_kwargs={"security": cluster.security},
    ),
)
def dpr_flow(PATH_TO_WRITE_YOUR_PRODUCT: str):
    logger = get_run_logger()
    logger.warning(f" IP address for flow: {dask_utils.get_ip_address()}")

    client.submit(single_dpr_task, PATH_TO_WRITE_YOUR_PRODUCT).result()
