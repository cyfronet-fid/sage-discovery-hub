"""Public iSHARE capabilities endpoint for the SAGE portal."""

from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException

from app.settings import settings
from app.utils.ishare_pr_client import (
    IShareConfigurationError,
    IShareParticipantRegistryClient,
)

router = APIRouter()


@router.get("/capabilities", name="capabilities")
async def capabilities():
    if not settings.ISHARE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="ISHARE_CLIENT_ID is not configured")

    try:
        token = IShareParticipantRegistryClient(settings).build_capabilities_token(
            _portal_capabilities_info()
        )
    except IShareConfigurationError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err

    return {"capabilities_token": token}


def _portal_capabilities_info() -> dict:
    portal_url = str(settings.UI_BASE_URL)
    return {
        "party_id": settings.ISHARE_CLIENT_ID,
        "supported_versions": [
            {
                "version": settings.ISHARE_PR_VERSION,
                "supported_features": [
                    {
                        "public": [
                            {
                                "feature": "SAGE Portal",
                                "description": "Portal for SAGE project",
                                "id": "sage-portal",
                                "url": portal_url,
                            },
                            {
                                "feature": "capabilities",
                                "description": "Retrieves iSHARE capabilities",
                                "id": "capabilities",
                                "url": urljoin(portal_url, "/capabilities"),
                            },
                        ]
                    }
                ],
            }
        ],
        "ishare_roles": [{"role": "ServiceProvider"}],
    }
