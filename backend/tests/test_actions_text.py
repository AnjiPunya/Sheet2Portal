import pytest

from app.services.actions.amounts import parse_amount
from app.services.actions.confirm import classify
from app.services.actions.messages import completed, language_of


@pytest.mark.parametrize(
    "text",
    ["yes", "Yes.", "yes please", "OK", "okay go ahead", "confirm", "Sure, do it", "అవును", "అవునండి", "సరే", "సరే చేయండి", "ఓకే", "avunu", "sare cheyyi", "సరే, confirm"],
)
def test_plain_confirmations(text):
    assert classify(text) == "confirm"


@pytest.mark.parametrize("text", ["no", "No thanks", "cancel", "cancel it", "don't", "never mind", "వద్దు", "వద్దండి", "క్యాన్సిల్", "vaddu", "ఆపండి"])
def test_plain_cancellations(text):
    assert classify(text) == "cancel"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "yes but make it 6 crore",  # correction -> the model revises the draft
        "no, the other project",
        "అవును కానీ బడ్జెట్ 6 కోట్లు",
        "don't do it yet, change the manager",
        "yes no",  # contradictory
        "approve PR-1004",  # a new request, not a confirmation
        "what is the budget",
        "ok ok ok ok ok ok ok ok",  # too long to be a plain yes
    ],
)
def test_anything_else_goes_to_the_model(text):
    assert classify(text) == "other"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("5 crore", 50_000_000),
        ("2.5 lakh", 250_000),
        ("₹40,000", 40_000),
        ("Rs. 3 cr", 30_000_000),
        ("5 కోట్లు", 50_000_000),
        ("2 లక్షలు", 200_000),
        ("12", 12),
        (7, 7),
        ("5 tonnes", "5 tonnes"),  # not an amount unit: left for validation to reject
        ("next week", "next week"),
    ],
)
def test_spoken_amounts(raw, expected):
    assert parse_amount(raw) == expected


def test_reply_language():
    assert language_of("అవును") == "te"
    assert language_of("yes") == "en"
    assert language_of("yes", hint="mixed") == "te"
    assert "సృష్టించాను" in completed("create", "Project", "Green Valley", "te")
    assert completed("approve", "Purchase Request", "PR-1004", "en") == "Done. Approved purchase request PR-1004."
