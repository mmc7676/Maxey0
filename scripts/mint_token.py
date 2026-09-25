"""Mint a bearer token for MAXEY0_MCP_TOKEN_HASHES, or hash one already issued.

    python scripts/mint_token.py --role operator --label ci-runner
    python scripts/mint_token.py --role viewer --label dashboard --out ~/dashboard.token
    python scripts/mint_token.py --role operator --label legacy --from-file old.token

The deployment stores `sha256:<digest>:<role>:<label>`; only the caller holds
the token. That split is the point: a plaintext `MAXEY0_MCP_TOKENS` entry makes
every copy of the environment -- a backup, a support bundle, a pasted
screenshot of `.env` -- a working credential, and a digest does not.

Three modes:

- default: mint a token and print it once, labeled, with the entry to paste.
  Nothing is written anywhere.
- ``--out PATH``: mint, write the token to PATH (created owner-only where the
  platform supports it, never overwritten without ``--force``), and print only
  the entry. PATH may not be inside this repository: a token file there is one
  `git add .` from being committed.
- ``--from-file PATH``: hash a token that already exists -- the migration path
  from a plaintext entry -- and print only the entry.

Tokens are ``m0ss_`` plus 32 random bytes, base64url. The prefix is what lets
`scripts/_packaging.py` recognize one in a file about to be archived.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maxey0_ss.auth.policy import (  # noqa: E402
    LABEL_PATTERN,
    TOKEN_HASHES_VAR,
    token_hash_entry,
)
from maxey0_ss.auth.roles import ROLES  # noqa: E402

TOKEN_PREFIX = "m0ss_"
#: Bytes of randomness in a minted token. 32 is 256 bits: nothing to guess, so
#: the fast digest the deployment stores has nothing to protect against.
TOKEN_BYTES = 32
#: Below this, a token read with --from-file is hashed but flagged: a digest of
#: a short, human-chosen token can be reversed by guessing.
SHORT_TOKEN = 20


def mint() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def _label(value: str) -> str:
    if not LABEL_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be 1-64 characters of A-Z a-z 0-9 . _ - "
            "(it becomes the caller's name in logs, as bearer:<label>)")
    return value


def _inside_repository(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return resolved == ROOT or ROOT in resolved.parents


def _write_token(path: Path, token: str, *, force: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (token + "\n").encode("ascii"))
    finally:
        os.close(fd)


def _read_token(path: Path) -> str:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) != 1:
        raise ValueError(f"{path} must hold exactly one token on one line; "
                         f"it holds {len(lines)} non-empty lines")
    token = lines[0]
    if any(c.isspace() or not c.isprintable() for c in token):
        raise ValueError(f"the token in {path} contains whitespace or control "
                         f"characters, which no Authorization header can carry")
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mint_token.py",
        description=f"Mint a bearer token and its {TOKEN_HASHES_VAR} entry.")
    parser.add_argument("--role", required=True, choices=sorted(ROLES),
                        help="role the token grants")
    parser.add_argument("--label", required=True, type=_label,
                        help="caller name, unique within the deployment")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--out", type=Path, metavar="PATH",
                        help="write the minted token to PATH and print only the entry")
    source.add_argument("--from-file", type=Path, metavar="PATH",
                        help="hash the existing token in PATH instead of minting one")
    parser.add_argument("--force", action="store_true",
                        help="with --out, replace an existing file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.force and args.out is None:
        parser.error("--force only applies to --out")

    if args.from_file is not None:
        try:
            token = _read_token(args.from_file.expanduser())
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"mint_token: {exc}", file=sys.stderr)
            return 1
        if len(token) < SHORT_TOKEN:
            print(f"mint_token: this token is {len(token)} characters. Its digest "
                  f"can be reversed by guessing; mint a replacement and retire it.",
                  file=sys.stderr)
        print(token_hash_entry(token, args.role, args.label))
        return 0

    token = mint()
    entry = token_hash_entry(token, args.role, args.label)

    if args.out is not None:
        path = args.out.expanduser()
        if _inside_repository(path):
            print(f"mint_token: refusing to write a token inside the repository "
                  f"({ROOT}); choose a path outside it", file=sys.stderr)
            return 1
        try:
            _write_token(path, token, force=args.force)
        except FileExistsError:
            print(f"mint_token: {path} exists; pass --force to replace it",
                  file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"mint_token: could not write {path}: {exc}", file=sys.stderr)
            return 1
        print(f"mint_token: token written to {path}", file=sys.stderr)
        print(entry)
        return 0

    print(f"# Bearer token for {args.label!r} ({args.role}). Shown once and stored "
          f"nowhere; give it to the caller:")
    print(token)
    print(f"# {TOKEN_HASHES_VAR} entry (append to the comma-separated list):")
    print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
