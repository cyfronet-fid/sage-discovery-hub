"""Schemas for connector selection flow."""

from typing import Optional

from pydantic import BaseModel


class ConnectorSelectionRequest(BaseModel):
    party_id: str
    next_url: Optional[str] = None


class ConnectorSelectionResponse(BaseModel):
    redirect_url: str
    selected_connector_party_id: str
    selected_connector_name: Optional[str] = None


class ConnectorSelectionStatusResponse(BaseModel):
    selected_connector_party_id: Optional[str] = None
    selected_connector_name: Optional[str] = None
    selected_connector_dashboard_url: Optional[str] = None
