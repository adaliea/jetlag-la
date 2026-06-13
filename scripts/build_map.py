"""Build the self-contained interactive LA Hide + Seek map."""

from __future__ import annotations

import csv
import html
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "current-gtfs-rail"
REFERENCE = ROOT / "reference-old-la-map"
OUTPUT = ROOT / "map"
ZONE_KM = 0.4


def read_csv(name):
    with (GTFS / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, coordinate in enumerate(polygon):
        xi, yi = coordinate[:2]
        xj, yj = polygon[j][:2]
        crosses = (yi > y) != (yj > y)
        if crosses and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def local_xy(point, latitude):
    lon, lat = point
    return lon * 111.32 * math.cos(math.radians(latitude)), lat * 110.574


def distance_to_segment_km(point, a, b):
    latitude = point[1]
    px, py = local_xy(point, latitude)
    ax, ay = local_xy(a, latitude)
    bx, by = local_xy(b, latitude)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_boundary_km(point, polygon):
    return min(
        distance_to_segment_km(point, polygon[i - 1], polygon[i])
        for i in range(len(polygon))
    )


def perpendicular_distance(point, start, end):
    x, y = point
    x1, y1 = start
    x2, y2 = end
    if start == end:
        return math.hypot(x - x1, y - y1)
    return abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / math.hypot(
        y2 - y1, x2 - x1
    )


def simplify(points, tolerance=0.00018):
    if len(points) < 3:
        return points
    max_distance = 0
    index = 0
    for i in range(1, len(points) - 1):
        distance = perpendicular_distance(points[i], points[0], points[-1])
        if distance > max_distance:
            index, max_distance = i, distance
    if max_distance <= tolerance:
        return [points[0], points[-1]]
    left = simplify(points[: index + 1], tolerance)
    right = simplify(points[index:], tolerance)
    return left[:-1] + right


def load_boundary():
    tree = ET.parse(REFERENCE / "processed" / "game_region.kml")
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    text = tree.find(".//k:coordinates", ns).text
    points = [tuple(map(float, pair.split(",")[:2])) for pair in text.split()]
    return simplify(points)


def geojson_feature(geometry_type, coordinates, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": geometry_type, "coordinates": coordinates},
    }


def geometry_contains(point, geometry):
    coordinates = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        return point_in_polygon(point, coordinates[0])
    if geometry["type"] == "MultiPolygon":
        return any(point_in_polygon(point, polygon[0]) for polygon in coordinates)
    return False


def render_inline_markdown(text):
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def render_markdown(markdown):
    lines = []
    for line in markdown.splitlines():
        if line.startswith("  ") and lines and lines[-1].lstrip().startswith("- "):
            lines[-1] += " " + line.strip()
        else:
            lines.append(line)
    output = []
    paragraph = []
    list_open = False
    table_rows = []

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{render_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    def flush_table():
        if not table_rows:
            return
        header, *rows = table_rows
        output.append("<div class=\"table-wrap\"><table><thead><tr>")
        output.extend(f"<th>{render_inline_markdown(cell)}</th>" for cell in header)
        output.append("</tr></thead><tbody>")
        for row in rows:
            output.append("<tr>")
            output.extend(f"<td>{render_inline_markdown(cell)}</td>" for cell in row)
            output.append("</tr>")
        output.append("</tbody></table></div>")
        table_rows.clear()

    for line in lines + [""]:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            close_list()
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            table_rows.append(cells)
            continue
        flush_table()
        if stripped.startswith("#"):
            flush_paragraph()
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            title = stripped[level:].strip()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            output.append(
                f'<h{level} id="{slug}">{render_inline_markdown(title)}</h{level}>'
            )
        elif stripped.startswith("- "):
            flush_paragraph()
            if not list_open:
                output.append("<ul>")
                list_open = True
            output.append(f"<li>{render_inline_markdown(stripped[2:])}</li>")
        elif not stripped:
            flush_paragraph()
            close_list()
        else:
            paragraph.append(stripped)

    return "\n".join(output)


def render_rules_page(markdown):
    body = render_markdown(markdown)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>LA Special Rules | Jet Lag: Hide + Seek</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4efe5; color: #1e2630; font-family: Inter, system-ui, sans-serif; line-height: 1.55; }}
    header {{ position: sticky; top: 0; padding: 14px 20px; background: #172331; color: white; box-shadow: 0 2px 12px #0003; }}
    header a {{ color: #ffd27a; margin-right: 18px; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 24px 20px 60px; }}
    h1 {{ line-height: 1.1; }}
    h2 {{ margin-top: 36px; padding-top: 10px; border-top: 2px solid #d8cdbb; }}
    h3 {{ margin-top: 28px; }}
    a {{ color: #1261a0; }}
    li {{ margin: 7px 0; }}
    code {{ padding: 2px 4px; border-radius: 3px; background: #e8dfd1; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ padding: 9px 10px; border: 1px solid #d8cdbb; text-align: left; vertical-align: top; }}
    th {{ background: #e9dfcf; }}
  </style>
</head>
<body>
  <header><a href="./index.html">Back to map</a><a href="https://jetlag.denull.ru/en/rules/">Official rules</a></header>
  <main>{body}</main>
</body>
</html>"""


def build_data():
    boundary = load_boundary()
    divisions = json.loads(
        (REFERENCE / "processed" / "divisions.geojson").read_text(encoding="utf-8")
    )
    routes = {row["route_id"]: row for row in read_csv("routes.txt")}
    stops = read_csv("stops.txt")
    stop_to_station = {
        row["stop_id"]: row["parent_station"] or row["stop_id"] for row in stops
    }
    trip_to_route = {}
    shape_to_route = {}
    for row in read_csv("trips.txt"):
        trip_to_route[row["trip_id"]] = row["route_id"]
        shape_to_route[row["shape_id"]] = row["route_id"]

    stop_routes = defaultdict(set)
    with (GTFS / "stop_times.txt").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            station_id = stop_to_station.get(row["stop_id"], row["stop_id"])
            stop_routes[station_id].add(trip_to_route[row["trip_id"]])

    stations = []
    for row in stops:
        if row["location_type"] != "1":
            continue
        point = (float(row["stop_lon"]), float(row["stop_lat"]))
        if not point_in_polygon(point, boundary):
            continue
        if distance_to_boundary_km(point, boundary) < ZONE_KM:
            continue
        served = sorted(
            {
                routes[route_id]["route_long_name"].replace("Metro ", "")
                for route_id in stop_routes[row["stop_id"]]
            }
        )
        name = re.sub(r" Station$", "", row["stop_name"])
        if name == "Union":
            name = "Union Station"
        division = next(
            (
                feature["properties"]["name"]
                for feature in divisions["features"]
                if geometry_contains(point, feature["geometry"])
            ),
            "Boundary area",
        )
        stations.append(
            geojson_feature(
                "Point",
                list(point),
                {
                    "name": name,
                    "lines": served,
                    "division": division,
                    "stop_id": row["stop_id"],
                    "zone_m": int(ZONE_KM * 1000),
                },
            )
        )

    shapes = defaultdict(list)
    with (GTFS / "shapes.txt").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            shapes[row["shape_id"]].append(
                (int(row["shape_pt_sequence"]), [float(row["shape_pt_lon"]), float(row["shape_pt_lat"])])
            )

    lines = []
    for shape_id, points in shapes.items():
        if shape_id not in shape_to_route:
            continue
        points = [point for _, point in sorted(points)]
        if not any(point_in_polygon(point, boundary) for point in points):
            continue
        route = routes[shape_to_route[shape_id]]
        lines.append(
            geojson_feature(
                "LineString",
                simplify(points, 0.00012),
                {
                    "line": route["route_long_name"].replace("Metro ", ""),
                    "color": "#" + route["route_color"],
                },
            )
        )

    return {
        "updated": "2026-06-13",
        "station_count": len(stations),
        "boundary": geojson_feature("Polygon", [[list(p) for p in boundary]], {}),
        "stations": {"type": "FeatureCollection", "features": stations},
        "lines": {"type": "FeatureCollection", "features": lines},
        "divisions": divisions,
    }


def main():
    data = build_data()
    rules_markdown = (ROOT / "RULES_LA.md").read_text(encoding="utf-8")
    template = (ROOT / "scripts" / "map-template.html").read_text(encoding="utf-8")
    rendered = template.replace("__MAP_DATA__", json.dumps(data, separators=(",", ":")))
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "index.html").write_text(rendered, encoding="utf-8")
    (OUTPUT / "map-data.geojson.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    shutil.copyfile(ROOT / "RULES_LA.md", OUTPUT / "RULES_LA.md")
    (OUTPUT / "rules.html").write_text(
        render_rules_page(rules_markdown), encoding="utf-8"
    )
    with (OUTPUT / "station-reference.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["station", "lines", "division", "stop_id"])
        writer.writeheader()
        for feature in sorted(
            data["stations"]["features"], key=lambda x: x["properties"]["name"]
        ):
            properties = feature["properties"]
            writer.writerow(
                {
                    "station": properties["name"],
                    "lines": ", ".join(properties["lines"]),
                    "division": properties["division"],
                    "stop_id": properties["stop_id"],
                }
            )
    print(f"Built map with {data['station_count']} eligible stations.")


if __name__ == "__main__":
    main()
