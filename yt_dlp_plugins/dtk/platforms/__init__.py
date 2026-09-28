"""Platform packages（vendored subset for yt-dlp plugin；registry 已移除）。"""
from dtk.platforms.base import (
    ClientProfile,
    EndpointSpec,
    EndpointTable,
    PlatformAdapter,
    RequestSpec,
)

__all__ = ["ClientProfile", "EndpointSpec", "EndpointTable", "PlatformAdapter", "RequestSpec"]
