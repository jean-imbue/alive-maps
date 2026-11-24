"""Alive Maps as a standalone web app, for hosting outside the workspace (Cloud in a Bottle).

The same page, assets and route engine as the workspace app, without the workspace's shell
wiring or its API-document machinery. State goes under BOTTLE_APP_DATA_DIR (or ALIVE_MAPS_DATA_DIR).
"""

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from flask import Flask, Response, abort, jsonify, request, send_file
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alive_maps.engine import RouteError, WalkingGraph, load_region, save_record, search_places

DATA_DIR = Path(os.environ.get("BOTTLE_APP_DATA_DIR") or os.environ.get("ALIVE_MAPS_DATA_DIR", "data"))
ASSETS = Path(__file__).parent / "assets"
ASSET_NAMES = {"leaflet.js", "leaflet.css", "app.js", "style.css", "ovo.woff2", "triangles.svg"}

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://tile.openstreetmap.org; "
    "object-src 'none'; base-uri 'self'; form-action 'self'"
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Location(Frozen):
    lat: float = Field(ge=-75, le=75, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    name: str = Field(default="Map pin", max_length=250)


class PlanRequest(Frozen):
    start: Location
    end: Location
    extra_minutes: int = Field(default=10, ge=0, le=30)


app = Flask("alive_maps", static_folder=None)


def error(detail: str, status: int) -> Response:
    response = jsonify(detail=detail)
    response.status_code = status
    return response


@app.after_request
def add_content_security_policy(response: Response) -> Response:
    if response.mimetype == "text/html":
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response


@app.errorhandler(RouteError)
def route_error(failure: RouteError) -> Response:
    return error(str(failure), 422)


@app.route("/")
def index() -> Response:
    return Response((ASSETS / "index.html").read_text().replace("<!--SHELL-->", ""), mimetype="text/html")


@app.route("/health")
def health() -> Response:
    return jsonify(status="ok")


@app.route("/assets/<basename>")
def asset(basename: str) -> Response:
    if basename not in ASSET_NAMES:
        abort(404)
    return send_file(ASSETS / basename)


@app.route("/api/search")
def search() -> Response:
    return jsonify(places=search_places(DATA_DIR, request.args.get("q", "").strip()))


@app.route("/api/plan", methods=["POST"])
def plan() -> Response:
    try:
        body = PlanRequest.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError:
        return error("Choose a start and an end on the map.", 422)
    start, end = (body.start.lat, body.start.lon), (body.end.lat, body.end.lon)
    record, region_id = load_region(DATA_DIR, start, end)
    result: dict[str, Any] = WalkingGraph(record["raw"]).plan(start, end, body.extra_minutes)
    identity = uuid.uuid4().hex
    response = {
        "id": identity, "region_id": region_id, "source": record["source"], "fetched_at": record["fetched_at"],
        "start": body.start.model_dump(), "end": body.end.model_dump(), **result,
    }
    save_record(DATA_DIR, "plans", identity, {"request": body.model_dump(), "response": response})
    return jsonify(response)


@app.route("/api/raw/<identity>")
def raw(identity: str) -> Response:
    if len(identity) != 24 or any(c not in "0123456789abcdef" for c in identity):
        abort(404)
    path = DATA_DIR / "regions" / f"{identity}.json"
    if not path.exists():
        abort(404)
    record = json.loads(path.read_text())
    return jsonify({key: record[key] for key in ("source", "fetched_at", "bbox", "raw")})


@app.route("/api/export/<identity>/<mode>")
def export_route(identity: str, mode: str) -> Response:
    if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
        abort(404)
    path = DATA_DIR / "plans" / f"{hashlib.sha256(identity.encode()).hexdigest()[:24]}.json"
    if not path.exists():
        abort(404)
    result = json.loads(path.read_text())["response"]
    selected = next((r for r in result["routes"] if r["id"] == mode), None)
    if selected is None:
        abort(404)
    root = ET.Element("gpx", version="1.1", creator="Alive Maps", xmlns="http://www.topografix.com/GPX/1/1")
    track = ET.SubElement(root, "trk")
    ET.SubElement(track, "name").text = f"Alive Maps: {result['start']['name']} to {result['end']['name']} ({mode})"
    segment = ET.SubElement(track, "trkseg")
    for lat, lon in selected["coordinates"]:
        ET.SubElement(segment, "trkpt", lat=str(lat), lon=str(lon))
    response = Response(ET.tostring(root, encoding="utf-8", xml_declaration=True), mimetype="application/gpx+xml")
    response.headers["Content-Disposition"] = f'attachment; filename="alive-maps-{mode}.gpx"'
    return response
