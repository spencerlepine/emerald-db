# Emerald Wiki

A standalone, read-only web frontend for the CSV database in `../database`. The Python standard library serves the app and exposes the CSVs as JSON; there are no package dependencies or generated data copies.

## Run

From the repository root:

```sh
python3 wiki/server.py
```

Open <http://127.0.0.1:8000>. Use `--port 8001` if port 8000 is already in use. The server resolves `../database` relative to `server.py`, so it can be started from any working directory.

The browser app discovers CSV files, headers, row counts, entity categories, and entity fields at runtime. Entity pages use stable URLs such as `/entity/databank%3A1-the-phantom-menace%3Acharacters%3Aadi-gallia`; timeline pages use `/timeline/phantom-menace`. The API is read-only and reflects CSV edits after the page is refreshed.

Entity images are stored in `entity_images.csv` as ordered rows containing the
entity ID, position, path, and status. Paths are relative to `database/`. Add
another row with a higher position to attach another image; entity pages show
all rows in order. The server serves files from `database/images/` through
`/database-images/<filename>`. The original image fields in `entities.csv` are
retained for compatibility.
