"""
Shared modules for Formula OCR microservices.

This package contains common code shared across all services:
- domain: Core domain models (BBox, Node)
- infrastructure: Redis, MinIO, DB clients
- merge: Logic for merging OCR and formula data

To use in a service:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from shared.domain.bbox import BBox
    from shared.domain.node import Node
    from shared.infrastructure.redis_client import create_redis_client
    from shared.infrastructure.minio_client import create_minio_client
    from shared.merge.tree_merger import TreeMerger
"""

from .domain.bbox import BBox
from .domain.node import Node
from .infrastructure import (
    create_redis_client, get_redis_client,
    create_minio_client, get_minio_client
)
from .merge import TreeMerger, SpatialIndex, OptimizedPageParser

__version__ = "1.0.0"

__all__ = [
    'BBox',
    'Node',
    'create_redis_client',
    'get_redis_client',
    'create_minio_client',
    'get_minio_client',
    'TreeMerger',
    'SpatialIndex',
    'OptimizedPageParser',
]
