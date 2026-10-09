"""Bind explicitly reviewed native traversals into the shared typed catalog.

Room connections alone are not access rules. Every native link must have an
explicit rule and evidence, or an explicit exclusion with a reason. The review
is bound to the exact link-table hash; opposite directions remain independent.
"""

from ..integrations.rom.room_links import RoomLink
from .catalog import Json, array, obj, parse_catalog, parse_rules, string


def apply_native_routes(catalog: Json, links: tuple[RoomLink, ...], review: Json, source_sha256: str) -> dict[str, Json]:
    data = obj(review)
    if set(data) != {"format_version", "source_sha256", "room_regions", "links"}:
        raise ValueError("Native route reviews require version, source hash, room regions and links")
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported native route review version")
    if (
        len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
        or data["source_sha256"] != source_sha256
    ):
        raise ValueError("Native route review does not match the source link table")
    result = dict(obj(catalog))
    regions = {string(obj(region)["id"]) for region in array(result["regions"])}
    room_regions = {room: string(region) for room, region in obj(data["room_regions"]).items()}
    if set(room_regions.values()) - regions:
        raise ValueError("Native rooms reference unknown catalog regions")
    if len({link.id for link in links}) != len(links):
        raise ValueError("Duplicate native link identity")
    reviews = obj(data["links"])
    if set(reviews) != {link.id for link in links}:
        raise ValueError("Every native link requires exactly one review; stale or missing reviews are rejected")
    paths = list(array(result["paths"]))
    path_ids = {string(obj(path)["id"]) for path in paths}
    for link in links:
        entry = obj(reviews[link.id])
        if set(entry) == {"exclude"}:
            string(entry["exclude"])
            continue
        if set(entry) != {"requires", "evidence"}:
            raise ValueError(f"Route {link.id} needs explicit requirements and evidence, or an exclusion reason")
        string(entry["evidence"])
        parse_rules(entry["requires"])
        if not link.has_destination:
            raise ValueError(f"Virtual or empty destination must be excluded explicitly: {link.id}")
        if {link.source_room, link.destination_room} - room_regions.keys():
            raise ValueError(f"Unmapped native route endpoint: {link.id}")
        if link.id in path_ids:
            raise ValueError(f"Native route duplicates an existing catalog path: {link.id}")
        source, target = room_regions[link.source_room], room_regions[link.destination_room]
        paths.append({
            "id": link.id,
            "forward": {"source": source, "target": target, "requires": entry["requires"]},
            # A reverse native record gets its own independently reviewed edge.
            "reverse": {"source": target, "target": source, "requires": {"any": []}},
        })
        path_ids.add(link.id)
    result["paths"] = paths
    parse_catalog(result)
    return result
