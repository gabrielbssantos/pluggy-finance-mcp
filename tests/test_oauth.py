import json
import time

import httpx
import jwt
import pytest
from conftest import CLIENT_ID, ISSUER_URL, REMOTE_URL, SUBJECT, remote_settings
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from jwt.warnings import InsecureKeyLengthWarning

from pluggy_finance_mcp.auth.mcp import OidcJwtVerifier


class FakeOidcProvider:
    def __init__(self, keys):
        self.keys = keys
        self.discovery_status = 200
        self.jwks_status = 200
        self.discovery_calls = 0
        self.jwks_calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            self.discovery_calls += 1
            return httpx.Response(
                self.discovery_status,
                json={"issuer": ISSUER_URL, "jwks_uri": ISSUER_URL + "jwks"},
            )
        if request.url.path == "/.well-known/oauth-authorization-server":
            self.discovery_calls += 1
            return httpx.Response(
                200,
                json={"issuer": ISSUER_URL, "jwks_uri": ISSUER_URL + "jwks"},
            )
        if request.url.path == "/jwks":
            self.jwks_calls += 1
            return httpx.Response(
                self.jwks_status,
                json={"keys": self.keys},
                headers={"Cache-Control": "public, max-age=300"},
            )
        return httpx.Response(404)


def rsa_key(kid="key-1", key_size=2048):
    private = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    public = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private, public


def ec_key(kid="ec-key-1"):
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return private, public


def access_token(private, kid="key-1", algorithm="RS256", **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER_URL,
        "aud": REMOTE_URL,
        "sub": SUBJECT,
        "azp": CLIENT_ID,
        "scope": "openid pluggy:access",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm=algorithm, headers={"kid": kid})


async def verifier_for(provider, **settings_overrides):
    http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    verifier = OidcJwtVerifier(remote_settings(**settings_overrides), http)
    return verifier, http


async def test_valid_rsa_token_and_cached_jwks():
    private, public = rsa_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        token = access_token(private)
        first = await verifier.verify_token(token)
        second = await verifier.verify_token(token)
        assert first is not None and second is not None
        assert first.client_id == CLIENT_ID
        assert first.subject == SUBJECT
        assert first.resource == REMOTE_URL
        assert first.scopes == ["openid", "pluggy:access"]
        assert provider.discovery_calls == 1
        assert provider.jwks_calls == 1
    finally:
        await http.aclose()


async def test_client_id_claim_and_audience_list_are_supported():
    private, public = rsa_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        token = access_token(private, azp=None, client_id=CLIENT_ID, aud=[REMOTE_URL, "other"])
        assert await verifier.verify_token(token) is not None
    finally:
        await http.aclose()


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"iss": "https://attacker.example"},
        {"aud": "https://other.example/mcp"},
        {"sub": "someone-else"},
        {"azp": "unapproved-client"},
        {"scope": "openid"},
        {"exp": 1},
        {"nbf": int(time.time()) + 600},
    ],
)
async def test_rejects_invalid_claims(claim_overrides):
    private, public = rsa_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        assert await verifier.verify_token(access_token(private, **claim_overrides)) is None
    finally:
        await http.aclose()


async def test_rejects_malformed_wrong_algorithm_and_remote_key_headers():
    private, public = rsa_key()
    ec_private, _ = ec_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        wrong_algorithm = access_token(ec_private, algorithm="ES256")
        remote_key = jwt.encode(
            {
                "iss": ISSUER_URL,
                "aud": REMOTE_URL,
                "sub": SUBJECT,
                "azp": CLIENT_ID,
                "scope": "pluggy:access",
                "exp": int(time.time()) + 300,
            },
            private,
            algorithm="RS256",
            headers={"kid": "key-1", "jku": "https://attacker.example/jwks"},
        )
        assert await verifier.verify_token("not-a-jwt") is None
        assert await verifier.verify_token(wrong_algorithm) is None
        assert await verifier.verify_token(remote_key) is None
        assert provider.discovery_calls == 0
    finally:
        await http.aclose()


async def test_rejects_invalid_signature():
    _, public = rsa_key()
    attacker_private, _ = rsa_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        assert await verifier.verify_token(access_token(attacker_private)) is None
    finally:
        await http.aclose()


async def test_rejects_duplicate_key_ids_and_weak_rsa_keys():
    private, public = rsa_key()
    duplicate_provider = FakeOidcProvider([public, public])
    duplicate_verifier, duplicate_http = await verifier_for(duplicate_provider)
    try:
        assert await duplicate_verifier.verify_token(access_token(private)) is None
    finally:
        await duplicate_http.aclose()

    weak_private, weak_public = rsa_key(key_size=1024)
    weak_provider = FakeOidcProvider([weak_public])
    weak_verifier, weak_http = await verifier_for(weak_provider)
    try:
        with pytest.warns(InsecureKeyLengthWarning):
            weak_token = access_token(weak_private)
        assert await weak_verifier.verify_token(weak_token) is None
    finally:
        await weak_http.aclose()


async def test_es256_token_is_supported_when_explicitly_configured():
    private, public = ec_key()
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider, mcp_oauth_signing_algorithm="ES256")
    try:
        token = access_token(private, kid="ec-key-1", algorithm="ES256")
        assert await verifier.verify_token(token) is not None
    finally:
        await http.aclose()


async def test_rotated_kid_refreshes_once_and_key_rotation_succeeds():
    private_one, public_one = rsa_key("key-1")
    private_two, public_two = rsa_key("key-2")
    private_three, _ = rsa_key("key-3")
    provider = FakeOidcProvider([public_one])
    verifier, http = await verifier_for(provider)
    try:
        assert await verifier.verify_token(access_token(private_one)) is not None
        provider.keys = [public_two]
        assert await verifier.verify_token(access_token(private_two, kid="key-2")) is not None
        calls_after_rotation = provider.jwks_calls
        assert await verifier.verify_token(access_token(private_three, kid="key-3")) is None
        assert await verifier.verify_token(access_token(private_three, kid="key-3")) is None
        assert provider.jwks_calls == calls_after_rotation
    finally:
        await http.aclose()


async def test_unknown_kid_does_not_cause_repeated_jwks_requests():
    _, public = rsa_key("known")
    unknown_private, _ = rsa_key("unknown")
    provider = FakeOidcProvider([public])
    verifier, http = await verifier_for(provider)
    try:
        token = access_token(unknown_private, kid="unknown")
        assert await verifier.verify_token(token) is None
        assert await verifier.verify_token(token) is None
        assert provider.jwks_calls == 1
    finally:
        await http.aclose()


async def test_discovery_fallback_and_provider_failure_fail_closed():
    private, public = rsa_key()
    provider = FakeOidcProvider([public])
    provider.discovery_status = 404
    verifier, http = await verifier_for(provider)
    try:
        token = access_token(private)
        assert await verifier.verify_token(token) is not None
        assert provider.discovery_calls == 2
        verifier._keys_expires_at = 0
        provider.jwks_status = 503
        assert await verifier.verify_token(token) is None
    finally:
        await http.aclose()
