from traitlets import Unicode

from dask_gateway_server.backends.local import LocalClusterConfig


class MyLocalClusterConfig(LocalClusterConfig):
    cluster_name = Unicode(
        "",
        config=True,
        help="Logical name supplied by the client",
    )
