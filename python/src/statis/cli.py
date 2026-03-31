"""
statis verify <receipt_id> [--api-url URL]

Verifies a Statis receipt hash against the public verification endpoint.
No API key required.
"""
import sys
import json
import argparse
import urllib.request
import urllib.error


def verify(receipt_id: str, api_url: str = "https://api.statis.dev") -> int:
    """Returns exit code 0 if valid, 1 if tampered or not found."""
    url = f"{api_url}/receipts/{receipt_id}/verify"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Receipt '{receipt_id}' not found.", file=sys.stderr)
            return 1
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return 1

    print(f"Receipt ID:     {data['receipt_id']}")
    print(f"Action type:    {data['action_type']}")
    print(f"Tenant prefix:  {data['tenant_id_prefix']}")
    print(f"Status:         {data['status']}")
    print(f"Evaluated at:   {data['evaluated_at']}")
    print(f"Hash:           {data['hash']}")
    print(f"Hash valid:     {data['hash_valid']}")

    if data['hash_valid']:
        print("\nVERIFIED — receipt is authentic and untampered.")
        return 0
    else:
        print("\nTAMPERED — receipt hash does not match stored value.", file=sys.stderr)
        return 1


def _main_verify(args: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="statis verify", description="Verify a Statis receipt")
    parser.add_argument("receipt_id", help="Receipt ID to verify")
    parser.add_argument("--api-url", default="https://api.statis.dev", help="Statis API base URL")
    parsed = parser.parse_args(args)
    sys.exit(verify(parsed.receipt_id, parsed.api_url))


def _main_init(args: list[str]) -> None:
    from statis.cli_init import run_init_adapter

    parser = argparse.ArgumentParser(prog="statis init", description="Scaffold Statis resources")
    sub = parser.add_subparsers(dest="resource", required=True)
    adapter_p = sub.add_parser("adapter", help="Scaffold a new adapter")
    adapter_p.add_argument("--name", required=True, help="Adapter name (e.g. MyAdapter, notion)")
    adapter_p.add_argument(
        "--action-types",
        dest="action_types",
        default="",
        help="Comma-separated action types (e.g. create_record,update_record)",
    )
    parsed = parser.parse_args(args)
    sys.exit(run_init_adapter(parsed.name, parsed.action_types))


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "init":
        _main_init(argv[1:])
    else:
        # Default: verify (backward-compatible — `statis verify <id>` and `statis <id>` both work)
        if argv and argv[0] == "verify":
            argv = argv[1:]
        _main_verify(argv)


if __name__ == "__main__":
    main()
