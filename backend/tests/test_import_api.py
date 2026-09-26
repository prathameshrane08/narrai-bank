from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import auth
from main import app
from models import Account, Transaction

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)
pytestmark = pytest.mark.usefixtures("real_auth")


@pytest.fixture
def bank(repo):
    """A Kestrel API key and a freshly provisioned pilot customer."""
    key, _ = repo.create_api_key("kestrel", "import tests")
    headers = {"X-NarrAI-API-Key": key}
    ref = f"pilot-{auth.new_api_key()[1][3:9].lower()}"  # unique per test
    response = client.put(f"/api/customers/{ref}", json={"display_name": "Pilot customer"}, headers=headers)
    assert response.json() == {"ref": ref, "created": True}
    return headers, ref


def upload(headers, ref, name):
    return client.post(f"/api/customers/{ref}/statements", content=(FIXTURES / name).read_bytes(), headers=headers)


def test_provisioning_is_idempotent(bank):
    headers, ref = bank
    again = client.put(f"/api/customers/{ref}", json={"display_name": "Pilot customer"}, headers=headers)
    assert again.json()["created"] is False


def test_camt_import_summary_and_reimport_is_safe(bank):
    headers, ref = bank
    first = upload(headers, ref, "statement.camt053.xml").json()
    assert first["format"] == "camt.053"
    assert first["account"] == "DE89 •••• •••• 3000"  # masked; the full IBAN is never stored
    assert first["imported"] == 9  # 10 booked entries minus the USD one
    assert first["skipped"] == {"not booked (pending)": 1, "reversal": 1, "currency other than EUR": 1}
    assert first["categories"]["Refunds"] == 1 and first["categories"]["Transfers"] == 1

    second = upload(headers, ref, "statement.camt053.xml").json()
    assert (second["imported"], second["duplicates"]) == (0, 9)


def test_mt940_for_the_same_account_lands_on_the_same_account(bank, repo):
    headers, ref = bank
    upload(headers, ref, "statement.camt053.xml")
    upload(headers, ref, "statement.mt940")  # same IBAN, derived from bank code + account number

    customer = repo.find_customer("kestrel", ref)
    with repo.session_factory() as session:
        accounts = session.scalar(select(func.count()).select_from(Account).where(Account.customer_id == customer.id))
        stored = session.scalars(select(Transaction.description).join(Account)
                                 .where(Account.customer_id == customer.id)).all()
    assert accounts == 1
    assert len(stored) == 9 + 5 - 1  # the salary appears in both files and is stored once
    assert not any("DE89370400440532013000" in (d or "") for d in stored)


def test_imported_customer_sees_correct_money_in_and_out(bank, repo):
    headers, ref = bank
    upload(headers, ref, "statement.camt053.xml")
    customer = repo.find_customer("kestrel", ref)
    token, _ = auth.issue_session("kestrel", customer.id)

    body = client.get("/api/dashboard?month=2026-08", headers={"Authorization": f"Bearer {token}"}).json()
    # One imported month: everything but the comparison-based story works.
    assert body["facts"] is None and body["notice"] and body["insights"] == []
    account = body["account"]
    # Money in: salary 2,850 + Zalando refund 59.90. Money out: everything else, including the
    # 200 transfer to savings (it leaves the account) and the 100 cash withdrawal.
    assert account["income"] == 2909.90
    assert account["spending"] == round(890 + 43.17 + 59.90 + 200 + 100 + 13.99 + 4.60, 2)
    assert account["balance"] == round(1250.40 + 2909.90 - account["spending"], 2)
    # Spending analytics exclude the transfer to savings and never treat the refund as spending.
    assert "Transfers" not in body["categories"] and "Refunds" not in body["categories"]
    spent_by_category = sum(row[c] for row in body["monthly_spending"] for c in body["categories"] if c in row)
    assert round(spent_by_category, 2) == round(account["spending"] - 200, 2)  # the savings transfer isn't spending
    assert client.get("/api/story?month=2026-08", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_import_errors(bank, repo):
    headers, ref = bank
    assert client.post(f"/api/customers/{ref}/statements", content=b"hello,world\n1,2\n",
                       headers=headers).status_code == 422
    assert client.post("/api/customers/nobody/statements", content=b"x", headers=headers).status_code == 404
    assert client.post(f"/api/customers/{ref}/statements", content=b"x").status_code == 401
    too_big = client.post(f"/api/customers/{ref}/statements", content=b"x" * (5 * 1024 * 1024 + 1), headers=headers)
    assert too_big.status_code == 413
    assert client.put("/api/customers/bad ref!", json={"display_name": "x"}, headers=headers).status_code == 422


def test_another_bank_cannot_import_for_this_customer(bank, repo):
    _, ref = bank
    other_key, _ = repo.create_api_key("aurelia", "other bank")
    response = client.post(f"/api/customers/{ref}/statements", content=(FIXTURES / "statement.mt940").read_bytes(),
                           headers={"X-NarrAI-API-Key": other_key})
    assert response.status_code == 404  # the customer doesn't exist at Aurelia


def test_csv_without_iban_goes_to_the_existing_account_and_says_so(bank):
    headers, ref = bank
    upload(headers, ref, "statement.camt053.xml")
    summary = upload(headers, ref, "statement-export.csv").json()
    assert summary["account"] == "DE89 •••• •••• 3000"


def test_same_booking_in_another_format_is_not_counted_twice(bank, repo):
    headers, ref = bank
    upload(headers, ref, "statement.camt053.xml")
    mt940 = upload(headers, ref, "statement.mt940").json()
    # The 31 August salary is in both files (worded differently); the 4 other MT940 bookings are new.
    assert (mt940["imported"], mt940["duplicates"]) == (4, 1)


def test_identical_bookings_in_one_file_are_all_kept(bank):
    headers, ref = bank
    two_coffees = ("Buchungstag;Beguenstigter/Zahlungspflichtiger;Verwendungszweck;Betrag\n"
                   "03.08.2026;Cafe Kranz;Kaffee;-4,60\n03.08.2026;Cafe Kranz;Kaffee;-4,60\n").encode()
    first = client.post(f"/api/customers/{ref}/statements", content=two_coffees, headers=headers).json()
    again = client.post(f"/api/customers/{ref}/statements", content=two_coffees, headers=headers).json()
    assert (first["imported"], again["imported"], again["duplicates"]) == (2, 0, 2)
