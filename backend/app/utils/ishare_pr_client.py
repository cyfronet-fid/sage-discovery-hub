"""Client utilities for iSHARE Participant Registry discovery and login routing."""

import asyncio
import base64
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptojwt.jwk.rsa import RSAKey
from cryptojwt.jwt import JWT
from cryptojwt.key_bundle import KeyBundle
from cryptojwt.key_jar import KeyJar

from app.schemas.party_registry import PartyListItem, PartyListResponse, PartyListSource
from app.settings import GlobalSettings

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
CERTIFICATE_PATTERN = re.compile(
    rb"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", re.DOTALL
)


class IShareConfigurationError(RuntimeError):
    """Raised when the iSHARE integration is missing local configuration."""


class IShareParticipantRegistryError(RuntimeError):
    """Raised when the Participant Registry or a participant endpoint fails."""


class IShareParticipantRegistryClient:
    """Fetch and validate parties from the iSHARE Participant Registry."""

    def __init__(self, settings: GlobalSettings):
        self._settings = settings
        self._base_url = str(settings.ISHARE_PR_BASE_URL)
        self._version = settings.ISHARE_PR_VERSION.strip("/")

    async def get_connector_list(
        self, include_details: bool = True
    ) -> PartyListResponse:
        """Return validated data connectors for the configured Sage data space."""

        response = await self.get_party_list(
            role="ServiceProvider",
            data_space_id=self._settings.ISHARE_CONNECTOR_DATASPACE_ID,
            tag=self._settings.ISHARE_CONNECTOR_TAG,
            registrar_id=self._settings.ISHARE_CONNECTOR_REGISTRAR_ID,
            active_only=self._settings.ISHARE_CONNECTOR_ACTIVE_ONLY,
            capability_url_overrides=self._settings.ISHARE_CONNECTOR_CAPABILITY_URL_OVERRIDES,
            dashboard_url_overrides=self._settings.ISHARE_CONNECTOR_DASHBOARD_URL_OVERRIDES,
        )
        if self._settings.ISHARE_CONNECTOR_ACTIVE_ONLY:
            await self._refresh_connector_items_from_party_records(response.items)
        if include_details:
            await self._enrich_connector_items(response.items)
        return response

    async def get_connector_details(self, party_id: str) -> PartyListItem:
        """Return one validated connector enriched with capabilities metadata."""

        party = await self.get_party_record(party_id)
        item = self._to_party_list_item(
            party,
            role="ServiceProvider",
            data_space_id=self._settings.ISHARE_CONNECTOR_DATASPACE_ID,
            tag=self._settings.ISHARE_CONNECTOR_TAG,
            registrar_id=self._settings.ISHARE_CONNECTOR_REGISTRAR_ID,
            capability_url_overrides=(
                self._settings.ISHARE_CONNECTOR_CAPABILITY_URL_OVERRIDES
            ),
            dashboard_url_overrides=(
                self._settings.ISHARE_CONNECTOR_DASHBOARD_URL_OVERRIDES
            ),
        )
        if item is None:
            raise IShareParticipantRegistryError(
                f"Connector {party_id} is not in the validated EDC connector list"
            )
        await self._enrich_connector_items([item])
        return item

    async def get_identity_provider_list(self) -> PartyListResponse:
        """Return active identity providers."""

        return await self.get_party_list(
            role="IdentityProvider",
            active_only=self._settings.ISHARE_IDP_ACTIVE_ONLY,
            capability_url_overrides=self._settings.ISHARE_IDP_CAPABILITY_URL_OVERRIDES,
            authorize_url_overrides=self._settings.ISHARE_IDP_AUTHORIZE_URL_OVERRIDES,
        )

    async def get_party_list(
        self,
        role: str,
        data_space_id: Optional[str] = None,
        tag: Optional[str] = None,
        registrar_id: Optional[str] = None,
        active_only: bool = True,
        capability_url_overrides: Optional[dict[str, str]] = None,
        authorize_url_overrides: Optional[dict[str, str]] = None,
        dashboard_url_overrides: Optional[dict[str, str]] = None,
    ) -> PartyListResponse:
        """Return validated parties that match the requested filters."""

        access_token = await self._get_access_token()
        filters = self._build_filters(
            role=role,
            data_space_id=data_space_id,
            tag=tag,
            registrar_id=registrar_id,
            active_only=active_only,
        )
        parties_payload = await self._get_parties(access_token, filters)
        parties = self._extract_party_list(parties_payload)
        items = [
            item
            for item in (
                self._to_party_list_item(
                    party,
                    role=role,
                    data_space_id=data_space_id,
                    tag=tag,
                    registrar_id=registrar_id,
                    capability_url_overrides=capability_url_overrides,
                    authorize_url_overrides=authorize_url_overrides,
                    dashboard_url_overrides=dashboard_url_overrides,
                )
                for party in parties
            )
            if item is not None
        ]

        return PartyListResponse(
            items=items,
            source=PartyListSource(
                participant_registry_id=(
                    self._settings.ISHARE_PR_PARTICIPANT_REGISTRY_ID
                ),
                parties_endpoint=self._parties_endpoint,
                filters=filters,
            ),
        )

    async def get_party_record(self, party_id: str) -> dict[str, Any]:
        """Return a single validated party record from the registry."""

        access_token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(
            timeout=self._settings.ISHARE_PR_TIMEOUT_SECONDS
        ) as client:
            response = None
            last_error = None
            for parties_endpoint in self._parties_endpoints:
                try:
                    response = await client.get(
                        urljoin(parties_endpoint + "/", party_id), headers=headers
                    )
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as err:
                    if err.response.status_code in (404, 500):
                        last_error = err
                        continue
                    raise IShareParticipantRegistryError(
                        f"Could not fetch iSHARE party {party_id}: {err}"
                    ) from err
                except httpx.HTTPError as err:
                    raise IShareParticipantRegistryError(
                        f"Could not fetch iSHARE party {party_id}: {err}"
                    ) from err

        if response is None:
            raise IShareParticipantRegistryError(
                f"Could not fetch iSHARE party {party_id}: {last_error}"
            )

        payload = self._decode_http_json_or_jwt(
            response, expected_issuer=self._participant_registry_expected_issuer
        )
        if isinstance(payload, dict):
            for key in ("party_info", "party", "data", "payload"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    payload = nested
        if not isinstance(payload, dict):
            raise IShareParticipantRegistryError(
                f"Participant Registry returned invalid payload for party {party_id}"
            )
        return payload

    async def get_capabilities(
        self, capability_url: str, expected_issuer: str
    ) -> dict[str, Any]:
        """Fetch and verify a participant capabilities document."""

        async with httpx.AsyncClient(
            timeout=self._settings.ISHARE_CAPABILITIES_TIMEOUT_SECONDS
        ) as client:
            try:
                response = await client.get(
                    capability_url, headers={"Accept": "application/json"}
                )
                response.raise_for_status()
            except httpx.HTTPError as err:
                raise IShareParticipantRegistryError(
                    f"Could not fetch capabilities from {capability_url}: {err}"
                ) from err

        payload = self._decode_http_json_or_jwt(
            response, expected_issuer=expected_issuer
        )
        if not isinstance(payload, dict):
            raise IShareParticipantRegistryError(
                f"Capabilities response from {capability_url} was not an object"
            )
        return payload

    async def exchange_authorization_code(
        self,
        token_url: str,
        code: str,
        redirect_uri: str,
        audience: str,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens using iSHARE client assertion."""

        data = {
            "grant_type": "authorization_code",
            "client_id": self._settings.ISHARE_CLIENT_ID,
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": self._create_client_assertion(audience),
            "redirect_uri": redirect_uri,
            "code": code,
        }

        async with httpx.AsyncClient(
            timeout=self._settings.ISHARE_CAPABILITIES_TIMEOUT_SECONDS
        ) as client:
            try:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
            except httpx.HTTPError as err:
                raise IShareParticipantRegistryError(
                    f"Could not exchange authorization code at {token_url}: {err}"
                ) from err

        try:
            return response.json()
        except ValueError as err:
            raise IShareParticipantRegistryError(
                f"Token endpoint {token_url} did not return JSON"
            ) from err

    def build_authorization_request_jwt(
        self,
        idp_party_id: str,
        idp_public_key: RSAPublicKey,
        redirect_uri: str,
        state: str,
        nonce: str,
        scope: Optional[str] = None,
        acr_values: Optional[str] = None,
        language: str = "en",
    ) -> str:
        """Build the signed-and-encrypted iSHARE request JWT for /connect/authorize."""

        key_jar = KeyJar()
        signing_bundle = KeyBundle()
        signing_bundle.append(
            RSAKey(
                priv_key=self._private_key(),
                use="sig",
                x5c=self._certificate_chain_x5c(),
            )
        )
        key_jar.add_kb("", signing_bundle)

        encryption_bundle = KeyBundle()
        encryption_bundle.append(RSAKey(pub_key=idp_public_key, use="enc"))
        key_jar.add_kb(idp_party_id, encryption_bundle)

        jwt = JWT(
            key_jar=key_jar,
            iss=self._settings.ISHARE_CLIENT_ID or "",
            lifetime=30,
            sign=True,
            sign_alg="RS256",
            encrypt=True,
            enc_alg="RSA-OAEP",
            enc_enc="A256GCM",
        )
        payload = {
            "sub": "urn:TBD",
            "response_type": "code",
            "client_id": self._settings.ISHARE_CLIENT_ID,
            "scope": scope or self._settings.ISHARE_AUTHORIZE_SCOPE,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "acr_values": acr_values or self._settings.ISHARE_AUTHORIZE_ACR_VALUES,
            "language": language,
            "jti": str(uuid.uuid4()),
        }
        return jwt.pack(payload=payload, recv=idp_party_id, aud=[idp_party_id])

    def build_capabilities_token(self, capabilities_info: dict[str, Any]) -> str:
        """Build a signed iSHARE capabilities token for this portal."""

        now = int(time.time())
        header = {
            "alg": "RS256",
            "typ": "JWT",
            "x5c": self._certificate_chain_x5c(),
        }
        payload = {
            "sub": self._settings.ISHARE_CLIENT_ID,
            "nbf": now,
            "iss": self._settings.ISHARE_CLIENT_ID,
            "exp": now + 30,
            "iat": now,
            "capabilities_info": capabilities_info,
            "jti": str(uuid.uuid4()),
        }

        signing_input = (
            f"{self._b64url_json(header)}.{self._b64url_json(payload)}".encode()
        )
        signature = self._private_key().sign(
            signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{signing_input.decode()}.{self._b64url(signature)}"

    def extract_associated_idp_party_id(
        self, capabilities_payload: dict[str, Any]
    ) -> str:
        """Extract the associated IDP party id from capabilities metadata."""

        capabilities_info = capabilities_payload.get("capabilities_info")
        if not isinstance(capabilities_info, dict):
            raise IShareParticipantRegistryError(
                "Capabilities response does not contain capabilities_info"
            )

        identifier = self._settings.ISHARE_ASSOCIATED_IDP_IDENTIFIER
        services = []
        for key in ("publicServices", "restrictedServices"):
            value = capabilities_info.get(key)
            if isinstance(value, list):
                services.extend(item for item in value if isinstance(item, dict))

        for service in services:
            if self._first_string(service, ("identifier",)) != identifier:
                continue
            status = self._first_string(service, ("status",))
            if status is not None and status.lower() != "active":
                continue
            party_id = self._first_string(service, ("partyId", "party_id"))
            if party_id:
                return party_id
            auth_registry = service.get("authRegistry")
            if isinstance(auth_registry, dict):
                party_id = self._first_string(auth_registry, ("partyId", "party_id"))
                if party_id:
                    return party_id

        for key in ("associatedIdp", "associated_idp", "associatedIdP"):
            value = capabilities_info.get(key)
            if isinstance(value, dict):
                status = self._first_string(value, ("status",))
                if status is not None and status.lower() != "active":
                    continue
                party_id = self._first_string(value, ("partyId", "party_id"))
                if party_id:
                    return party_id
            elif isinstance(value, str) and value:
                return value

        raise IShareParticipantRegistryError(
            "Capabilities response does not declare an active associated IDP"
        )

    def resolve_service_endpoint(
        self, capabilities_payload: dict[str, Any], endpoint_hint: str
    ) -> Optional[str]:
        """Resolve an endpoint URL from capabilities metadata using heuristics."""

        capabilities_info = capabilities_payload.get("capabilities_info")
        if not isinstance(capabilities_info, dict):
            return None

        services = []
        for key in ("publicServices", "restrictedServices"):
            value = capabilities_info.get(key)
            if isinstance(value, list):
                services.extend(item for item in value if isinstance(item, dict))
        services.extend(self._supported_feature_entries(capabilities_info))

        normalized_hint = endpoint_hint.lower()
        for service in services:
            status = self._first_string(service, ("status",))
            if status is not None and status.lower() != "active":
                continue
            endpoint_url = self._first_string(
                service, ("endpointURL", "endpointUrl", "url")
            )
            identifier = self._first_string(service, ("identifier", "id")) or ""
            title = self._first_string(service, ("title", "feature")) or ""
            haystack = " ".join([identifier.lower(), title.lower(), endpoint_url or ""])
            if normalized_hint in haystack:
                return endpoint_url
            if normalized_hint == "authorize" and endpoint_url:
                if (
                    "/connect/authorize" in endpoint_url
                    or "/connect/authorise" in endpoint_url
                ):
                    return endpoint_url
            if normalized_hint == "token" and endpoint_url:
                if "/connect/token" in endpoint_url:
                    return endpoint_url

        return None

    def extract_ishare_roles(self, capabilities_payload: dict[str, Any]) -> list[str]:
        """Extract iSHARE roles declared by a capabilities response."""

        capabilities_info = capabilities_payload.get("capabilities_info")
        if not isinstance(capabilities_info, dict):
            return []

        roles = capabilities_info.get("ishare_roles")
        if isinstance(roles, dict):
            roles = [roles]
        if isinstance(roles, str):
            roles = [roles]
        if not isinstance(roles, list):
            return []

        result: list[str] = []
        seen = set()
        for role in roles:
            value = role if isinstance(role, str) else None
            if isinstance(role, dict):
                value = self._first_string(role, ("role", "roleId", "name", "value"))
            if not value:
                continue
            normalized = self._normalize_role(value)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(value)
        return result

    def idp_public_key_from_party(self, party: dict[str, Any]) -> RSAPublicKey:
        """Extract the public key used to encrypt requests to the IDP."""

        certificates = party.get("certificates")
        if not isinstance(certificates, list):
            raise IShareParticipantRegistryError(
                f"IDP {party.get('party_id') or party.get('id')} does not expose certificates"
            )

        for certificate_entry in certificates:
            if not isinstance(certificate_entry, dict):
                continue
            x5c = certificate_entry.get("x5c")
            if not isinstance(x5c, str) or not x5c:
                continue
            certificate = x509.load_der_x509_certificate(base64.b64decode(x5c))
            public_key = certificate.public_key()
            if isinstance(public_key, RSAPublicKey):
                return public_key

        raise IShareParticipantRegistryError(
            f"IDP {party.get('party_id') or party.get('id')} does not expose an RSA certificate"
        )

    async def _get_access_token(self) -> str:
        self._ensure_configured()
        assertion = self._create_client_assertion(
            self._settings.ISHARE_PR_AUDIENCE
            or self._settings.ISHARE_PR_PARTICIPANT_REGISTRY_ID
        )
        data = {
            "grant_type": "client_credentials",
            "scope": "iSHARE",
            "client_id": self._settings.ISHARE_CLIENT_ID,
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        }

        async with httpx.AsyncClient(
            timeout=self._settings.ISHARE_PR_TIMEOUT_SECONDS
        ) as client:
            response = None
            last_error = None
            for token_endpoint in self._token_endpoints:
                try:
                    response = await client.post(token_endpoint, data=data)
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as err:
                    if err.response.status_code == 404:
                        last_error = err
                        continue
                    raise IShareParticipantRegistryError(
                        f"Could not get iSHARE access token: {err}"
                    ) from err
                except httpx.HTTPError as err:
                    raise IShareParticipantRegistryError(
                        f"Could not get iSHARE access token: {err}"
                    ) from err

        if response is None:
            raise IShareParticipantRegistryError(
                f"Could not get iSHARE access token: {last_error}"
            )

        try:
            payload = response.json()
            access_token = payload["access_token"]
        except (KeyError, ValueError, TypeError) as err:
            raise IShareParticipantRegistryError(
                "Participant Registry token response did not contain access_token"
            ) from err

        return access_token

    async def _get_parties(self, access_token: str, filters: dict[str, str]) -> Any:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(
            timeout=self._settings.ISHARE_PR_TIMEOUT_SECONDS
        ) as client:
            response = None
            last_error = None
            for parties_endpoint in self._parties_endpoints:
                try:
                    response = await client.get(
                        parties_endpoint, params=filters, headers=headers
                    )
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as err:
                    if err.response.status_code in (404, 500):
                        last_error = err
                        continue
                    raise IShareParticipantRegistryError(
                        f"Could not fetch iSHARE parties: {err}"
                    ) from err
                except httpx.HTTPError as err:
                    raise IShareParticipantRegistryError(
                        f"Could not fetch iSHARE parties: {err}"
                    ) from err

        if response is None:
            raise IShareParticipantRegistryError(
                f"Could not fetch iSHARE parties: {last_error}"
            )

        return self._decode_http_json_or_jwt(
            response, expected_issuer=self._participant_registry_expected_issuer
        )

    def _build_filters(
        self,
        role: str,
        data_space_id: Optional[str] = None,
        tag: Optional[str] = None,
        registrar_id: Optional[str] = None,
        active_only: bool = True,
    ) -> dict[str, str]:
        filters = {self._settings.ISHARE_IDP_ROLE_PARAM: role}
        if data_space_id:
            filters["dataSpaceID"] = data_space_id
        if tag:
            filters["tags"] = tag
        if registrar_id:
            filters["registarSatelliteID"] = registrar_id
        if active_only:
            filters["active_only"] = "true"
        return filters

    def _create_client_assertion(self, audience: str) -> str:
        now = int(time.time())
        header = {
            "alg": "RS256",
            "typ": "JWT",
            "x5c": self._certificate_chain_x5c(),
        }
        payload = {
            "iss": self._settings.ISHARE_CLIENT_ASSERTION_ISS
            or self._settings.ISHARE_CLIENT_ID,
            "sub": self._settings.ISHARE_CLIENT_ASSERTION_SUB
            or self._settings.ISHARE_CLIENT_ID,
            "aud": audience,
            "jti": str(uuid.uuid4()),
            "exp": now + 30,
            "iat": now,
        }

        signing_input = (
            f"{self._b64url_json(header)}.{self._b64url_json(payload)}".encode()
        )
        signature = self._private_key().sign(
            signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{signing_input.decode()}.{self._b64url(signature)}"

    def _decode_http_json_or_jwt(
        self, response: httpx.Response, expected_issuer: Optional[str]
    ) -> Any:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            return self._decode_embedded_token(payload, expected_issuer=expected_issuer)

        text = response.text.strip()
        if self._looks_like_jwt(text):
            return self._decode_signed_jwt(text, expected_issuer=expected_issuer)

        try:
            return self._decode_embedded_token(
                json.loads(text), expected_issuer=expected_issuer
            )
        except ValueError as err:
            raise IShareParticipantRegistryError(
                "Participant response was not JSON or JWT"
            ) from err

    def _decode_signed_jwt(
        self, token: str, expected_issuer: Optional[str] = None
    ) -> Any:
        header_segment, payload_segment, signature_segment = token.split(".")
        header = json.loads(self._b64url_decode(header_segment))
        payload = json.loads(self._b64url_decode(payload_segment))
        signature = self._b64url_decode(signature_segment)
        signing_input = f"{header_segment}.{payload_segment}".encode()

        alg_to_hash = {
            "RS256": hashes.SHA256(),
            "RS384": hashes.SHA384(),
            "RS512": hashes.SHA512(),
        }
        algorithm = header.get("alg")
        if algorithm not in alg_to_hash:
            raise IShareParticipantRegistryError(
                f"Unsupported JWT algorithm: {algorithm}"
            )

        x5c = header.get("x5c")
        if not x5c:
            raise IShareParticipantRegistryError("JWT response does not contain x5c")

        try:
            certificate = x509.load_der_x509_certificate(base64.b64decode(x5c[0]))
            certificate.public_key().verify(
                signature,
                signing_input,
                padding.PKCS1v15(),
                alg_to_hash[algorithm],
            )
        except (InvalidSignature, ValueError) as err:
            raise IShareParticipantRegistryError(
                "JWT response signature is invalid"
            ) from err
        self._validate_jwt_payload(payload, expected_issuer=expected_issuer)
        return payload

    def _validate_jwt_payload(
        self, payload: dict[str, Any], expected_issuer: Optional[str] = None
    ) -> None:
        now = int(time.time())
        expires_at = payload.get("exp")
        not_before = payload.get("nbf")
        issuer = payload.get("iss")

        try:
            expires_at_int = int(expires_at) if expires_at is not None else None
            not_before_int = int(not_before) if not_before is not None else None
        except (TypeError, ValueError) as err:
            raise IShareParticipantRegistryError(
                "JWT response has invalid time claims"
            ) from err

        if expires_at_int is not None and expires_at_int < now:
            raise IShareParticipantRegistryError("JWT response is expired")
        if not_before_int is not None and not_before_int > now:
            raise IShareParticipantRegistryError("JWT response is not valid yet")
        if expected_issuer and issuer and issuer != expected_issuer:
            raise IShareParticipantRegistryError(
                f"JWT response has unexpected issuer: {issuer}"
            )

    def _extract_party_list(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            raise IShareParticipantRegistryError(
                "Participant Registry response does not contain party objects"
            )

        payload = self._decode_embedded_token(payload)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            raise IShareParticipantRegistryError(
                "Participant Registry response does not contain party objects"
            )

        for key in ("parties", "parties_info", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._extract_party_list(value)
                return nested

        if any(key in payload for key in ("partyId", "party_id", "id")):
            return [payload]

        nested_payload = payload.get("payload")
        if nested_payload is not None:
            return self._extract_party_list(nested_payload)

        raise IShareParticipantRegistryError(
            "Participant Registry response does not include a party list"
        )

    def _to_party_list_item(
        self,
        party: dict[str, Any],
        role: str,
        data_space_id: Optional[str] = None,
        tag: Optional[str] = None,
        registrar_id: Optional[str] = None,
        capability_url_overrides: Optional[dict[str, str]] = None,
        authorize_url_overrides: Optional[dict[str, str]] = None,
        dashboard_url_overrides: Optional[dict[str, str]] = None,
    ) -> Optional[PartyListItem]:
        if not self._is_active(party):
            return None
        if not self._has_current_role(party, role):
            return None
        if data_space_id and not self._has_dataspace(party, data_space_id):
            return None
        if tag and not self._has_tag(party, tag):
            return None
        if registrar_id and not self._has_registrar(party, registrar_id):
            return None

        party_id = self._first_string(
            party, ("partyId", "party_id", "id", "did", "participantId")
        )
        if party_id is None:
            return None

        capability_url = (
            (capability_url_overrides or {}).get(party_id)
            or self._first_string(
                party,
                (
                    "capabilityUrl",
                    "capabilitiesUrl",
                    "capability_url",
                    "capabilities_endpoint",
                ),
            )
            or None
        )
        authorize_url = (authorize_url_overrides or {}).get(party_id)
        dashboard_url = (dashboard_url_overrides or {}).get(party_id)

        return PartyListItem(
            party_id=party_id,
            name=self._first_string(
                party, ("name", "partyName", "party_name", "legalName")
            ),
            role=role,
            status="Active",
            capability_url=capability_url if capability_url else None,
            data_space_id=(
                data_space_id if data_space_id else self._first_dataspace_id(party)
            ),
            tag=tag if tag else self._first_tag(party),
            authorize_url=authorize_url,
            dashboard_url=dashboard_url,
        )

    async def _enrich_connector_items(self, items: list[PartyListItem]) -> None:
        await asyncio.gather(
            *(self._enrich_connector_item(item) for item in items if item.capability_url)
        )

    async def _enrich_connector_item(self, item: PartyListItem) -> None:
        try:
            capabilities = await self.get_capabilities(
                item.capability_url, expected_issuer=item.party_id
            )
        except IShareParticipantRegistryError:
            return
        item.ishare_roles = self.extract_ishare_roles(capabilities)
        item.dashboard_url = item.dashboard_url or self.resolve_service_endpoint(
            capabilities, "dashboard"
        )

    async def _refresh_connector_items_from_party_records(
        self, items: list[PartyListItem]
    ) -> None:
        refreshed_items = await asyncio.gather(
            *(self._refresh_connector_item_from_party_record(item) for item in items)
        )
        items[:] = [item for item in refreshed_items if item is not None]

    async def _refresh_connector_item_from_party_record(
        self, item: PartyListItem
    ) -> Optional[PartyListItem]:
        try:
            party = await self.get_party_record(item.party_id)
        except IShareParticipantRegistryError:
            return item

        return self._to_party_list_item(
            party,
            role=item.role,
            data_space_id=self._settings.ISHARE_CONNECTOR_DATASPACE_ID,
            tag=self._settings.ISHARE_CONNECTOR_TAG,
            registrar_id=self._settings.ISHARE_CONNECTOR_REGISTRAR_ID,
            capability_url_overrides=(
                self._settings.ISHARE_CONNECTOR_CAPABILITY_URL_OVERRIDES
            ),
            dashboard_url_overrides=(
                self._settings.ISHARE_CONNECTOR_DASHBOARD_URL_OVERRIDES
            ),
        )

    @staticmethod
    def _supported_feature_entries(
        capabilities_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        supported_versions = capabilities_info.get("supported_versions")
        if not isinstance(supported_versions, list):
            return []

        entries: list[dict[str, Any]] = []
        for version in supported_versions:
            if not isinstance(version, dict):
                continue
            supported_features = version.get("supported_features")
            if not isinstance(supported_features, list):
                continue
            for feature_group in supported_features:
                if not isinstance(feature_group, dict):
                    continue
                for key in ("public", "restricted", "private"):
                    value = feature_group.get(key)
                    if isinstance(value, list):
                        entries.extend(
                            item for item in value if isinstance(item, dict)
                        )
        return entries

    def _is_active(self, party: dict[str, Any]) -> bool:
        status = self._first_string(party, ("status", "state"))
        if status is not None:
            return status.lower() == "active"

        adherence = party.get("adherence")
        if isinstance(adherence, dict):
            status = self._first_string(adherence, ("status", "state"))
            if status is not None:
                return status.lower() == "active"

        active = party.get("active")
        if isinstance(active, bool):
            return active

        return False

    def _has_current_role(self, party: dict[str, Any], expected_role: str) -> bool:
        roles = party.get("roles") or party.get("participantRoles") or []
        if isinstance(roles, dict):
            roles = [roles]
        if isinstance(roles, str):
            roles = [roles]

        for role in roles:
            if self._role_name(role) != self._normalize_role(expected_role):
                continue
            if isinstance(role, dict) and not self._role_is_current(role):
                continue
            return True

        return False

    def _has_dataspace(self, party: dict[str, Any], data_space_id: str) -> bool:
        agreements = party.get("agreements") or []
        if not isinstance(agreements, list):
            return False

        normalized_id = data_space_id.lower()
        for agreement in agreements:
            if not isinstance(agreement, dict):
                continue
            agreement_data_space_id = self._first_string(
                agreement, ("dataspace_id", "dataSpaceID", "data_space_id")
            )
            if (
                agreement_data_space_id
                and agreement_data_space_id.lower() == normalized_id
            ):
                return True
        return False

    def _has_tag(self, party: dict[str, Any], expected_tag: str) -> bool:
        additional_info = party.get("additional_info")
        if not isinstance(additional_info, dict):
            return False

        tags = additional_info.get("tags")
        if isinstance(tags, str):
            normalized_tags = {
                tag.strip().lower() for tag in re.split(r"[,;\s]+", tags) if tag.strip()
            }
            return expected_tag.lower() in normalized_tags
        if isinstance(tags, list):
            normalized_tags = {
                str(tag).strip().lower() for tag in tags if str(tag).strip()
            }
            return expected_tag.lower() in normalized_tags
        return False

    def _has_registrar(self, party: dict[str, Any], expected_registrar_id: str) -> bool:
        registrar_id = self._first_string(
            party,
            ("registrar_id", "registrarId", "registrarID", "registarSatelliteID"),
        )
        if not registrar_id:
            return False
        return registrar_id.lower() == expected_registrar_id.lower()

    def _first_dataspace_id(self, party: dict[str, Any]) -> Optional[str]:
        agreements = party.get("agreements") or []
        if not isinstance(agreements, list):
            return None
        for agreement in agreements:
            if not isinstance(agreement, dict):
                continue
            data_space_id = self._first_string(
                agreement, ("dataspace_id", "dataSpaceID", "data_space_id")
            )
            if data_space_id:
                return data_space_id
        return None

    def _first_tag(self, party: dict[str, Any]) -> Optional[str]:
        additional_info = party.get("additional_info")
        if not isinstance(additional_info, dict):
            return None
        tags = additional_info.get("tags")
        if isinstance(tags, str) and tags.strip():
            return tags.strip()
        return None

    def _role_is_current(self, role: dict[str, Any]) -> bool:
        today = date.today()
        starts_at = self._parse_date(
            self._first_string(
                role, ("startDate", "start_date", "validFrom", "enabled_from")
            )
        )
        ends_at = self._parse_date(
            self._first_string(role, ("endDate", "end_date", "validUntil"))
        )

        if starts_at is not None and starts_at > today:
            return False
        if ends_at is not None and ends_at < today:
            return False
        return True

    def _role_name(self, role: Any) -> Optional[str]:
        if isinstance(role, str):
            return self._normalize_role(role)
        if isinstance(role, dict):
            value = self._first_string(role, ("role", "roleId", "name", "value"))
            if value is not None:
                return self._normalize_role(value)
        return None

    def _private_key(self) -> RSAPrivateKey:
        path = self._required_path(
            self._settings.ISHARE_PRIVATE_KEY_PATH, "ISHARE_PRIVATE_KEY_PATH"
        )
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, RSAPrivateKey):
            raise IShareConfigurationError(
                "ISHARE_PRIVATE_KEY_PATH must point to an RSA private key"
            )
        return key

    def _certificate_chain_x5c(self) -> list[str]:
        path = self._required_path(
            self._settings.ISHARE_CERTIFICATE_CHAIN_PATH,
            "ISHARE_CERTIFICATE_CHAIN_PATH",
        )
        pem_data = path.read_bytes()
        certificates = [
            b"-----BEGIN CERTIFICATE-----"
            + match.group(1)
            + b"-----END CERTIFICATE-----"
            for match in CERTIFICATE_PATTERN.finditer(pem_data)
        ]
        if not certificates:
            raise IShareConfigurationError(
                "ISHARE_CERTIFICATE_CHAIN_PATH must contain at least one PEM certificate"
            )

        return [
            base64.b64encode(
                x509.load_pem_x509_certificate(certificate).public_bytes(
                    serialization.Encoding.DER
                )
            ).decode()
            for certificate in certificates
        ]

    def _required_path(self, value: Optional[str], env_name: str) -> Path:
        if not value:
            raise IShareConfigurationError(f"{env_name} is not configured")
        path = Path(value).expanduser()
        if not path.exists():
            raise IShareConfigurationError(f"{env_name} does not exist: {path}")
        return path

    def _ensure_configured(self) -> None:
        if not self._settings.ISHARE_CLIENT_ID:
            raise IShareConfigurationError("ISHARE_CLIENT_ID is not configured")
        self._required_path(
            self._settings.ISHARE_PRIVATE_KEY_PATH, "ISHARE_PRIVATE_KEY_PATH"
        )
        self._required_path(
            self._settings.ISHARE_CERTIFICATE_CHAIN_PATH,
            "ISHARE_CERTIFICATE_CHAIN_PATH",
        )

    @property
    def connector_return_url(self) -> str:
        return urljoin(
            self._settings.BACKEND_BASE_URL, "/api/web/auth/connectors/return"
        )

    @property
    def _token_endpoint(self) -> str:
        return urljoin(self._base_url, f"{self._version}/connect/token")

    @property
    def _token_endpoints(self) -> list[str]:
        endpoints = [
            urljoin(self._base_url, f"{self._version}/connect/token"),
            urljoin(self._base_url, "connect/token"),
        ]
        return list(dict.fromkeys(endpoints))

    @property
    def _parties_endpoint(self) -> str:
        return urljoin(self._base_url, f"{self._version}/parties")

    @property
    def _parties_endpoints(self) -> list[str]:
        endpoints = [
            urljoin(self._base_url, f"{self._version}/parties"),
            urljoin(self._base_url, "parties"),
        ]
        return list(dict.fromkeys(endpoints))

    @property
    def _participant_registry_expected_issuer(self) -> str:
        return (
            self._settings.ISHARE_PR_AUDIENCE
            or self._settings.ISHARE_PR_PARTICIPANT_REGISTRY_ID
        )

    @staticmethod
    def _first_string(source: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if value is None:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @staticmethod
    def _normalize_role(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    def _decode_embedded_token(
        self, payload: Any, expected_issuer: Optional[str] = None
    ) -> Any:
        if not isinstance(payload, dict):
            return payload

        for key in ("parties_token", "party_token", "capabilities_token", "jwt"):
            token = payload.get(key)
            if isinstance(token, str) and self._looks_like_jwt(token):
                return self._decode_signed_jwt(token, expected_issuer=expected_issuer)

        return payload

    @staticmethod
    def _looks_like_jwt(value: str) -> bool:
        return len(value.split(".")) == 3

    @staticmethod
    def _b64url_json(value: dict[str, Any]) -> str:
        return IShareParticipantRegistryClient._b64url(
            json.dumps(value, separators=(",", ":")).encode()
        )

    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        padding_length = (-len(value)) % 4
        return base64.urlsafe_b64decode(value + ("=" * padding_length))
