import argparse
from pathlib import Path

from app.db import SessionLocal
from app.services.ingest_patch import ingest_patch_payload, load_payload_from_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest normalized patch notes JSON")
    parser.add_argument("--file", required=True, help="Path to normalized patch JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    payload = load_payload_from_file(file_path)

    db = SessionLocal()
    try:
        summary = ingest_patch_payload(db, payload)
        db.commit()
        print(
            f"Ingest completed: version={summary.version}, entities={summary.entities}, changes={summary.changes}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

