# pylint: disable=missing-module-docstring, too-many-locals
import logging
import urllib.parse
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from starlette.responses import RedirectResponse

from app.dependencies.user_actions import (
    UserActionClient,
    send_user_action_bg_task,
    user_actions_client,
)
from app.schemas.session_data import SessionData
from app.settings import settings
from app.utils.cookie_validators import backend, cookie, verifier

router = APIRouter()
logger = logging.getLogger(__name__)


# pylint: disable=too-many-arguments, too-many-positional-arguments
@router.get(
    "/navigate",
    name="web:register-navigation-user-action",
)
async def register_navigation_user_action(
    request: Request,
    background_tasks: BackgroundTasks,
    return_path: str,
    search_params: str,
    url: str,
    resource_id: str,
    resource_type: Literal[
        "service",
        "publication",
        "dataset",
        "training",
        "software",
        "data source",
        "data-source",
        "other",
        "guideline",
        "bundle",
        "provider",
        "project",
        "organisation",
        "catalogue",
    ],
    page_id: str,
    recommendation: bool = False,
    client: UserActionClient | None = Depends(user_actions_client),
):
    """Registers entering a URL and redirects to the URL"""

    if resource_type == "data-source":
        resource_type = "data source"

    url = urllib.parse.unquote(url)

    if url.startswith("/"):
        url = urllib.parse.urljoin(settings.UI_BASE_URL, url)

    target_id = uuid.uuid4()

    should_attach_cookie = False
    try:
        session_id = cookie(request)
        session = await verifier(request)
    except HTTPException:
        session_id = uuid.uuid4()
        new_session_uuid = uuid.uuid4()
        session = SessionData(
            username=None, aai_state=None, aai_id="", session_uuid=str(new_session_uuid)
        )
        await backend.create(session_id, session)
        should_attach_cookie = True

    if resource_type == "dataset":
        if not session.selected_connector_dashboard_url:
            session.pending_dataset_resource_id = resource_id
            session.pending_dataset_url = url
            session.pending_dataset_navigation_url = _relative_request_url(request)
            await backend.update(session_id, session)
            response = await _create_connector_selection_redirect(request)
            if should_attach_cookie:
                cookie.attach_to_response(response, session_id)
            return response
        url = _dataset_dashboard_url(url, session.selected_connector_dashboard_url)
        session.pending_dataset_resource_id = None
        session.pending_dataset_url = None
        session.pending_dataset_navigation_url = None
        await backend.update(session_id, session)

    response = await _create_redirect_response(
        return_path, search_params, session.session_uuid, str(target_id), url
    )
    if should_attach_cookie:
        cookie.attach_to_response(response, session_id)

    if not client:
        logger.debug("No mqtt client, user action not sent")
        return response

    # For now, the recommendation visit id will be stored in cookies by itself,
    # not connected to any session.
    recommendation_visit_id = request.cookies.get("recommendation_visit_id")

    background_tasks.add_task(
        send_user_action_bg_task,
        client,
        session,
        url,
        page_id,
        resource_id,
        resource_type,
        recommendation,
        str(target_id),
        recommendation_visit_id,
    )
    return response


async def _create_redirect_response(
    return_path: str, search_params: str, client_uid: str, target_id: str, url: str
):
    separator = "&" if urllib.parse.urlparse(url).query else "?"
    redirect_response = RedirectResponse(
        status_code=303,
        url=(
            url
            + separator
            + "return_path="
            + return_path
            + "&search_params="
            + search_params
            + "&source_id="
            + target_id
            + "&client_uid="
            + client_uid
        ),
    )
    return redirect_response


async def _create_connector_selection_redirect(request: Request) -> RedirectResponse:
    next_url = urllib.parse.quote(_relative_request_url(request), safe="")
    return RedirectResponse(
        status_code=303,
        url=f"{settings.UI_BASE_URL}idps?next={next_url}",
    )


def _relative_request_url(request: Request) -> str:
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def _dataset_dashboard_url(url: str, dashboard_url: str) -> str:
    parsed_original = urllib.parse.urlparse(url)
    parsed_dashboard = urllib.parse.urlparse(dashboard_url)
    base_path = parsed_dashboard.path.rstrip("/")
    original_path = parsed_original.path.lstrip("/")
    combined_path = f"{base_path}/{original_path}" if base_path else f"/{original_path}"
    return urllib.parse.urlunparse(
        (
            parsed_dashboard.scheme,
            parsed_dashboard.netloc,
            combined_path,
            "",
            parsed_original.query,
            "",
        )
    )
