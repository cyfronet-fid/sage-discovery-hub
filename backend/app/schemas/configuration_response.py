# pylint: disable=missing-module-docstring,missing-class-docstring
from pydantic import BaseModel

from app.settings import Url


class ConfigurationResponse(BaseModel):
    eu_marketplace_url: Url
    pl_marketplace_url: Url
    psnc_dashboard_url: Url
    eosc_commons_url: Url
    eosc_commons_env: str
    eosc_explore_url: Url
    eosc_helpdesk_form_url: Url
    helpdesk_target_id: int
    knowledge_hub_url: Url
    is_sort_by_relevance: bool
    max_results_by_page: int
    max_items_sort_relevance: int
    show_beta_collections: bool
    show_knowledge_base: bool
