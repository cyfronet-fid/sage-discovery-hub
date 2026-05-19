import { Component, Inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { Observable, catchError, finalize, map, of, startWith } from 'rxjs';
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

  readonly state$: Observable<IdpListState> = this._idpListService.get$().pipe(
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

  selectConnector(connector: IdpListItem): void {
    if (this.selectingPartyId !== null) {
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
}
