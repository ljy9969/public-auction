"""Shared coordinates and distance helpers."""
from __future__ import annotations

import math

DONG_COORDS: dict[str, tuple[float, float]] = {
    "잠실본동": (37.5133, 127.1002),
    "삼전동": (37.5052, 127.0905),
    "석촌동": (37.5055, 127.1065),
    "송파1동": (37.4995, 127.1125),
    "방이2동": (37.5115, 127.1180),
    "삼성동": (37.5088, 127.0630),
    "대치동": (37.4955, 127.0635),
    "역삼동": (37.5005, 127.0365),
    "논현동": (37.5115, 127.0310),
    "청담동": (37.5195, 127.0535),
    "압구정동": (37.5275, 127.0285),
    "신사동": (37.5240, 127.0205),
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
