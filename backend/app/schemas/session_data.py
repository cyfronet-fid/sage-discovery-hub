# pylint: disable=missing-module-docstring,missing-class-docstring
from typing import Any, Optional

from pydantic import BaseModel


class SessionData(BaseModel):
    username: Optional[str] = None
    aai_state: Optional[str] = None
    aai_id: Optional[str] = None
    rp_handler: Any = None
    session_uuid: str
    selected_connector_party_id: Optional[str] = None
    selected_connector_name: Optional[str] = None
    selected_connector_dashboard_url: Optional[str] = None
    pending_dataset_resource_id: Optional[str] = None
    pending_dataset_url: Optional[str] = None
    pending_dataset_navigation_url: Optional[str] = None
