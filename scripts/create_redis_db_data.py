import json
import os
import sys
from pprint import pprint
from typing import Any

import httpx
from jwcrypto import jwt

api_key = os.environ.get("INMOR_API_KEY")
if not api_key:
    print("Error: Set INMOR_API_KEY environment variable")
    sys.exit(1)

auth_headers = {"X-API-Key": api_key}

tmts = [
    {
        "tmtype": "https://sunet.se/does_not_exist_trustmark",
        "id": 1,
        "valid_for": 8760,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    },
    {
        "tmtype": "https://example.com/trust_mark_type",
        "id": 2,
        "valid_for": 720,
        "active": True,
        "autorenew": True,
        "renewal_time": 48,
    },
]

print("First let us create the server entity configuration")
_ = httpx.post("http://localhost:8000/api/v1/server/entity", headers=auth_headers)

print("Creating historical_keys if any")
_ = httpx.post("http://localhost:8000/api/v1/server/historical_keys", headers=auth_headers)


# Then let us create the trustmark types
for tm in tmts:
    resp = httpx.post("http://localhost:8000/api/v1/trustmarktypes", json=tm, headers=auth_headers)
    pprint(resp.json())

# Now create the Trustmarks
tms = [
    "https://fakerp0.labb.sunet.se",
    "https://fakeop0.labb.sunet.se",
    "https://fakerp1.labb.sunet.se",
    "https://localhost:8080",
]

# Because we need to skip the TA itself
subs = tms[:3]
for tm in tms:
    data: dict[str, Any] = {"tmt": 1, "domain": tm}
    resp = httpx.post("http://localhost:8000/api/v1/trustmarks", json=data, headers=auth_headers)
    pprint(resp.json())


print("--" * 30)
print("Extra trustmarks for RPs")
# One extra trustmark for only RPs
for tm in ["https://fakerp0.labb.sunet.se", "https://fakerp1.labb.sunet.se"]:
    data = {"tmt": 2, "domain": tm}
    resp = httpx.post("http://localhost:8000/api/v1/trustmarks", json=data, headers=auth_headers)
    pprint(resp.json())
print("--" * 30)

print("Now we will add the subordinates.")
for tm in subs:
    well_known = f"{tm}/.well-known/openid-federation"
    resp = httpx.get(well_known)
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))

    metadata = payload.get("metadata")
    if tm == "https://fakeop0.labb.sunet.se":
        # Only for fakerp0 we add forced_metadata
        forced_metadata = {
            "openid_provider": {
                "application_type": "mutant",
                "system": ["py", "rust"],
                "subject_types_supported": ["pairwise", "public", "e2e"],
            },
            "extra_field": "extra_value",
        }
    else:
        forced_metadata = {}

    resp = httpx.post(
        "http://localhost:8000/api/v1/subordinates",
        json={
            "entityid": tm,
            "metadata": payload["metadata"],
            "forced_metadata": forced_metadata,
            "jwks": payload["jwks"],
        },
        headers={**auth_headers, "Content-Type": "application/json", "accept": "application/json"},
    )
    print("--" * 30)
    pprint(resp.json())
