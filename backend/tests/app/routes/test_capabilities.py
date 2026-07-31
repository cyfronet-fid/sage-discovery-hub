# pylint: disable=missing-module-docstring,missing-function-docstring
import base64
import json

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_200_OK

from app.routes import capabilities as capabilities_routes


def _b64url_json(payload: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def _decode_jwt_payload(token: str) -> dict:
    payload_segment = token.split(".")[1]
    padding_length = (-len(payload_segment)) % 4
    return json.loads(
        base64.urlsafe_b64decode(payload_segment + ("=" * padding_length))
    )


@pytest.fixture(autouse=True)
def portal_capabilities_settings(monkeypatch):
    monkeypatch.setattr(
        capabilities_routes.settings, "ISHARE_CLIENT_ID", "EU.EORI.PL10101010"
    )
    monkeypatch.setattr(capabilities_routes.settings, "ISHARE_PR_VERSION", "2.1.1")
    monkeypatch.setattr(
        capabilities_routes.settings, "UI_BASE_URL", "https://beta.catalogue.gdds.eu/"
    )


@pytest.mark.asyncio
async def test_capabilities_endpoint_returns_portal_capabilities_token(
    app: FastAPI, client: AsyncClient, monkeypatch
):
    def fake_build_capabilities_token(self, capabilities_info):
        payload = {
            "sub": "EU.EORI.PL10101010",
            "iss": "EU.EORI.PL10101010",
            "capabilities_info": capabilities_info,
        }
        return f"{_b64url_json({'alg': 'RS256'})}.{_b64url_json(payload)}.signature"

    monkeypatch.setattr(
        capabilities_routes.IShareParticipantRegistryClient,
        "build_capabilities_token",
        fake_build_capabilities_token,
    )

    response = await client.get("/capabilities")

    assert response.status_code == HTTP_200_OK
    payload = _decode_jwt_payload(response.json()["capabilities_token"])
    capabilities_info = payload["capabilities_info"]
    public_features = capabilities_info["supported_versions"][0][
        "supported_features"
    ][0]["public"]

    assert payload["sub"] == "EU.EORI.PL10101010"
    assert payload["iss"] == "EU.EORI.PL10101010"
    assert capabilities_info["party_id"] == "EU.EORI.PL10101010"
    assert capabilities_info["ishare_roles"] == [{"role": "ServiceProvider"}]
    assert public_features == [
        {
            "feature": "SAGE Portal",
            "description": "Portal for SAGE project",
            "id": "sage-portal",
            "url": "https://beta.catalogue.gdds.eu/",
        },
        {
            "feature": "capabilities",
            "description": "Retrieves iSHARE capabilities",
            "id": "capabilities",
            "url": "https://beta.catalogue.gdds.eu/capabilities",
        },
    ]
