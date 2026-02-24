# pylint: disable=missing-module-docstring,missing-function-docstring
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import HTTP_200_OK


@pytest.mark.asyncio
async def test_return_backend_config(app: FastAPI, client: AsyncClient) -> None:
    response = await client.get(app.url_path_for("web:configuration"))

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "eosc_commons_env": "beta",
        "eosc_commons_url": "https://s3.cloud.cyfronet.pl/eosc-pl-common/",
        "eu_marketplace_url": "https://userspace.sandbox.eosc-beyond.eu/",
        "pl_marketplace_url": "https://marketplace.eosc.pl/",
        "psnc_dashboard_url": "https://provider-dashboard-edc-connector.apps.bst2.paas.psnc.pl/",
        "eosc_explore_url": "https://explore.sandbox.eosc-beyond.eu/",
        "eosc_helpdesk_form_url": "https://helpdesk.sandbox.eosc-beyond.eu/assets/form/form.js",
        "helpdesk_target_id": 38,
        "knowledge_hub_url": "https://knowledge-hub.sandbox.eosc-beyond.eu/",
        "is_sort_by_relevance": True,
        "max_results_by_page": 50,
        "max_items_sort_relevance": 250,
        "show_beta_collections": False,
        "show_knowledge_base": True,
    }
