import json
from pprint import pprint

import httpx
from jwcrypto import jwt

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
_ = httpx.post("http://localhost:8000/api/v1/server/entity")


# Then let us create the trustmark types
for tm in tmts:
    resp = httpx.post("http://localhost:8000/api/v1/trustmarktypes", json=tm)
    pprint(resp.json())

# Now create the Trustmarks
tms = [
    "https://fakerp0.labb.sunet.se",
    "https://fakeop0.labb.sunet.se",
    "https://fakerp1.labb.sunet.se",
    "http://localhost:8080",
]

# Because we need to skip the TA itself
subs = tms[:3]
for tm in tms:
    data = {"tmt": 1, "domain": tm}
    resp = httpx.post("http://localhost:8000/api/v1/trustmarks", json=data)
    pprint(resp.json())

print("Now we will add the subordinates.")
for tm in subs:
    well_known = f"{tm}/.well-known/openid-federation"
    resp = httpx.get(well_known)
    jwt_net: jwt.JWT = jwt.JWT.from_jose_token(resp.text)
    payload = json.loads(jwt_net.token.objects.get("payload").decode("utf-8"))

    metadata = payload.get("metadata")
    resp = httpx.post(
        "http://localhost:8000/api/v1/subordinates",
        json={
            "entityid": tm,
            "metadata": payload["metadata"],
            "forced_metadata": {},
            "jwks": payload["jwks"],
        },
        headers={"Content-Type": "application/json", "accept": "application/json"},
    )
    pprint(resp.json())
