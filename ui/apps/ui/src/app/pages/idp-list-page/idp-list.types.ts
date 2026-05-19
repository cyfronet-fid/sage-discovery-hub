export interface IdpListItem {
  party_id: string;
  name: string | null;
  role: string;
  status: string;
  capability_url: string | null;
  data_space_id: string | null;
  tag: string | null;
  authorize_url: string | null;
  login_url: string | null;
  dashboard_url: string | null;
  ishare_roles: string[];
}

export interface IdpListResponse {
  items: IdpListItem[];
  source: {
    participant_registry_id: string;
    parties_endpoint: string;
    filters: Record<string, string>;
  };
}

export interface ConnectorSelectionResponse {
  redirect_url: string;
  selected_connector_party_id: string;
  selected_connector_name: string | null;
}
