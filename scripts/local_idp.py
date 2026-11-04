"""Local SYNTHETIC OIDC IdP for development/tests only (binds 127.0.0.1).

Generates an ephemeral RSA key, serves JWKS and issues RS256 tokens carrying
preprovisioned membership claims (org_id, org_role, project_roles).
Never for production; no real credentials. Usage: python scripts/local_idp.py [port]
App config: OIDC_ISSUER=http://127.0.0.1:<port> OIDC_CLIENT_ID=evf-client
"""
import json, sys, time, uuid
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.responses import JSONResponse

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "local-synthetic-1"
app = FastAPI()

def jwk():
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64
    nums = key.public_key().public_numbers()
    b64 = lambda n: base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()
    return {"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256", "n": b64(nums.n), "e": b64(nums.e)}

@app.get("/.well-known/jwks.json")
def jwks(): return {"keys": [jwk()]}

@app.post("/token")
def token(body: dict):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": "evf-client", "iat": now,
              "exp": now + int(body.get("ttl", 600)), "sub": body.get("sub", str(uuid.uuid4())),
              "org_id": body["org_id"], "org_role": body.get("org_role", "member"),
              "project_roles": body.get("project_roles", {})}
    pem = key.private_bytes(__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
                            __import__("cryptography.hazmat.primitives.serialization", fromlist=["PrivateFormat"]).PrivateFormat.PKCS8,
                            __import__("cryptography.hazmat.primitives.serialization", fromlist=["NoEncryption"]).NoEncryption())
    return {"access_token": jwt.encode(claims, pem, algorithm="RS256", headers={"kid": KID})}

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
ISSUER = f"http://127.0.0.1:{PORT}"
if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="127.0.0.1", port=PORT)
