"""Delta Exchange REST API client.

Pieces: configuration, error types, response models, and the async HTTP
client. No business logic or persistence lives here.
"""

from app.integrations.delta.client import DeltaClient, get_delta_client
from app.integrations.delta.config import DeltaConfig, get_delta_config
from app.integrations.delta.exceptions import (
    APIError,
    AuthenticationError,
    DeltaError,
    NetworkError,
    RateLimitError,
)
from app.integrations.delta.models import (
    CandleResponse,
    DeltaErrorBody,
    DeltaResponse,
    Product,
    ProductAsset,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "CandleResponse",
    "DeltaClient",
    "DeltaConfig",
    "DeltaError",
    "DeltaErrorBody",
    "DeltaResponse",
    "NetworkError",
    "Product",
    "ProductAsset",
    "RateLimitError",
    "get_delta_client",
    "get_delta_config",
]
