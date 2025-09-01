# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jwcrypto",
# ]
# ///
import os
import sys

from jwcrypto import jwk

if os.path.exists("private.json"):
    print("private.json already exists.")
    sys.exit(0)

key = jwk.JWK.generate(kty="RSA", size=2048, use="sig")
key.kid = key.thumbprint()
data = key.export_public()
with open("public.json", "w") as f:
    f.write(data)

with open("private.json", "w") as f:
    f.write(key.export())

# For Django admin
with open("admin/private.json", "w") as f:
    f.write(key.export())
