"""Operator commands.

    python -m manage api-key create --bank kestrel --name "Kestrel mobile backend"
    python -m manage api-key list   --bank kestrel
    python -m manage api-key revoke --bank kestrel --prefix nk_AbCdEfGh
"""

import argparse
import sys

from database import make_engine, make_session_factory
from repository import Repository
from tenants import load_tenants


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

    args = parser.parse_args(argv)
    if args.bank not in load_tenants():
        print(f"Unknown bank '{args.bank}'. Known: {', '.join(load_tenants())}", file=sys.stderr)
        return 1

    repo = Repository(make_session_factory(make_engine()))
    if args.action == "create":
        key, prefix = repo.create_api_key(args.bank, args.name)
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
        print(f"Revoked {args.prefix}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
