"""Regression coverage for the "0 entities / No usable worksheets" bug.

Root cause: a workbook uploaded before row-level persistence existed has
Worksheet/Column rows and a preview sample, but zero rows in `records` --
the portal engine correctly treats a sheet with no rows as unusable, so
every sheet got dropped and the portal came back empty. The fix is to
detect this and transparently re-parse the preserved original file to
backfill the missing records; and if that's not possible, to fail loudly
(422) instead of silently returning a "successful" empty portal.
"""
import openpyxl
import pytest

from app.models.record import Record


@pytest.fixture
def two_sheet_xlsx(tmp_path):
    path = tmp_path / "legacy.xlsx"
    wb = openpyxl.Workbook()

    projects = wb.active
    projects.title = "Projects"
    projects.append(["Project Name", "Status", "Budget"])
    projects.append(["Alpha Tower", "In Progress", 1000])
    projects.append(["Beta Villas", "At Risk", 2000])

    tasks = wb.create_sheet("Tasks")
    tasks.append(["Task Name", "Project", "Status"])
    tasks.append(["Pour foundation", "Alpha Tower", "Open"])

    wb.save(path)
    return str(path)


def _upload(client, path, filename="legacy.xlsx"):
    with open(path, "rb") as f:
        return client.post(
            "/api/workbooks",
            files={"file": (filename, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )


def _wipe_records(client):
    """Simulate a workbook uploaded before the `records` table existed:
    Worksheet/Column metadata stays, but every persisted row is gone."""
    db = client.test_sessionmaker()
    db.query(Record).delete()
    db.commit()
    db.close()


def test_portal_self_heals_when_records_are_missing_but_file_is_intact(client, two_sheet_xlsx):
    upload = _upload(client, two_sheet_xlsx)
    workbook_id = upload.json()["id"]

    _wipe_records(client)

    # Sanity check we actually reproduced the bug precondition.
    db = client.test_sessionmaker()
    assert db.query(Record).count() == 0
    db.close()

    response = client.get(f"/api/workbooks/{workbook_id}/portal")
    assert response.status_code == 200
    config = response.json()
    assert len(config["entities"]) == 2
    assert {e["worksheet"] for e in config["entities"]} == {"Projects", "Tasks"}

    # Records should now actually be persisted, not just visible this once.
    db = client.test_sessionmaker()
    assert db.query(Record).count() > 0
    db.close()


def test_portal_rejects_empty_result_instead_of_200_with_zero_entities(client, two_sheet_xlsx, tmp_path):
    upload = _upload(client, two_sheet_xlsx)
    workbook_id = upload.json()["id"]

    _wipe_records(client)

    # Also make the original file unrecoverable, so self-heal can't kick in
    # either -- this must surface as an explicit error, never a silent
    # "successful" empty portal.
    import uuid

    from app.api.routes import portal as portal_route
    from app.models.workbook import Workbook

    db = client.test_sessionmaker()
    workbook = db.query(Workbook).filter(Workbook.id == uuid.UUID(upload.json()["id"])).first()
    stored_path = portal_route.storage.path_for(workbook.stored_path)
    db.close()
    with open(stored_path, "wb") as f:
        f.write(b"not a valid xlsx anymore")

    response = client.get(f"/api/workbooks/{workbook_id}/portal")
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "NO_USABLE_WORKSHEETS"


def test_records_endpoint_also_backfills(client, two_sheet_xlsx):
    upload = _upload(client, two_sheet_xlsx)
    workbook_id = upload.json()["id"]
    _wipe_records(client)

    response = client.get(f"/api/workbooks/{workbook_id}/worksheets/Projects/records")
    assert response.status_code == 200
    assert response.json()["total"] == 2
