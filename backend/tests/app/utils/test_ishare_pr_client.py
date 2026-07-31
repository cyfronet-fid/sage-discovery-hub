from app.settings import settings
from app.utils.ishare_pr_client import IShareParticipantRegistryClient


def test_extract_party_list_from_v211_parties_info_payload():
    client = IShareParticipantRegistryClient(settings)
    party = {"party_id": "did:ishare:EU.NL.NTRNL-example"}

    assert client._extract_party_list({"parties_info": {"data": [party]}}) == [party]


def test_build_service_provider_list_item_from_v211_party_shape():
    client = IShareParticipantRegistryClient(settings)
    party = {
        "adherence": {"status": "Active"},
        "party_id": "did:ishare:EU.NL.NTRNL-example",
        "party_name": "Example Data Connector",
        "capability_url": "https://idp.example.com/capabilities",
        "agreements": [{"dataspace_id": "EU.DSP.SAGE"}],
        "additional_info": {"tags": "sage-data-connector"},
        "roles": [
            {
                "role": "ServiceProvider",
                "start_date": "2026-01-01T00:00:00.000Z",
                "end_date": "2027-01-01T00:00:00.000Z",
            }
        ],
    }

    item = client._to_party_list_item(
        party,
        role="ServiceProvider",
        data_space_id="EU.DSP.SAGE",
        tag="sage-data-connector",
    )

    assert item is not None
    assert item.party_id == "did:ishare:EU.NL.NTRNL-example"
    assert item.name == "Example Data Connector"
    assert item.capability_url == "https://idp.example.com/capabilities"
    assert item.data_space_id == "EU.DSP.SAGE"
    assert item.tag == "sage-data-connector"


def test_exclude_inactive_party_from_idp_list():
    client = IShareParticipantRegistryClient(settings)

    assert (
        client._to_party_list_item(
            {
                "adherence": {"status": "Inactive"},
                "party_id": "did:ishare:EU.NL.NTRNL-example",
                "roles": [{"role": "ServiceProvider"}],
            },
            role="ServiceProvider",
        )
        is None
    )


def test_extract_associated_idp_party_id_from_capabilities():
    client = IShareParticipantRegistryClient(settings)

    capabilities = {
        "capabilities_info": {
            "publicServices": [
                {
                    "identifier": "associated-idp",
                    "partyId": "did:ishare:EU.NL.NTRNL-idp",
                    "status": "active",
                }
            ]
        }
    }

    assert (
        client.extract_associated_idp_party_id(capabilities)
        == "did:ishare:EU.NL.NTRNL-idp"
    )


def test_resolve_authorize_endpoint_from_capabilities():
    client = IShareParticipantRegistryClient(settings)

    capabilities = {
        "capabilities_info": {
            "publicServices": [
                {
                    "identifier": "authorise",
                    "title": "Authorise",
                    "endpointURL": "https://idp.example.com/connect/authorize",
                    "status": "active",
                }
            ]
        }
    }

    assert (
        client.resolve_service_endpoint(capabilities, "authorize")
        == "https://idp.example.com/connect/authorize"
    )


def test_resolve_dashboard_endpoint_from_supported_features_capabilities():
    client = IShareParticipantRegistryClient(settings)

    capabilities = {
        "capabilities_info": {
            "supported_versions": [
                {
                    "version": "v2.0.1",
                    "supported_features": [
                        {
                            "public": [
                                {
                                    "feature": "Dashboard",
                                    "description": "Connector operator dashboard",
                                    "id": "dashboard",
                                    "url": "https://dashboard.example/",
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    }

    assert (
        client.resolve_service_endpoint(capabilities, "dashboard")
        == "https://dashboard.example/"
    )


def test_extract_ishare_roles_from_capabilities():
    client = IShareParticipantRegistryClient(settings)

    capabilities = {
        "capabilities_info": {
            "ishare_roles": [
                {"role": "ServiceProvider"},
                {"role": "ServiceConsumer"},
                {"role": "IdentityProvider"},
            ]
        }
    }

    assert client.extract_ishare_roles(capabilities) == [
        "ServiceProvider",
        "ServiceConsumer",
        "IdentityProvider",
    ]
