from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageCell:
    key: str
    lat: float
    lng: float
    ring: int
    distance_km: float


class CoveragePlanner:
    """Builds a deterministic geographic grid and prioritizes never-scanned cells."""

    def __init__(self, spacing_km: float = 3.5, max_cells: int = 25):
        self.spacing_km = max(1.0, float(spacing_km))
        self.max_cells = max(1, int(max_cells))

    @staticmethod
    def _offset(center_lat: float, center_lng: float, north_km: float, east_km: float) -> tuple[float, float]:
        lat = center_lat + north_km / 111.32
        denom = max(0.2, math.cos(math.radians(center_lat)))
        lng = center_lng + east_km / (111.32 * denom)
        return round(lat, 6), round(lng, 6)

    def all_cells(self, center_lat: float, center_lng: float) -> list[CoverageCell]:
        side = max(1, math.ceil(math.sqrt(self.max_cells)))
        radius = side // 2
        points: list[CoverageCell] = []
        for y in range(-radius, radius + 1):
            for x in range(-radius, radius + 1):
                ring = max(abs(x), abs(y))
                north = y * self.spacing_km
                east = x * self.spacing_km
                lat, lng = self._offset(center_lat, center_lng, north, east)
                distance = round(math.hypot(north, east), 2)
                key = f"{round(center_lat,3)}:{round(center_lng,3)}:{x}:{y}:{self.spacing_km:g}"
                points.append(CoverageCell(key=key, lat=lat, lng=lng, ring=ring, distance_km=distance))
        points.sort(key=lambda c: (c.ring, c.distance_km, c.key))
        return points[: self.max_cells]

    def plan(self, center_lat: float, center_lng: float, history: dict[str, int] | None = None) -> list[CoverageCell]:
        history = history or {}
        cells = self.all_cells(center_lat, center_lng)
        return sorted(cells, key=lambda c: (history.get(c.key, 0), c.ring, c.distance_km, c.key))
