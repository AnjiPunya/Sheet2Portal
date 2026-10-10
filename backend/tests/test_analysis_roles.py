from app.services.analysis.roles import infer_role
from app.services.analysis.types import FieldRole


def test_identifier_by_name_hint():
    role, confidence = infer_role("Project ID", "int", list(range(5)))
    assert role == FieldRole.IDENTIFIER
    assert confidence >= 0.8


def test_status_by_name_hint():
    role, _ = infer_role("Status", "string", ["Open", "Closed", "Open"])
    assert role == FieldRole.STATUS


def test_literal_status_outranks_priority_as_a_status_signal():
    # "Priority" matches a weaker status-family hint; a column literally
    # named "status"/"state" must win when an entity has both, since that's
    # the one a workflow (pending/approved/rejected) usually lives on.
    _, status_confidence = infer_role("Approval_Status", "string", ["Pending", "Approved"])
    _, priority_confidence = infer_role("Priority", "string", ["High", "Medium"])
    assert status_confidence > priority_confidence


def test_due_date_vs_generic_date():
    due_role, _ = infer_role("Due Date", "date", ["2024-01-01"])
    generic_role, _ = infer_role("Reported Date", "date", ["2024-01-01"])
    assert due_role == FieldRole.DUE_DATE
    assert generic_role == FieldRole.DATE


def test_budget_vs_actual_amount():
    budget_role, _ = infer_role("Budget", "int", [1000, 2000])
    actual_role, _ = infer_role("Spent", "int", [900, 1800])
    generic_role, _ = infer_role("Total Price", "int", [50, 60])
    assert budget_role == FieldRole.BUDGET_AMOUNT
    assert actual_role == FieldRole.ACTUAL_AMOUNT
    assert generic_role == FieldRole.AMOUNT


def test_quantity_and_threshold():
    qty_role, _ = infer_role("Quantity On Hand", "int", [10, 20])
    threshold_role, _ = infer_role("Reorder Level", "int", [5, 15])
    assert qty_role == FieldRole.QUANTITY
    assert threshold_role == FieldRole.THRESHOLD


def test_boolean_is_flag():
    role, confidence = infer_role("Done", "bool", [True, False])
    assert role == FieldRole.FLAG
    assert confidence > 0.8


def test_small_sample_unique_text_is_not_misread_as_identifier():
    # 3 rows, all distinct values -- should NOT be confident this is an id
    # column just because every value happens to be unique at this size.
    role, _ = infer_role("Location", "string", ["Bengaluru", "Pune", "Chennai"])
    assert role != FieldRole.IDENTIFIER


def test_large_sample_unique_text_is_identifier_fallback():
    # "Batch Tag" has no name hint at all -- only the shape of the data
    # (20 rows, all distinct) should trigger the identifier fallback.
    role, _ = infer_role("Batch Tag", "string", [f"X{i}" for i in range(20)])
    assert role == FieldRole.IDENTIFIER
