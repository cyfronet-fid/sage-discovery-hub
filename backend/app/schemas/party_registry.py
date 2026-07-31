"""Schemas for iSHARE party registry discovery and connector login."""

from typing import Optional

from pydantic import BaseModel, Field


class PartyListItem(BaseModel):
    """A single validated party returned from the Participant Registry."""

    party_id: str
    name: Optional[str] = None
    role: str
    status: str
    capability_url: Optional[str] = None
    data_space_id: Optional[str] = None
    tag: Optional[str] = None
    authorize_url: Optional[str] = None
    login_url: Optional[str] = None
    dashboard_url: Optional[str] = None
    ishare_roles: list[str] = Field(default_factory=list)


class PartyListSource(BaseModel):
    """Metadata describing the PR call used to build the party list."""

    participant_registry_id: str
    parties_endpoint: str
    filters: dict[str, str]


class PartyListResponse(BaseModel):
    """Party list response."""

    items: list[PartyListItem]
    source: PartyListSource
