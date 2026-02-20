import { Component } from '@angular/core';
import { CustomRoute } from '@collections/services/custom-route.service';
import { NavConfigsRepository } from '@collections/repositories/nav-configs.repository';

@Component({
  selector: 'ess-collections-navigation',
  template: `
    <div class="container--xxl navigation">
      <!-- Search Info -->
      <div class="results-info" *ngIf="q$ | async as query">
        <ng-container *ngIf="query && query !== '*'">
          Your search results for: “{{ query }}”
        </ng-container>
      </div>

      <!-- Breadcrumbs -->
      <nav
        aria-label="breadcrumb"
        *ngIf="activeNavConfig$ | async as activeNavConfig"
      >
        <ol class="breadcrumb">
          <ng-container
            *ngFor="
              let breadcrumb of activeNavConfig.breadcrumbs;
              let last = last
            "
          >
            <li
              class="breadcrumb-item"
              [class.active]="last"
              [attr.aria-current]="last ? 'page' : null"
            >
              <a *ngIf="!last && breadcrumb.url" [routerLink]="breadcrumb.url">
                {{ breadcrumb.label }}
              </a>

              <span *ngIf="last || !breadcrumb.url">
                {{ breadcrumb.label }}
              </span>
            </li>

            <li class="breadcrumb-separator" aria-hidden="true" *ngIf="!last">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                fill="currentColor"
                viewBox="0 0 16 16"
              >
                <path
                  fill-rule="evenodd"
                  d="M5.146 3.646a.5.5 0 0 1 .708 0L10.5 8l-4.646 4.354a.5.5 0 0 1-.708-.708L9.293 8 5.146 4.354a.5.5 0 0 1 0-.708z"
                />
              </svg>
            </li>
          </ng-container>
        </ol>
      </nav>
    </div>
  `,
})
export class CollectionsNavigationComponent {
  public activeNavConfig$ = this._navConfigsRepository.activeEntity$;
  public q$ = this._customRoute.q$;

  constructor(
    private _customRoute: CustomRoute,
    private _navConfigsRepository: NavConfigsRepository
  ) {}
}
