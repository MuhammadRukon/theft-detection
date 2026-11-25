import json
from pathlib import Path

from app.behavior.base import Zone


class ZonesError(ValueError):
    pass


def point_in_polygon(x: float, y: float, polygon) -> bool:
    """Ray casting; points on an edge or vertex count as inside."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if cross == 0 and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            return True
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _zone(cam: str, i: int, raw) -> Zone:
    where = f"camera {cam!r} zone #{i + 1}"
    if not isinstance(raw, dict):
        raise ZonesError(f"{where}: must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ZonesError(f"{where}: 'name' must be a non-empty string")
    where = f"camera {cam!r} zone {name!r}"
    pts = raw.get("polygon")
    if not isinstance(pts, list) or len(pts) < 3:
        raise ZonesError(f"{where}: 'polygon' needs at least 3 points")
    poly = []
    for p in pts:
        if not (isinstance(p, list) and len(p) == 2 and all(_num(v) and 0 <= v <= 1 for v in p)):
            raise ZonesError(f"{where}: point {p!r} must be [x, y] with both in 0-1")
        poly.append((float(p[0]), float(p[1])))
    dwell = raw.get("dwell_s")
    if not _num(dwell) or dwell <= 0:
        raise ZonesError(f"{where}: 'dwell_s' must be a number > 0")
    return Zone(name, tuple(poly), float(dwell))


def load_zones(path: str | Path) -> dict[str, list[Zone]]:
    """{camera_id: [Zone]} from a JSON file; raises ZonesError naming the offending camera/zone."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise ZonesError(f"cannot read zones file {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ZonesError(f"zones file {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ZonesError("zones file must be an object of camera_id -> list of zones")
    out: dict[str, list[Zone]] = {}
    for cam, raw_zones in data.items():
        if not isinstance(raw_zones, list):
            raise ZonesError(f"camera {cam!r}: must be a list of zones")
        zones = [_zone(cam, i, z) for i, z in enumerate(raw_zones)]
        names = [z.name for z in zones]
        dup = next((n for n in names if names.count(n) > 1), None)
        if dup:
            raise ZonesError(f"camera {cam!r}: duplicate zone name {dup!r}")
        out[cam] = zones
    return out
