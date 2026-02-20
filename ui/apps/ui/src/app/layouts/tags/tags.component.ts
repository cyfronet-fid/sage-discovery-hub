import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  TrackByFunction,
} from '@angular/core';
import {
  ITag,
  IValueWithLabel,
  IValueWithLabelAndLink,
} from '@collections/repositories/types';
import { combineHighlightsWith } from './utils';
import { ViewportScroller } from '@angular/common';
import { translateDictionaryValue } from '../../dictionary/translateDictionaryValue';
import { DICTIONARY_TYPE_FOR_PIPE } from '../../dictionary/dictionaryType';

@Component({
  selector: 'ess-tags',
  templateUrl: './tags.component.html',
  styles: [
    `
      ::ng-deep .highlighted {
        background-color: #e8e7ff !important;
        padding: 0px;
      }

      .tag:last-child a::after {
        content: '';
        width: 0px;
        height: 0px;
        border-radius: 0px;
        line-height: 1.2;
      }

      .show-more-tag {
        padding: 5px;
        font-size: 12px;
        line-height: 1;
        font-weight: 525;
        color: #30549f;
        display: inline-block;
        transition: all 0.2s ease;
      }

      .show-more-tag:hover {
        color: #000000;
        cursor: pointer;
      }

      .show-more-btn {
        padding-left: 4px;
        border: none;
        background: none;
        font-size: 12px;
        color: #99ca3c;
        cursor: pointer;
      }

      .show-more-btn:hover {
        text-decoration: underline;
      }
    `,
  ],
})
export class TagsComponent implements OnChanges {
  parsedTags: ITag[] = [];
  showMoreStatePerTag: { [tagLabel: string]: boolean } = {};

  // NEW: per-value expansion (long publisher labels)
  expandedValues: Record<string, Record<number, boolean>> = {};

  @Input() tags: ITag[] = [];
  @Input() providerName?: string[] = [];
  @Input() highlights: { [field: string]: string[] | undefined } = {};

  @Output() activeFilter = new EventEmitter<{
    filter: string;
    value: string;
  }>();

  trackByLabel: TrackByFunction<ITag> = (index: number, entity: ITag) =>
    entity.label;

  constructor(private viewPortScroller: ViewportScroller) {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes['tags'] || changes['highlights']) {
      this.parsedTags = combineHighlightsWith(this.tags, this.highlights);

      this.showMoreStatePerTag = Object.fromEntries(
        this.parsedTags.map((tag) => [tag.label, false])
      );

      this.expandedValues = {};
      for (const tag of this.parsedTags) {
        this.expandedValues[tag.label] = {};
      }
    }
  }

  setActiveFilter(filter: string, value: string): void {
    this.activeFilter.emit({ filter, value });
    this.viewPortScroller.scrollToPosition([0, 0]);
  }

  cleanDuplicatedTagLabel(
    array: IValueWithLabelAndLink[]
  ): IValueWithLabelAndLink[] {
    if (array[array.length - 1]?.value.indexOf('>') !== -1) {
      array.reverse();
    }

    const cleaned = array.reduce(
      (accumulator: IValueWithLabel[], current: IValueWithLabel) => {
        const exists = accumulator.find(
          (item) =>
            translateDictionaryValue(
              DICTIONARY_TYPE_FOR_PIPE.TYPE_SCIENTIFIC_DOMAINS,
              item.label
            ).toString() ===
            translateDictionaryValue(
              DICTIONARY_TYPE_FOR_PIPE.TYPE_SCIENTIFIC_DOMAINS,
              current.label
            ).toString()
        );
        if (!exists) accumulator.push(current);
        return accumulator;
      },
      []
    );

    return cleaned;
  }

  addSubTitle(subTitle?: string) {
    return subTitle ? `${subTitle}: ` : undefined;
  }

  _onClickExternalLink(e: MouseEvent, link?: string) {
    return link ? e : e.preventDefault();
  }

  toggleShowAllTags(tagLabel: string) {
    this.showMoreStatePerTag[tagLabel] = !this.showMoreStatePerTag[tagLabel];
  }

  computeTagEntries(tag: ITag): IValueWithLabelAndLink[] {
    const cleaned = this.cleanDuplicatedTagLabel(tag.values);

    if (this.showMoreStatePerTag[tag.label] || !tag.showMoreThreshold) {
      return cleaned;
    }

    return cleaned.slice(0, tag.showMoreThreshold);
  }

  createShowMoreLabel(tag: ITag): string {
    return this.showMoreStatePerTag[tag.label]
      ? 'Show less'
      : `+ ${tag.values.length - (tag.showMoreThreshold ?? 0)}`;
  }

  toggleExpandValue(tagLabel: string, index: number) {
    this.expandedValues[tagLabel][index] =
      !this.expandedValues[tagLabel][index];
  }

  getDisplayLabel(
    tag: ITag,
    value: IValueWithLabelAndLink,
    index: number
  ): string {
    const MAX_LENGTH = 40; // or make configurable per tag later

    const isExpanded = this.expandedValues[tag.label]?.[index] ?? false;

    if (value.label.length <= MAX_LENGTH || isExpanded) {
      return value.label;
    }

    return value.label.slice(0, MAX_LENGTH) + '…';
  }

  shouldShowValueToggle(val: IValueWithLabelAndLink): boolean {
    return val.label.length > 40;
  }
}
