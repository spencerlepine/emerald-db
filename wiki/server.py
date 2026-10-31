from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


WIKI_DIR = Path(__file__).resolve().parent
DATABASE_DIR = WIKI_DIR.parent / "database"

# Wiki text blobs can be much larger than csv's 128 KiB default limit.
csv.field_size_limit(sys.maxsize)


def table_path(name: str) -> Path | None:
    if not name or Path(name).name != name or not name.endswith(".csv"):
        return None
    path = DATABASE_DIR / name
    return path if path.is_file() else None


def read_table(name: str) -> tuple[list[str], list[dict[str, str]]]:
    path = table_path(name)
    if path is None:
        raise FileNotFoundError(name)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames or [], list(reader)


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class WikiHandler(BaseHTTPRequestHandler):
    server_version = "EmeraldWiki/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self.handle_api(path, query)
            elif path.startswith("/database-images/"):
                self.serve_database_image(path.removeprefix("/database-images/"))
            else:
                self.serve_frontend(path)
        except (OSError, csv.Error, UnicodeError) as error:
            json_response(self, {"error": str(error)}, 500)

    def handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/tables":
            tables = []
            for file in sorted(DATABASE_DIR.glob("*.csv")):
                columns, rows = read_table(file.name)
                tables.append({"name": file.stem, "columns": columns, "count": len(rows)})
            json_response(self, {"tables": tables})
            return

        if path == "/api/facets":
            _, entities = read_table("entities.csv")
            categories: dict[str, int] = {}
            entity_types: dict[str, int] = {}
            for row in entities:
                for field, counts in (("category", categories), ("entity_type", entity_types)):
                    value = row.get(field, "").strip()
                    if value:
                        counts[value] = counts.get(value, 0) + 1
            json_response(self, {"categories": categories, "entity_types": entity_types})
            return

        if path == "/api/timeline":
            _, events = read_table("timeline_events.csv")
            events.sort(key=lambda row: int(row.get("sequence") or 0))
            json_response(self, {"events": events})
            return

        if path.startswith("/api/entity/"):
            self.entity_detail(path.removeprefix("/api/entity/"))
            return

        if path.startswith("/api/timeline/"):
            self.timeline_detail(path.removeprefix("/api/timeline/"))
            return

        if path == "/api/entities":
            self.list_entities(query)
            return

        if path.startswith("/api/table/"):
            self.list_table(path.removeprefix("/api/table/"), query)
            return

        json_response(self, {"error": "Not found"}, 404)

    @staticmethod
    def page_args(query: dict[str, list[str]]) -> tuple[str, int, int]:
        search = query.get("q", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["50"])[0]), 1), 100)
            offset = max(int(query.get("offset", ["0"])[0]), 0)
        except ValueError:
            limit, offset = 50, 0
        return search, limit, offset

    def list_entities(self, query: dict[str, list[str]]) -> None:
        columns, rows = read_table("entities.csv")
        search, limit, offset = self.page_args(query)
        category = query.get("category", [""])[0].casefold()
        entity_type = query.get("type", [""])[0].casefold()
        filtered = [
            row for row in rows
            if (not category or row.get("category", "").casefold() == category)
            and (not entity_type or row.get("entity_type", "").casefold() == entity_type)
            and (not search or any(search in value.casefold() for value in row.values() if value))
        ]
        json_response(self, {"columns": columns, "rows": filtered[offset:offset + limit], "total": len(filtered), "offset": offset, "limit": limit})

    def list_table(self, encoded_name: str, query: dict[str, list[str]]) -> None:
        name = unquote(encoded_name)
        try:
            columns, rows = read_table(f"{name}.csv")
        except FileNotFoundError:
            json_response(self, {"error": "Unknown table"}, 404)
            return
        search, limit, offset = self.page_args(query)
        if search:
            rows = [row for row in rows if any(search in value.casefold() for value in row.values() if value)]
        json_response(self, {"columns": columns, "rows": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit})

    def entity_detail(self, encoded_id: str) -> None:
        entity_id = unquote(encoded_id)
        _, entities = read_table("entities.csv")
        entity = next((row for row in entities if row.get("id") == entity_id), None)
        if entity is None:
            try:
                _, aliases = read_table("entity_aliases.csv")
            except FileNotFoundError:
                aliases = []
            canonical_id = next((row.get("entity_id") for row in aliases if row.get("alias_id") == entity_id), None)
            entity = next((row for row in entities if row.get("id") == canonical_id), None)
            if entity is None:
                json_response(self, {"error": "Entity not found"}, 404)
                return
            entity_id = entity.get("id", entity_id)

        entity_by_id = {row.get("id", ""): row for row in entities}
        _, metadata = read_table("metadata.csv")
        metadata_rows = [row for row in metadata if row.get("entity_id") == entity_id]
        _, relationships = read_table("relationships.csv")
        related = []
        for row in relationships:
            if row.get("source_id") == entity_id:
                target = entity_by_id.get(row.get("target_id", ""))
                if target:
                    related.append({"entity": target, "relationship": row.get("relationship", "")})
            elif row.get("target_id") == entity_id:
                source = entity_by_id.get(row.get("source_id", ""))
                if source:
                    related.append({"entity": source, "relationship": row.get("relationship", "")})
        for row in metadata_rows:
            target = entity_by_id.get(row.get("related_entity_id", ""))
            if target:
                related.append({"entity": target, "relationship": row.get("field", "")})

        _, links = read_table("timeline_entities.csv")
        _, events = read_table("timeline_events.csv")
        event_by_id = {row.get("id", ""): row for row in events}
        appearances = [
            {"event": event_by_id[link["event_id"]], "relationship": link.get("relationship", "")}
            for link in links
            if link.get("entity_id") == entity_id and link.get("event_id") in event_by_id
        ]
        try:
            _, image_rows = read_table("entity_images.csv")
        except FileNotFoundError:
            image_rows = []
        images = sorted(
            (row for row in image_rows if row.get("entity_id") == entity_id),
            key=lambda row: int(row.get("position") or 0),
        )
        # Keep old databases readable until they have an entity_images.csv table.
        if not images and entity.get("image_path"):
            images = [{"entity_id": entity_id, "position": "1", "path": entity["image_path"], "status": entity.get("image_status", "")}]
        json_response(self, {"entity": entity, "images": images, "metadata": metadata_rows, "related": related, "events": appearances})

    def timeline_detail(self, encoded_id: str) -> None:
        event_id = unquote(encoded_id)
        _, events = read_table("timeline_events.csv")
        event = next((row for row in events if row.get("id") == event_id), None)
        if event is None:
            json_response(self, {"error": "Timeline event not found"}, 404)
            return
        _, links = read_table("timeline_entities.csv")
        _, entities = read_table("entities.csv")
        entity_by_id = {row.get("id", ""): row for row in entities}
        appearances = [
            {"entity": entity_by_id[link["entity_id"]], "relationship": link.get("relationship", "")}
            for link in links
            if link.get("event_id") == event_id and link.get("entity_id") in entity_by_id
        ]
        json_response(self, {"event": event, "entities": appearances})

    def serve_frontend(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        requested = (WIKI_DIR / relative).resolve()
        if WIKI_DIR not in requested.parents and requested != WIKI_DIR:
            self.send_error(404)
            return
        if not requested.is_file():
            requested = WIKI_DIR / "index.html"
        if not requested.is_file():
            self.send_error(404)
            return
        body = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def serve_database_image(self, filename: str) -> None:
        image_dir = (DATABASE_DIR / "images").resolve()
        requested = (image_dir / filename).resolve()
        if Path(filename).name != filename or image_dir not in requested.parents or not requested.is_file():
            self.send_error(404)
            return
        body = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local Emerald CSV wiki.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not DATABASE_DIR.is_dir():
        parser.error(f"Database directory not found: {DATABASE_DIR}")
    server = ThreadingHTTPServer((args.host, args.port), WikiHandler)
    print(f"Emerald Wiki: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping wiki server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
