import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '@environment/environment';
import {
  ConnectorSelectionResponse,
  IdpListResponse,
} from './idp-list.types';

@Injectable({
  providedIn: 'root',
})
export class IdpListService {
  constructor(private _http: HttpClient) {}

  get$(): Observable<IdpListResponse> {
    return this._http.get<IdpListResponse>(
      `${environment.backendApiPath}/auth/connectors`
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
