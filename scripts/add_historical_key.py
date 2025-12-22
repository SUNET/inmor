#!/usr/bin/env python3
"""
Script to add a public key JWK to the historical_keys directory.

This script takes a public key JWK JSON file, adds the current timestamp,
and optionally revocation information, then saves it to the historical_keys directory.

Per OpenID Federation spec, historical keys may include:
- revoked: Object containing revoked_at timestamp and reason (optional)
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Possible revocation reasons per OpenID Federation spec
REVOCATION_REASONS = ["unspecified", "compromised", "superseded"]


def main():
    parser = argparse.ArgumentParser(
        description="Add a public key JWK to the historical_keys directory with optional revocation info.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a key to historical_keys
  %(prog)s publickeys/mykey.json

  # Add a key marked as compromised
  %(prog)s publickeys/mykey.json --revoked compromised

  # Add a key marked as superseded
  %(prog)s publickeys/mykey.json --revoked superseded

Revocation reasons:
  unspecified  - No specific reason given for revocation
  compromised  - The key has been compromised and should not be trusted
  superseded   - The key has been replaced by a newer key
""",
    )

    parser.add_argument(
        "jwk_file",
        type=str,
        help="Path to the public key JWK JSON file",
    )

    parser.add_argument(
        "--revoked",
        type=str,
        choices=REVOCATION_REASONS,
        metavar="REASON",
        help=f"Mark the key as revoked with the given reason. Choices: {', '.join(REVOCATION_REASONS)}",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="historical_keys",
        help="Output directory for historical keys (default: historical_keys)",
    )

    args = parser.parse_args()

    # Read the input JWK file
    jwk_path = Path(args.jwk_file)
    if not jwk_path.exists():
        print(f"Error: JWK file not found: {jwk_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(jwk_path, "r") as f:
            jwk_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {jwk_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate that the JWK has a 'kid' field for the filename
    if "kid" not in jwk_data:
        print("Error: JWK must have a 'kid' field", file=sys.stderr)
        sys.exit(1)

    kid = jwk_data["kid"]
    current_time = int(time.time())

    # Add exp timestamp (when the key was retired/moved to historical)
    jwk_data["exp"] = current_time

    # Add revocation info if specified
    if args.revoked:
        jwk_data["revoked"] = {
            "revoked_at": current_time,
            "reason": args.revoked,
        }

    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the key with the kid as filename
    output_path = output_dir / f"{kid}.json"

    with open(output_path, "w") as f:
        json.dump(jwk_data, f, indent=2)

    print(f"Saved historical key to: {output_path}")
    print(f"  kid: {kid}")
    print(f"  exp: {current_time}")
    if args.revoked:
        print(f"  revoked: {args.revoked} at {current_time}")


if __name__ == "__main__":
    main()
