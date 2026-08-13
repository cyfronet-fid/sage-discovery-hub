import { Component, Inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { Observable, catchError, finalize, map, of, startWith, tap } from 'rxjs';
import { IdpListService } from './idp-list.service';
import { IdpListItem, IdpListResponse } from './idp-list.types';

type IdpListState =
  | { status: 'loading' }
  | { status: 'loaded'; response: IdpListResponse }
  | { status: 'error'; message: string };

@Component({
  selector: 'ess-idp-list-page',
  templateUrl: './idp-list-page.component.html',
  styleUrls: ['./idp-list-page.component.scss'],
})
export class IdpListPageComponent {
  selectingPartyId: string | null = null;
  selectionError: string | null = null;
  connectorDetails: Record<string, IdpListItem> = {};
  loadingDetailsPartyIds = new Set<string>();
  detailErrorPartyIds = new Set<string>();

  readonly state$: Observable<IdpListState> = this._idpListService.get$(false).pipe(
    tap((response) => this.loadConnectorDetails(response.items)),
    map((response) => ({ status: 'loaded', response } as IdpListState)),
    startWith({ status: 'loading' } as IdpListState),
    catchError((error) =>
      of({
        status: 'error',
        message:
          error?.error?.detail ?? 'The connector list could not be loaded.',
      } as IdpListState)
    )
  );

  constructor(
    private _idpListService: IdpListService,
    private _route: ActivatedRoute,
    @Inject(DOCUMENT) private _document: Document
  ) {}

  get hasPendingNavigation(): boolean {
    return this._route.snapshot.queryParamMap.has('next');
  }

  getConnector(connector: IdpListItem): IdpListItem {
    return this.connectorDetails[connector.party_id] ?? connector;
  }

  isLoadingDetails(connector: IdpListItem): boolean {
    return this.loadingDetailsPartyIds.has(connector.party_id);
  }

  hasDetailError(connector: IdpListItem): boolean {
    return this.detailErrorPartyIds.has(connector.party_id);
  }

  areDetailsUnavailable(connector: IdpListItem): boolean {
    return this.isConnectorUnavailable(connector);
  }

  isConnectorUnavailable(connector: IdpListItem): boolean {
    const connectorDetails = this.getConnector(connector);
    return (
      !this.isLoadingDetails(connector) &&
      (this.hasDetailError(connector) ||
        Boolean(this.connectorDetails[connector.party_id])) &&
      !connectorDetails.dashboard_url
    );
  }

  getSortedConnectors(connectors: IdpListItem[]): IdpListItem[] {
    return connectors
      .map((connector, index) => ({ connector, index }))
      .sort((left, right) => {
        const leftUnavailable = this.isConnectorUnavailable(left.connector);
        const rightUnavailable = this.isConnectorUnavailable(right.connector);
        if (leftUnavailable === rightUnavailable) {
          return left.index - right.index;
        }
        return leftUnavailable ? 1 : -1;
      })
      .map(({ connector }) => connector);
  }

  selectConnector(connector: IdpListItem): void {
    if (
      this.selectingPartyId !== null ||
      this.isConnectorUnavailable(connector)
    ) {
      return;
    }

    this.selectionError = null;
    this.selectingPartyId = connector.party_id;
    const nextUrl = this._route.snapshot.queryParamMap.get('next');
    this._idpListService
      .select$(connector.party_id, nextUrl)
      .pipe(finalize(() => (this.selectingPartyId = null)))
      .subscribe({
        next: (response) => {
          this._document.location.href = response.redirect_url;
        },
        error: (error) => {
          this.selectionError =
            error?.error?.detail ?? 'The selected connector could not be saved.';
          this.selectingPartyId = null;
        },
      });
  }

  private loadConnectorDetails(connectors: IdpListItem[]): void {
    connectors.forEach((connector) => {
      if (
        this.connectorDetails[connector.party_id] ||
        this.loadingDetailsPartyIds.has(connector.party_id)
      ) {
        return;
      }

      this.loadingDetailsPartyIds.add(connector.party_id);
      this.detailErrorPartyIds.delete(connector.party_id);
      this._idpListService
        .details$(connector.party_id)
        .pipe(
          finalize(() => {
            this.loadingDetailsPartyIds.delete(connector.party_id);
          })
        )
        .subscribe({
          next: (details) => {
            this.connectorDetails[connector.party_id] = details;
          },
          error: () => {
            this.detailErrorPartyIds.add(connector.party_id);
          },
        });
    });
  }
}
