from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Change, Patch, PatchEntityImpact

TEST_PATCH_VERSIONS = {"14.1", "14.2"}


def seed() -> None:
    db: Session = SessionLocal()
    try:
        # Deployment-safe behavior: remove historical demo/test patches.
        test_patches = db.execute(select(Patch).where(Patch.version.in_(TEST_PATCH_VERSIONS))).scalars().all()
        removed_versions = [patch.version for patch in test_patches]
        for patch in test_patches:
            db.execute(delete(Change).where(Change.patch_id == patch.id))
            db.execute(delete(PatchEntityImpact).where(PatchEntityImpact.patch_id == patch.id))
            db.delete(patch)

        db.commit()
        if removed_versions:
            print(f"Removed test patches: {', '.join(sorted(removed_versions))}")
        else:
            print("No test patches found. Nothing to remove.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()

