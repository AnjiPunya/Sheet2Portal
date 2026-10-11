"""Move workbooks uploaded before sign-in existed to a user's account.

Before authentication, every upload went to a shared tenant named "default".
After auth, those workbooks belong to nobody, so they're invisible. Run this
once to hand them to a signed-up user:

    .venv/bin/python scripts/claim_legacy_workbooks.py you@example.com

Non-destructive: it only changes which tenant owns each workbook.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal  # noqa: E402
from app.models import Tenant, User, Workbook  # noqa: E402

LEGACY_TENANT_NAME = "default"


def main(email: str) -> int:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if user is None:
            print(f"No user with email {email!r}. Sign up in the app first.")
            return 1
        legacy = db.query(Tenant).filter(Tenant.name == LEGACY_TENANT_NAME).first()
        if legacy is None:
            print("No legacy workbooks to claim.")
            return 0
        moved = db.query(Workbook).filter(Workbook.tenant_id == legacy.id).update({"tenant_id": user.tenant_id})
        db.commit()
        print(f"Moved {moved} workbook(s) to {user.email}.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
