from dask_gateway_server.options import Options, String

from dask_gateway_local_ext import MyLocalClusterConfig

c.DaskGateway.backend_class = "dask_gateway_server.backends.local.UnsafeLocalBackend"
c.LocalBackend.cluster_config_class = MyLocalClusterConfig
c.Backend.cluster_options = Options(
    String("cluster_name", default="", label="Cluster Name"),
)
