#!/usr/bin/env python3
from __future__ import annotations

import argparse
import secrets

from app.core.security import hash_service_token
from app.db.session import SessionLocal
from app.models.entities import Project, ServiceToken

ALLOWED_SCOPES = {"analysis", "delivery", "internal", "metrics", "orchestrator", "render", "scan", "worker"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a hashed API service token and print its secret once.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--scope", required=True, help="Comma-separated service scopes")
    parser.add_argument("--project-id")
    parser.add_argument("--role", default="worker")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scopes = {scope.strip() for scope in args.scope.split(",") if scope.strip()}
    unsupported = scopes - ALLOWED_SCOPES
    if not scopes or unsupported:
        raise SystemExit(f"invalid scope set; unsupported: {', '.join(sorted(unsupported)) or 'empty scope'}")
    token_value = secrets.token_urlsafe(48)
    with SessionLocal() as db:
        if args.project_id and db.get(Project, args.project_id) is None:
            raise SystemExit("project not found")
        row = ServiceToken(
            name=args.name,
            token_hash=hash_service_token(token_value),
            scope=",".join(sorted(scopes)),
            role=args.role,
            project_id=args.project_id,
        )
        db.add(row)
        db.commit()
        print(f"service_token_id={row.id}")
        print(f"service_token={token_value}")


if __name__ == "__main__":
    main()
