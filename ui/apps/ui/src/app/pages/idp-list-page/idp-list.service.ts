import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '@environment/environment';
import {
  ConnectorSelectionResponse,
  IdpListItem,
  IdpListResponse,
} from './idp-list.types';

@Injectable({
  providedIn: 'root',
})
export class IdpListService {
  constructor(private _http: HttpClient) {}

  get$(includeDetails = true): Observable<IdpListResponse> {
    return this._http.get<IdpListResponse>(
      `${environment.backendApiPath}/auth/connectors`,
      {
        params: {
          include_details: String(includeDetails),
        },
      }
    );
  }

  details$(partyId: string): Observable<IdpListItem> {
    return this._http.get<IdpListItem>(
      `${environment.backendApiPath}/auth/connectors/${encodeURIComponent(
        partyId
      )}/details`
    );
  }

  select$(
    partyId: string,
    nextUrl: string | null
  ): Observable<ConnectorSelectionResponse> {
    return this._http.post<ConnectorSelectionResponse>(
      `${environment.backendApiPath}/auth/connectors/select`,
      {
        party_id: partyId,
        next_url: nextUrl,
      }
    );
  }
}
