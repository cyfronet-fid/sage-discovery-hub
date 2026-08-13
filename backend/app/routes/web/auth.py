# pylint: disable=missing-module-docstring,broad-except,missing-function-docstring,cyclic-import,use-dict-literal
import base64
import html
import json
from urllib.parse import urlparse
import uuid
from typing import Optional
from uuid import UUID, uuid4

from cachetools import TTLCache
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette import status
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.schemas.connector_selection import (
    ConnectorSelectionRequest,
    ConnectorSelectionResponse,
    ConnectorSelectionStatusResponse,
)
from app.schemas.party_registry import PartyListItem, PartyListResponse
from app.schemas.session_data import SessionData
from app.schemas.user_info_response import UserInfoResponse
from app.settings import settings
from app.utils.cookie_validators import backend, cookie, verifier
from app.utils.ishare_pr_client import (
    IShareConfigurationError,
    IShareParticipantRegistryClient,
    IShareParticipantRegistryError,
)
from app.utils.rp_handler import get_rp_handler

router = APIRouter()
connector_login_cache = TTLCache(maxsize=100, ttl=600)


@router.get("/connectors", name="web:auth-connectors", response_model=PartyListResponse)
async def auth_connectors(include_details: bool = True):
    try:
        return await IShareParticipantRegistryClient(settings).get_connector_list(
            include_details=include_details
        )
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except IShareParticipantRegistryError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.get(
    "/connectors/{party_id}/details",
    name="web:auth-connector-details",
    response_model=PartyListItem,
)
async def auth_connector_details(party_id: str):
    try:
        return await IShareParticipantRegistryClient(settings).get_connector_details(
            party_id
        )
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except IShareParticipantRegistryError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get(
    "/identity-providers",
    name="web:auth-identity-providers",
    response_model=PartyListResponse,
)
async def auth_identity_providers():
    try:
        return await IShareParticipantRegistryClient(
            settings
        ).get_identity_provider_list()
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except IShareParticipantRegistryError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.get("/idps", name="web:auth-idps", response_model=PartyListResponse)
async def auth_idps_alias():
    return await auth_connectors()


@router.get(
    "/connectors/selection",
    response_model=ConnectorSelectionStatusResponse,
    name="web:auth-connectors-selection",
)
async def connector_selection(request: Request):
    try:
        session_id = cookie(request)
        session_data = await backend.read(session_id)
    except Exception:
        return ConnectorSelectionStatusResponse()

    return ConnectorSelectionStatusResponse(
        selected_connector_party_id=session_data.selected_connector_party_id,
        selected_connector_name=session_data.selected_connector_name,
        selected_connector_dashboard_url=session_data.selected_connector_dashboard_url,
    )


@router.post(
    "/connectors/select",
    response_model=ConnectorSelectionResponse,
    name="web:auth-connectors-select",
)
async def select_connector(
    payload: ConnectorSelectionRequest, request: Request, response: Response
):
    client = IShareParticipantRegistryClient(settings)
    try:
        connector = await client.get_connector_details(payload.party_id)
        if not connector.dashboard_url:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Connector {payload.party_id} does not have a configured dashboard URL"
                ),
            )

        session_id, session_data, should_attach_cookie = await _get_or_create_session(
            request
        )
        session_data.selected_connector_party_id = connector.party_id
        session_data.selected_connector_name = connector.name or connector.party_id
        session_data.selected_connector_dashboard_url = connector.dashboard_url
        if should_attach_cookie:
            await backend.create(session_id, session_data)
        else:
            await backend.update(session_id, session_data)
        result = ConnectorSelectionResponse(
            redirect_url=_post_selection_redirect_url(payload.next_url, session_data),
            selected_connector_party_id=connector.party_id,
            selected_connector_name=connector.name,
        )
        json_response = JSONResponse(content=jsonable_encoder(result))
        if should_attach_cookie:
            cookie.attach_to_response(json_response, session_id)
        return json_response
    except HTTPException:
        raise
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except IShareParticipantRegistryError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.get("/connectors/login", response_class=HTMLResponse)
async def connector_login_request(party_id: str):
    client = IShareParticipantRegistryClient(settings)
    try:
        connector = await client.get_connector_details(party_id)
        if not connector.capability_url:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Connector {party_id} does not expose capabilityUrl in PR and no override is configured"
                ),
            )

        connector_capabilities = await client.get_capabilities(
            connector.capability_url, expected_issuer=connector.party_id
        )
        associated_idp_party_id = client.extract_associated_idp_party_id(
            connector_capabilities
        )

        identity_provider = await client.get_party_record(associated_idp_party_id)
        authorize_url = settings.ISHARE_IDP_AUTHORIZE_URL_OVERRIDES.get(
            associated_idp_party_id
        )
        token_url = settings.ISHARE_IDP_TOKEN_URL_OVERRIDES.get(associated_idp_party_id)

        idp_capability_url = settings.ISHARE_IDP_CAPABILITY_URL_OVERRIDES.get(
            associated_idp_party_id
        ) or client._first_string(
            identity_provider,
            (
                "capabilityUrl",
                "capabilitiesUrl",
                "capability_url",
                "capabilities_endpoint",
            ),
        )

        if idp_capability_url:
            idp_capabilities = await client.get_capabilities(
                idp_capability_url, expected_issuer=associated_idp_party_id
            )
            authorize_url = authorize_url or client.resolve_service_endpoint(
                idp_capabilities, "authorize"
            )
            token_url = token_url or client.resolve_service_endpoint(
                idp_capabilities, "token"
            )

        if not authorize_url:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Could not resolve authorizeUrl for IDP {associated_idp_party_id}. "
                    "Configure ISHARE_IDP_AUTHORIZE_URL_OVERRIDES or publish IDP capabilities."
                ),
            )
        if not token_url and "/connect/" in authorize_url:
            token_url = authorize_url.replace(
                "/connect/authorize", "/connect/token"
            ).replace("/connect/authorise", "/connect/token")
        if not token_url:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Could not resolve token endpoint for IDP {associated_idp_party_id}. "
                    "Configure ISHARE_IDP_TOKEN_URL_OVERRIDES or publish IDP capabilities."
                ),
            )

        state = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        connector_login_cache[state] = {
            "connector_party_id": connector.party_id,
            "idp_party_id": associated_idp_party_id,
            "token_url": token_url,
            "redirect_uri": client.connector_return_url,
            "nonce": nonce,
        }
        request_jwt = client.build_authorization_request_jwt(
            idp_party_id=associated_idp_party_id,
            idp_public_key=client.idp_public_key_from_party(identity_provider),
            redirect_uri=client.connector_return_url,
            state=state,
            nonce=nonce,
        )
        return HTMLResponse(
            _render_auto_post_form(
                action=authorize_url,
                form_fields={
                    "response_type": "code",
                    "scope": settings.ISHARE_AUTHORIZE_SCOPE,
                    "client_id": settings.ISHARE_CLIENT_ID or "",
                    "request": request_jwt,
                },
                connector_name=connector.name or connector.party_id,
            )
        )
    except HTTPException:
        raise
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except IShareParticipantRegistryError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@router.get("/connectors/return")
async def connector_login_return(code: str, state: str):
    if state not in connector_login_cache:
        return RedirectResponse(status_code=303, url=f"{settings.UI_BASE_URL}idps")

    login_context = connector_login_cache.pop(state)
    client = IShareParticipantRegistryClient(settings)
    try:
        token_response = await client.exchange_authorization_code(
            token_url=login_context["token_url"],
            code=code,
            redirect_uri=login_context["redirect_uri"],
            audience=login_context["idp_party_id"],
        )
        id_token_payload = _decode_jwt_payload(token_response.get("id_token"))
        if (
            login_context.get("nonce")
            and id_token_payload.get("nonce")
            and id_token_payload.get("nonce") != login_context["nonce"]
        ):
            return RedirectResponse(status_code=303, url=f"{settings.UI_BASE_URL}idps")
        username = (
            id_token_payload.get("name")
            or id_token_payload.get("sub")
            or login_context["connector_party_id"]
        )
        aai_id = id_token_payload.get("sub") or username

        session_id = uuid4()
        session_data = SessionData(
            username=username,
            aai_state=state,
            aai_id=aai_id,
            session_uuid=str(uuid.uuid4()),
        )
        await backend.create(session_id, session_data)
        auth_response = RedirectResponse(status_code=303, url=settings.UI_BASE_URL)
        cookie.attach_to_response(auth_response, session_id)
        return auth_response
    except IShareParticipantRegistryError:
        return RedirectResponse(status_code=303, url=f"{settings.UI_BASE_URL}idps")


@router.get("/request")
async def auth_request():
    try:
        result = get_rp_handler().begin(issuer_id=settings.OIDC_ISSUER)
    except Exception as err:
        raise HTTPException(
            status_code=400, detail=f"Something went wrong: {err} {repr(err)}"
        ) from err
    return RedirectResponse(status_code=303, url=result["url"])


@router.get("/checkin")
async def auth_checkin(code: str, state: str):
    if not state:
        return RedirectResponse(status_code=400, url=settings.UI_BASE_URL)

    try:
        aai_response = get_rp_handler().finalize(
            settings.OIDC_ISSUER, dict(code=code, state=state)
        )

        session_id = uuid4()
        username = aai_response["userinfo"]["name"]
        aai_id = aai_response["userinfo"]["sub"]

        session_data = SessionData(
            username=username,
            aai_state=state,
            aai_id=aai_id,
            session_uuid=str(uuid.uuid4()),
        )
        await backend.create(session_id, session_data)
        auth_response = RedirectResponse(status_code=303, url=settings.UI_BASE_URL)
        cookie.attach_to_response(auth_response, session_id)
        return auth_response
    except Exception:
        return RedirectResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            url=settings.UI_BASE_URL,
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/userinfo", dependencies=[Depends(cookie)], response_model=UserInfoResponse
)
async def user_info(session_data: SessionData = Depends(verifier)) -> UserInfoResponse:
    if session_data.username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return UserInfoResponse(username=session_data.username)


@router.get("/logout")
async def logout(response: Response, session_id: UUID = Depends(cookie)):
    try:
        await backend.delete(session_id)
    except KeyError:
        pass

    cookie.delete_from_response(response)
    return RedirectResponse(status_code=303, url=settings.UI_BASE_URL)


def _render_auto_post_form(
    action: str, form_fields: dict[str, str], connector_name: str
) -> str:
    hidden_inputs = "\n".join(
        (
            f'<input type="hidden" name="{html.escape(name)}" '
            f'value="{html.escape(value)}" />'
        )
        for name, value in form_fields.items()
    )
    escaped_action = html.escape(action, quote=True)
    escaped_connector_name = html.escape(connector_name)
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Redirecting to connector login</title>
  </head>
  <body>
    <main style="font-family: Arial, sans-serif; max-width: 640px; margin: 48px auto; padding: 0 20px;">
      <h1 style="font-size: 28px; line-height: 1.2; margin: 0 0 12px;">Redirecting to connector login</h1>
      <p style="margin: 0 0 18px; color: #4d5968;">
        Preparing the authentication request for {escaped_connector_name}.
      </p>
      <form id="ishare-authorize-form" method="post" action="{escaped_action}">
        {hidden_inputs}
        <button type="submit">Continue</button>
      </form>
    </main>
    <script>
      document.getElementById('ishare-authorize-form').submit();
    </script>
  </body>
</html>"""


def _decode_jwt_payload(token: Optional[str]) -> dict[str, str]:
    if not token or token.count(".") < 2:
        return {}
    _, payload, _ = token.split(".", 2)
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload + padding).decode("utf-8"))
    except Exception:
        return {}


async def _get_or_create_session(
    request: Request,
) -> tuple[UUID, SessionData, bool]:
    try:
        session_id = cookie(request)
        session_data = await backend.read(session_id)
        return session_id, session_data, False
    except Exception:
        session_id = uuid4()
        session_data = SessionData(
            username=None,
            aai_state=None,
            aai_id="",
            session_uuid=str(uuid.uuid4()),
        )
        return session_id, session_data, True


def _post_selection_redirect_url(
    next_url: Optional[str], session_data: SessionData
) -> str:
    if next_url:
        return (
            next_url
            if _is_allowed_navigation_url(next_url)
            else f"{settings.UI_BASE_URL}search"
        )
    if session_data.pending_dataset_navigation_url:
        return session_data.pending_dataset_navigation_url
    return f"{settings.UI_BASE_URL}search"


def _is_allowed_navigation_url(url: str) -> bool:
    parsed_next = urlparse(url)
    if not parsed_next.path.startswith("/api/web/navigate"):
        return False
    if not parsed_next.netloc:
        return True

    parsed_backend = urlparse(str(settings.BACKEND_BASE_URL))
    parsed_ui = urlparse(str(settings.UI_BASE_URL))
    allowed_hosts = {parsed_backend.netloc, parsed_ui.netloc}
    return parsed_next.netloc in allowed_hosts
