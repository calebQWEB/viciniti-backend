import math
from sqlalchemy import func

EARTH_RADIUS_KM = 6371.0


def distance_km(lat_col, lng_col, lat: float, lng: float):
    """SQL expression: great-circle (haversine) distance in km from (lat, lng) to the row's coordinates."""
    dlat = func.radians(lat_col - lat)
    dlng = func.radians(lng_col - lng)
    a = (
        func.power(func.sin(dlat / 2.0), 2)
        + math.cos(math.radians(lat)) * func.cos(func.radians(lat_col)) * func.power(func.sin(dlng / 2.0), 2)
    )
    # Clamp to 1 so float error can't push asin() out of its domain
    return 2 * EARTH_RADIUS_KM * func.asin(func.least(1.0, func.sqrt(a)))


def within_radius(lat_col, lng_col, lat: float, lng: float, radius_km: float) -> list:
    """Filter conditions keeping rows within radius_km of (lat, lng)."""
    lat_delta = math.degrees(radius_km / EARTH_RADIUS_KM)
    conditions = [
        lat_col.isnot(None),
        lng_col.isnot(None),
        # Cheap bounding box first, so the exact distance only runs on nearby rows
        lat_col.between(lat - lat_delta, lat + lat_delta),
    ]

    cos_lat = math.cos(math.radians(lat))
    if cos_lat > 1e-6:
        lng_delta = math.degrees(radius_km / (EARTH_RADIUS_KM * cos_lat))
        # Skip the longitude box when it would wrap around the antimeridian
        if lng - lng_delta >= -180 and lng + lng_delta <= 180:
            conditions.append(lng_col.between(lng - lng_delta, lng + lng_delta))

    conditions.append(distance_km(lat_col, lng_col, lat, lng) <= radius_km)
    return conditions


def attach_distances(rows) -> list:
    """Turn (model, distance) rows into models carrying a distance_km attribute for the response schema."""
    results = []
    for obj, distance in rows:
        obj.distance_km = round_distance(distance)
        results.append(obj)
    return results


# Public coordinates are snapped to this grid (~550 m) so a seller's home can't be pinpointed
COORDINATE_BLUR_DEGREES = 0.005


def blur_coordinate(value):
    """Snap a latitude or longitude to the public grid; None stays None."""
    if value is None:
        return None
    return round(round(value / COORDINATE_BLUR_DEGREES) * COORDINATE_BLUR_DEGREES, 4)


def round_distance(km: float) -> float:
    """Round to the nearest 0.5 km (minimum 0.5) so exact distances can't be used to triangulate."""
    return max(0.5, round(km * 2) / 2)


def mark_owner_view(obj):
    """Flag an ORM listing/service so the response schema returns its exact coordinates."""
    obj.exact_coordinates = True
    return obj
