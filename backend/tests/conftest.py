import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient wired to an isolated in-memory SQLite DB and a temp upload dir.

    SQLite stands in for Postgres in tests because the models use SQLAlchemy's
    dialect-agnostic Uuid/JSON types -- no Postgres-only features are used.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    from app.api.routes import portal as portal_route
    from app.api.routes import workbooks as workbooks_route
    from app.services.storage.local import LocalStorageBackend

    test_storage = LocalStorageBackend(str(tmp_path / "uploads"))
    monkeypatch.setattr(workbooks_route, "storage", test_storage)
    # portal.py did `from workbooks import storage`, which bound its own
    # independent name at import time -- patching workbooks_route.storage
    # above does not cascade to it, so it needs patching separately.
    monkeypatch.setattr(portal_route, "storage", test_storage)

    test_client = TestClient(app)
    test_client.test_sessionmaker = TestSessionLocal
    with test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def multi_sheet_xlsx(tmp_path):
    path = tmp_path / "workbook.xlsx"
    wb = openpyxl.Workbook()

    projects = wb.active
    projects.title = "Projects"
    projects.append(["Project", "Budget", "Spent", "Start Date"])
    projects.append(["Website Revamp", 10000, 8000, "2024-01-15"])
    projects.append(["Mobile App", 25000, 27000, "2024-02-01"])

    tasks = wb.create_sheet("Tasks")
    tasks.append(["Task", "Project", "Done"])
    tasks.append(["Design mockups", "Website Revamp", True])
    tasks.append(["Build API", "Mobile App", False])

    wb.save(path)
    return str(path)


@pytest.fixture
def empty_sheet_xlsx(tmp_path):
    path = tmp_path / "empty.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Blank"
    wb.save(path)
    return str(path)


@pytest.fixture
def duplicate_header_xlsx(tmp_path):
    path = tmp_path / "dupes.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Name", "Name", None])
    ws.append(["Alice", "Smith", "extra"])
    wb.save(path)
    return str(path)


@pytest.fixture
def simple_csv(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Name,Age,Active\nAlice,30,true\nBob,25,false\n")
    return str(path)


@pytest.fixture
def empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    return str(path)
