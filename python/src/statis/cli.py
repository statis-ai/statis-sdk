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


def main():
    parser = argparse.ArgumentParser(description="Verify a Statis receipt")
    parser.add_argument("receipt_id", help="Receipt ID to verify")
    parser.add_argument("--api-url", default="https://api.statis.dev", help="Statis API base URL")
    args = parser.parse_args()
    sys.exit(verify(args.receipt_id, args.api_url))


if __name__ == "__main__":
    main()
