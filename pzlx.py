import json
import tempfile
import zipfile
from pathlib import Path


def open_pzlx(filename):
    folder = tempfile.mkdtemp(prefix="pzlx_")
    with zipfile.ZipFile(filename) as archive:
        archive.extractall(folder)
    data = json.loads((Path(folder) / "puzzle.json").read_text(encoding="utf-8"))
    data["attachments"] = [str(Path(folder) / a) for a in data.get("attachments", [])]
    return data


def create_pzlx(puzzle_data: dict, filename, attachments: list):
    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("puzzle.json", json.dumps(puzzle_data, indent=2))
        for attachment in attachments:
            if Path(attachment).is_file():
                archive.write(attachment, arcname=f"attachments/{Path(attachment).name}")
    print(f"Created/Updated {filename}")
