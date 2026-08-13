# pylint: disable=missing-module-docstring,missing-function-docstring
import urllib.parse

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_200_OK, HTTP_303_SEE_OTHER

from app.routes.web import auth as auth_routes
from app.dependencies import user_actions as user_actions_dependencies
from app.schemas.party_registry import PartyListItem, PartyListResponse, PartyListSource
from app.utils.cookie_validators import backend
from tests.utils import UserSession


CONNECTOR_A = "EU.EORI.PL7770002062"
CONNECTOR_B = "EU.EORI.PL8880002062"
DASHBOARD_A = "https://dashboard-a.example/"
DASHBOARD_B = "https://dashboard-b.example/base/"


class FakeIShareParticipantRegistryClient:
    def __init__(self, settings):
        self._settings = settings

    async def get_connector_list(self):
        return PartyListResponse(
            items=[
                PartyListItem(
                    party_id=CONNECTOR_A,
                    name="Connector A",
                    role="ServiceProvider",
                    status="Active",
                    data_space_id="EU.DS.GND.SAGE",
                    tag="connector",
                    dashboard_url=DASHBOARD_A,
                ),
                PartyListItem(
                    party_id=CONNECTOR_B,
                    name="Connector B",
                    role="ServiceProvider",
                    status="Active",
                    data_space_id="EU.DS.GND.SAGE",
                    tag="connector",
                    dashboard_url=DASHBOARD_B,
                ),
            ],
            source=PartyListSource(
                participant_registry_id="did:ishare:EU.NL.NTRPL-12345678",
                parties_endpoint="https://pr.example/parties",
                filters={"tags": "connector"},
            ),
        )

    async def get_connector_details(self, party_id):
        connector_list = await self.get_connector_list()
        connector = next(
            (item for item in connector_list.items if item.party_id == party_id),
            None,
        )
        if connector is None:
            raise ValueError(f"Unknown connector {party_id}")
        return connector


def dataset_navigation_params(resource_id: str = "dataset-1") -> dict[str, str]:
    return {
        "url": urllib.parse.quote(
            f"/offer/{resource_id}?participantId=abc&originator=xyz"
        ),
        "return_path": "search/all",
        "search_params": "q%3D%2A",
        "resource_id": resource_id,
        "resource_type": "dataset",
        "page_id": "/search/all",
        "recommendation": "0",
    }


@pytest.fixture(autouse=True)
def isolate_connector_flow(monkeypatch, app: FastAPI):
    backend.data.clear()
    app.dependency_overrides[user_actions_dependencies.user_actions_client] = (
        lambda: None
    )
    monkeypatch.setattr(
        auth_routes,
        "IShareParticipantRegistryClient",
        FakeIShareParticipantRegistryClient,
    )
    yield
    app.dependency_overrides.pop(
        user_actions_dependencies.user_actions_client, None
    )
    backend.data.clear()


@pytest.mark.asyncio
async def test_dataset_click_without_selected_connector_redirects_to_connector_list_and_stores_pending_dataset(
    app: FastAPI, client: AsyncClient
):
    response = await client.get(
        app.url_path_for("web:register-navigation-user-action"),
        params=dataset_navigation_params("dataset-1"),
        follow_redirects=False,
    )

    assert response.status_code == HTTP_303_SEE_OTHER
    assert response.headers["location"].startswith("http://localhost:4200/idps")
    assert response.headers.get("set-cookie")

    session_data = next(iter(backend.data.values()))
    assert session_data.pending_dataset_resource_id == "dataset-1"
    assert session_data.pending_dataset_url == (
        "http://localhost:4200/offer/dataset-1?participantId=abc&originator=xyz"
    )
    assert session_data.pending_dataset_navigation_url.startswith("/api/web/navigate")


@pytest.mark.asyncio
async def test_connector_selection_is_stored_in_existing_session_and_resumes_pending_dataset(
    auth_client: AsyncClient, user_session: UserSession
):
    user_session.session_data.pending_dataset_navigation_url = (
        "/api/web/navigate?resource_type=dataset&resource_id=dataset-1"
    )
    await backend.update(user_session.backend_session_id, user_session.session_data)

    response = await auth_client.post(
        "/api/web/auth/connectors/select",
        json={"party_id": CONNECTOR_A},
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["redirect_url"] == (
        "/api/web/navigate?resource_type=dataset&resource_id=dataset-1"
    )
    session_data = await backend.read(user_session.backend_session_id)
    assert session_data.selected_connector_party_id == CONNECTOR_A
    assert session_data.selected_connector_name == "Connector A"
    assert session_data.selected_connector_dashboard_url == DASHBOARD_A


@pytest.mark.asyncio
async def test_connector_selection_with_next_url_creates_session_and_returns_next_url(
    client: AsyncClient,
):
    next_url = "/api/web/navigate?resource_type=dataset&resource_id=dataset-1"

    response = await client.post(
        "/api/web/auth/connectors/select",
        json={"party_id": CONNECTOR_A, "next_url": next_url},
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["redirect_url"] == next_url
    assert response.headers.get("set-cookie")

    session_data = next(iter(backend.data.values()))
    assert session_data.selected_connector_party_id == CONNECTOR_A
    assert session_data.selected_connector_dashboard_url == DASHBOARD_A


@pytest.mark.asyncio
async def test_connector_selection_status_returns_selected_connector(
    auth_client: AsyncClient, user_session: UserSession
):
    user_session.session_data.selected_connector_party_id = CONNECTOR_A
    user_session.session_data.selected_connector_name = "Connector A"
    user_session.session_data.selected_connector_dashboard_url = DASHBOARD_A
    await backend.update(user_session.backend_session_id, user_session.session_data)

    response = await auth_client.get("/api/web/auth/connectors/selection")

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "selected_connector_party_id": CONNECTOR_A,
        "selected_connector_name": "Connector A",
        "selected_connector_dashboard_url": DASHBOARD_A,
    }


@pytest.mark.asyncio
async def test_dataset_click_with_selected_connector_redirects_to_selected_dashboard(
    app: FastAPI, auth_client: AsyncClient, user_session: UserSession
):
    user_session.session_data.selected_connector_party_id = CONNECTOR_A
    user_session.session_data.selected_connector_dashboard_url = DASHBOARD_A
    user_session.session_data.pending_dataset_resource_id = "old-dataset"
    await backend.update(user_session.backend_session_id, user_session.session_data)

    response = await auth_client.get(
        app.url_path_for("web:register-navigation-user-action"),
        params=dataset_navigation_params("dataset-2"),
        follow_redirects=False,
    )

    assert response.status_code == HTTP_303_SEE_OTHER
    redirect_url = response.headers["location"]
    parsed_redirect = urllib.parse.urlparse(redirect_url)
    redirect_params = urllib.parse.parse_qs(parsed_redirect.query)
    assert redirect_url.startswith("https://dashboard-a.example/offer/dataset-2?")
    assert redirect_params["participantId"] == ["abc"]
    assert redirect_params["originator"] == ["xyz"]
    assert redirect_params["return_path"] == ["search/all"]
    assert redirect_params["search_params"] == ["q=*"]
    session_data = await backend.read(user_session.backend_session_id)
    assert session_data.pending_dataset_resource_id is None
    assert session_data.pending_dataset_url is None
    assert session_data.pending_dataset_navigation_url is None


@pytest.mark.asyncio
async def test_changing_selected_connector_changes_dataset_dashboard_url(
    app: FastAPI, auth_client: AsyncClient, user_session: UserSession
):
    first_selection = await auth_client.post(
        "/api/web/auth/connectors/select",
        json={"party_id": CONNECTOR_A},
    )
    assert first_selection.status_code == HTTP_200_OK

    first_redirect = await auth_client.get(
        app.url_path_for("web:register-navigation-user-action"),
        params=dataset_navigation_params("dataset-3"),
        follow_redirects=False,
    )
    assert first_redirect.headers["location"].startswith(
        "https://dashboard-a.example/offer/dataset-3"
    )

    second_selection = await auth_client.post(
        "/api/web/auth/connectors/select",
        json={"party_id": CONNECTOR_B},
    )
    assert second_selection.status_code == HTTP_200_OK

    second_redirect = await auth_client.get(
        app.url_path_for("web:register-navigation-user-action"),
        params=dataset_navigation_params("dataset-3"),
        follow_redirects=False,
    )
    assert second_redirect.headers["location"].startswith(
        "https://dashboard-b.example/base/offer/dataset-3"
    )
