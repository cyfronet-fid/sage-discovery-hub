import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  QueryList,
  SimpleChanges,
  TrackByFunction,
  ViewChildren,
} from '@angular/core';
import { ISecondaryTag } from '@collections/repositories/types';
import { combineHighlightsWith } from './utils';

@Component({
  selector: 'ess-secondary-tags',
  template: `
    <div class="usage secondary-tags">
      <!-- Create some space between description and secondary tags -->
      <div *ngIf="checkTagsWithValues()" style="margin-bottom: 0.7rem;"></div>

      <ng-container
        *ngFor="let tag of parsedTags; let i = index; trackBy: identityTagTrack"
      >
        <ng-container [ngSwitch]="tag.type">
          <!-- URL TAGS -->
          <ng-container *ngSwitchCase="'url'">
            <span *ngIf="tag.values.length > 0" class="statistic text-muted">
              <div class="title-holder">
                <ng-container *ngIf="tag.iconPath">
                  <img [src]="tag.iconPath" alt="" />
                </ng-container>
                <ng-container *ngIf="tag.label">
                  <span class="label-text">{{ tag.label }}</span>
                </ng-container>
              </div>

              <div
                #keywordsBlock
                class="keywords-block"
                [class.is-collapsed]="!isExpanded(tag, i)"
                [attr.data-key]="tagKey(tag, i)"
              >
                <ng-container *ngFor="let keyword of tag.values">
                  <a
                    href="javascript:void(0)"
                    (click)="setActiveFilter($any(tag.filter), keyword.value)"
                    [innerHTML]="keyword.label"
                  ></a>
                  <span class="kw-sep">&nbsp;&nbsp;&nbsp;</span>
                </ng-container>
              </div>

              <div class="show-more-holder" *ngIf="canExpand(tag, i)">
                <a
                  href="javascript:void(0)"
                  class="show-more"
                  [class.is-open]="isExpanded(tag, i)"
                  (click)="toggleExpand(tag, i)"
                >
                  <span class="show-more-text">
                    {{ isExpanded(tag, i) ? 'Show less' : 'Show more' }}
                  </span>
                  <span class="show-more-arrow" aria-hidden="true"></span>
                </a>
              </div>
            </span>
          </ng-container>

          <!-- INFO TAGS -->
          <ng-container *ngSwitchCase="'info'">
            <span *ngIf="tag.values.length > 0" class="statistic text-muted">
              <div class="title-holder">
                <ng-container *ngIf="tag.iconPath">
                  <img [src]="tag.iconPath" alt="" />
                </ng-container>
                <ng-container *ngIf="tag.label">
                  <span class="label-text">{{ tag.label }}</span>
                </ng-container>
              </div>

              <div
                #keywordsBlock
                class="keywords-block"
                [class.is-collapsed]="!isExpanded(tag, i)"
                [attr.data-key]="tagKey(tag, i)"
              >
                <ng-container i18n *ngFor="let keyword of tag.values">
                  {{ keyword }}<span class="kw-sep">&nbsp;&nbsp;</span>
                </ng-container>
              </div>

              <div class="show-more-holder" *ngIf="canExpand(tag, i)">
                <a
                  href="javascript:void(0)"
                  class="show-more"
                  [class.is-open]="isExpanded(tag, i)"
                  (click)="toggleExpand(tag, i)"
                >
                  <span class="show-more-text">
                    {{ isExpanded(tag, i) ? 'show less' : 'show more' }}
                  </span>
                  <span class="show-more-arrow" aria-hidden="true"></span>
                </a>
              </div>
            </span>
          </ng-container>
        </ng-container>
      </ng-container>
    </div>
  `,
  styles: [
    `
      .usage > .statistic {
        font-size: 11px;
        display: block;
        overflow: visible;
        line-height: 1.7;
      }

      .statistic > img {
        display: inline;
        float: left;
        margin-right: 10px;
        margin-top: 5px;
      }

      .label-text {
        color: black;
        display: inline;
        float: left;
        margin-right: 10px;
      }

      .usage .title-holder {
        display: flex;
        column-gap: 5px;
        margin-bottom: 8px;
        font-size: 12px;

        img {
          width: 11px;
          height: auto;
        }
      }

      /* --- COLLAPSE / EXPAND --- */
      .keywords-block {
        display: block;
        overflow: hidden;
        line-height: 1.7;
      }

      .keywords-block.is-collapsed {
        max-height: 1.7em;
      }

      .kw-sep:last-child {
        display: none;
      }

      .show-more-holder {
        display: flex;
        justify-content: flex-end;
        margin-top: 9px;
      }

      .show-more {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 0;
        margin: 0;
        background: transparent;
        border: 0;
        font-size: 12px;
        line-height: 1;
        color: #34503e;
        text-decoration: none;
        cursor: pointer;
        opacity: 0.85;
      }

      .show-more:hover {
        opacity: 1;
        text-decoration: underline;
      }

      .show-more-text {
        white-space: nowrap;
      }

      .show-more-arrow {
        width: 6px;
        height: 6px;
        border-right: 1.5px solid currentColor;
        border-bottom: 1.5px solid currentColor;
        transform: rotate(45deg); /* strzałka w dół */
        margin-top: -1px;
        transition: transform 0.15s ease;
      }

      .show-more.is-open .show-more-arrow {
        transform: rotate(-135deg);
        margin-top: 3px;
      }

      ::ng-deep .highlighted {
        background-color: #e8e7ff !important;
        padding: 0px;
      }
    `,
  ],
})
export class SecondaryTagsComponent implements OnChanges, AfterViewInit {
  parsedTags: ISecondaryTag[] = [];

  @Input() tags: ISecondaryTag[] = [];
  @Input() highlights: { [field: string]: string[] | undefined } = {};

  @Output() activeFilter = new EventEmitter<{
    filter: string;
    value: string;
  }>();

  @ViewChildren('keywordsBlock') keywordsBlocks!: QueryList<
    ElementRef<HTMLElement>
  >;

  /** state of expansion per tag */
  private expandedMap = new Map<string, boolean>();
  /** should we show "show more"? */
  private canExpandMap = new Map<string, boolean>();

  ngOnChanges(changes: SimpleChanges) {
    if (changes['tags'] || changes['highlights']) {
      this.parsedTags = combineHighlightsWith(this.tags, this.highlights);

      setTimeout(() => this.updateExpandableStates(), 0);
    }
  }

  ngAfterViewInit(): void {
    setTimeout(() => this.updateExpandableStates(), 0);

    this.keywordsBlocks.changes.subscribe(() => {
      setTimeout(() => this.updateExpandableStates(), 0);
    });

    const ro = new ResizeObserver(() => this.updateExpandableStates());
    this.keywordsBlocks.forEach((ref) => ro.observe(ref.nativeElement));
  }

  identityTagTrack: TrackByFunction<ISecondaryTag> = (
    index: number,
    tag: ISecondaryTag
  ) => tag;

  setActiveFilter(filter: string, value: string): void {
    this.activeFilter.emit({ filter, value });
  }

  checkTagsWithValues(): boolean {
    return (
      this.parsedTags && this.parsedTags.some((tag) => tag.values.length > 0)
    );
  }

  tagKey(tag: ISecondaryTag, index: number): string {
    return `${index}|${tag.type}|${tag.filter ?? ''}|${tag.label ?? ''}|${
      tag.values?.length ?? 0
    }`;
  }

  isExpanded(tag: ISecondaryTag, index: number): boolean {
    return this.expandedMap.get(this.tagKey(tag, index)) === true;
  }

  canExpand(tag: ISecondaryTag, index: number): boolean {
    return this.canExpandMap.get(this.tagKey(tag, index)) === true;
  }

  toggleExpand(tag: ISecondaryTag, index: number): void {
    const key = this.tagKey(tag, index);
    this.expandedMap.set(key, !this.isExpanded(tag, index));
  }

  private updateExpandableStates(): void {
    if (!this.keywordsBlocks) return;

    this.keywordsBlocks.forEach((ref) => {
      const el = ref.nativeElement;
      const key = el.dataset['key'];
      if (!key) return;

      const computed = window.getComputedStyle(el);
      const lineHeight = parseFloat(computed.lineHeight || '0');

      const needsExpand = el.scrollHeight > lineHeight + 1;

      this.canExpandMap.set(key, needsExpand);

      if (!needsExpand) {
        this.expandedMap.set(key, false);
      }
    });
  }
}
