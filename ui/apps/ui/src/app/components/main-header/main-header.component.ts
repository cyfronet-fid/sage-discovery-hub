import { Component, OnInit, ViewEncapsulation } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { UntilDestroy, untilDestroyed } from '@ngneat/until-destroy';
import { UserProfileService } from '../../auth/user-profile.service';
import { EoscCommonWindow } from './types';
import { environment } from '@environment/environment';
import { catchError, delay, of } from 'rxjs';

declare let window: EoscCommonWindow;

interface ConnectorSelectionStatus {
  selected_connector_party_id: string | null;
  selected_connector_name: string | null;
  selected_connector_dashboard_url: string | null;
}

@UntilDestroy()
@Component({
  selector: 'ess-main-header',
  template: `
    <div class="main-header">
      <div
        [id]="id"
        [attr.data-logout-url]="backendUrl + '/auth/logout'"
        [attr.show-eosc-links]="'true'"
        #h5er
      ></div>

      <details *ngIf="selectedConnectorName" class="main-header__connector">
        <summary>
          <span class="main-header__connector-label">Data connector</span>
          <span class="main-header__connector-name">{{
            selectedConnectorName
          }}</span>
          <span class="main-header__connector-chevron" aria-hidden="true"></span>
        </summary>
        <div class="main-header__connector-menu">
          <a href="/idps">Change data connector</a>
        </div>
      </details>
    </div>
  `,
  styles: [
    `
      .main-header {
        position: relative;
      }

      .main-header__connector {
        position: absolute;
        right: 24px;
        top: 10px;
        z-index: 20;
        width: min(280px, calc(100vw - 48px));
        font-family: Roboto, Arial, sans-serif;
      }

      .main-header__connector summary {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 12px;
        gap: 2px 10px;
        align-items: center;
        min-height: 40px;
        padding: 7px 12px;
        border: 1px solid #d9dee7;
        border-radius: 8px;
        background: #fff;
        box-shadow: 0 6px 18px rgba(24, 63, 74, 0.08);
        cursor: pointer;
        color: #1b1f2a;
        font-weight: 600;
        list-style: none;
        transition:
          border-color 0.16s ease,
          box-shadow 0.16s ease;
      }

      .main-header__connector summary::-webkit-details-marker {
        display: none;
      }

      .main-header__connector summary:hover,
      .main-header__connector summary:focus-visible {
        border-color: #7bb6b2;
        box-shadow: 0 8px 22px rgba(24, 63, 74, 0.12);
        outline: none;
      }

      .main-header__connector-label {
        grid-column: 1;
        color: #657386;
        font-size: 11px;
        font-weight: 700;
        line-height: 1;
        text-transform: uppercase;
      }

      .main-header__connector-name {
        grid-column: 1;
        min-width: 0;
        overflow: hidden;
        color: #1b1f2a;
        font-size: 14px;
        line-height: 1.25;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .main-header__connector-chevron {
        grid-column: 2;
        grid-row: 1 / span 2;
        width: 8px;
        height: 8px;
        border-right: 2px solid #657386;
        border-bottom: 2px solid #657386;
        transform: rotate(45deg);
        transition: transform 0.16s ease;
      }

      .main-header__connector[open] .main-header__connector-chevron {
        transform: rotate(225deg);
      }

      .main-header__connector-menu {
        position: absolute;
        top: calc(100% + 8px);
        right: 0;
        width: 100%;
        padding: 6px;
        border: 1px solid #d9dee7;
        border-radius: 8px;
        background: #fff;
        box-shadow: 0 14px 32px rgba(24, 63, 74, 0.16);
      }

      .main-header__connector a {
        display: block;
        padding: 9px 10px;
        border-radius: 6px;
        color: #006c67;
        font-size: 14px;
        font-weight: 600;
        text-decoration: none;
      }

      .main-header__connector a:hover,
      .main-header__connector a:focus-visible {
        background: #edf8f6;
        outline: none;
      }
    `,
  ],
  encapsulation: ViewEncapsulation.None,
})
export class MainHeaderComponent implements OnInit {
  id = 'eosc-common-main-header';
  backendUrl = `${environment.backendApiPath}`;
  selectedConnectorName: string | null = null;

  constructor(
    private _userProfileService: UserProfileService,
    private _http: HttpClient
  ) {}

  ngOnInit() {
    this._loadConnectorSelection();
    this._userProfileService.user$
      .pipe(
        untilDestroyed(this),
        // delay is required to have rerender out of angular's detection cycle
        delay(0)
      )
      .subscribe((profile) =>
        window.eosccommon.renderMainHeader(`#${this.id}`, profile ?? undefined)
      );
  }

  private _loadConnectorSelection(): void {
    this._http
      .get<ConnectorSelectionStatus>(
        `${environment.backendApiPath}/auth/connectors/selection`
      )
      .pipe(
        untilDestroyed(this),
        catchError(() => of(null))
      )
      .subscribe((selection) => {
        this.selectedConnectorName = selection?.selected_connector_name ?? null;
      });
  }
}
