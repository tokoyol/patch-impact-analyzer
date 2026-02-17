import argparse

from app.db import SessionLocal
from app.services.embed_changes import embed_changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate embeddings for patch changes")
    parser.add_argument(
        "--patch",
        help="Optional patch version filter, e.g. 26.3",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db = SessionLocal()
    try:
        summary = embed_changes(db, patch_version=args.patch)
        db.commit()
        patch_label = args.patch if args.patch else "all"
        print(
            f"Embedding completed: patch={patch_label}, embedded={summary.embedded}, skipped={summary.skipped}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
