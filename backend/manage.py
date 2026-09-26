"""Operator commands.

    python -m manage api-key create --bank kestrel --name "Kestrel mobile backend"
    python -m manage api-key list   --bank kestrel
    python -m manage api-key revoke --bank kestrel --prefix nk_AbCdEfGh
    python -m manage import --bank kestrel --customer c-1042 --file statement.xml [--name "Pilot customer 1"]
    python -m manage purge  --bank kestrel --months 24     # retention: delete older transactions
    python -m manage audit  --bank kestrel [--customer c-1042]
    python -m manage openapi                               # regenerate docs/openapi.json
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from database import make_engine, make_session_factory
from repository import Repository
from tenants import load_tenants


OPENAPI_FILE = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def months_before(start: date, months: int) -> date:
    """The first day of the month `months` months before `start`'s month."""
    total = start.year * 12 + (start.month - 1) - months
    return date(total // 12, total % 12 + 1, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="group", required=True)
    keys = sub.add_parser("api-key", help="manage a bank's API keys").add_subparsers(dest="action", required=True)

    create = keys.add_parser("create")
    create.add_argument("--bank", required=True)
    create.add_argument("--name", required=True, help="what the key is for, e.g. 'mobile backend'")
    keys.add_parser("list").add_argument("--bank", required=True)
    revoke = keys.add_parser("revoke")
    revoke.add_argument("--bank", required=True)
    revoke.add_argument("--prefix", required=True)

    importer = sub.add_parser("import", help="import a camt.053 / MT940 / CSV statement for a customer")
    importer.add_argument("--bank", required=True)
    importer.add_argument("--customer", required=True, help="the bank's id for the customer")
    importer.add_argument("--file", required=True, type=Path)
    importer.add_argument("--name", help="create the customer with this display name if missing")

    purge = sub.add_parser("purge", help="retention: delete transactions older than N months")
    purge.add_argument("--bank", required=True)
    purge.add_argument("--months", required=True, type=int)
    audit_log = sub.add_parser("audit", help="show a bank's audit log")
    audit_log.add_argument("--bank", required=True)
    audit_log.add_argument("--customer")

    sub.add_parser("openapi", help="write the API specification to docs/openapi.json")

    args = parser.parse_args(argv)
    if args.group == "openapi":
        from main import app

        OPENAPI_FILE.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote {OPENAPI_FILE}")
        return 0
    if args.bank not in load_tenants():
        print(f"Unknown bank '{args.bank}'. Known: {', '.join(load_tenants())}", file=sys.stderr)
        return 1

    repo = Repository(make_session_factory(make_engine()))
    operator = ("operator", "cli")

    if args.group == "purge":
        if args.months < 1:
            print("--months must be at least 1", file=sys.stderr)
            return 1
        cutoff = months_before(date.today(), args.months)
        removed = repo.purge(args.bank, cutoff)
        repo.audit(args.bank, *operator, "retention.purged", details={**removed, "before": cutoff.isoformat()})
        print(f"Deleted {removed['transactions']} transactions booked before {cutoff}; "
              f"{removed['expired_revocations']} expired sign-out records.")
        return 0

    if args.group == "audit":
        customer_id = None
        if args.customer:
            customer = repo.find_customer(args.bank, args.customer)
            customer_id = customer.id if customer else "none"
        for event in reversed(repo.audit_events(args.bank, customer_id, limit=200)):
            print(f"{event['at']}  {event['actor']:<24} {event['action']:<22} "
                  f"{event['customer_id'] or '-':<32} {event['details'] or ''}")
        return 0

    if args.group == "import":
        from importers import StatementError
        from importers.service import import_statement

        if args.name:
            customer, _ = repo.ensure_customer(args.bank, args.customer, args.name)
        else:
            customer = repo.find_customer(args.bank, args.customer)
        if customer is None:
            print("Unknown customer; pass --name to create it.", file=sys.stderr)
            return 1
        try:
            summary = import_statement(repo, customer, args.file.read_bytes())
        except StatementError as exc:
            print(f"Could not import: {exc}", file=sys.stderr)
            return 1
        repo.audit(args.bank, *operator, "statement.imported", customer.id,
                   details={"format": summary["format"], "imported": summary["imported"]})
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.action == "create":
        key, prefix = repo.create_api_key(args.bank, args.name)
        repo.audit(args.bank, *operator, "api_key.created", details={"prefix": prefix})
        print(f"API key for {args.bank} ({args.name}):\n\n  {key}\n")
        print("Store it in the bank's secret manager now; it cannot be shown again.")
        print(f"Identify or revoke it later by its prefix: {prefix}")
    elif args.action == "list":
        for k in repo.list_api_keys(args.bank):
            state = "revoked" if k["revoked"] else "active"
            print(f"{k['prefix']}  {state:<7}  {k['name']}  created {k['created_at']:%Y-%m-%d}  "
                  f"last used {k['last_used_at'] or 'never'}")
    elif args.action == "revoke":
        if not repo.revoke_api_key(args.bank, args.prefix):
            print("No active key with that prefix for this bank.", file=sys.stderr)
            return 1
        repo.audit(args.bank, *operator, "api_key.revoked", details={"prefix": args.prefix})
        print(f"Revoked {args.prefix}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
