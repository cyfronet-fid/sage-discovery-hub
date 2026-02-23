import { IFiltersConfig } from '../../repositories/types';
import { URL_PARAM_NAME } from './nav-config.data';
import { alphanumericFilterSort } from '@collections/data/utils';

export const allCollectionsFilters: IFiltersConfig = {
  id: URL_PARAM_NAME,
  filters: [
    {
      id: 'catalogue',
      filter: 'catalogue',
      label: 'Catalogue',
      type: 'multiselect',
      defaultCollapsed: false,
      tooltipText: '',
      expandArrow: true,
    },
    {
      id: 'type',
      filter: 'type',
      label: 'Type of research product',
      type: 'multiselect',
      defaultCollapsed: true,
      tooltipText: '',
      expandArrow: true,
    },
    {
      id: 'publisher',
      filter: 'publisher',
      label: 'Publisher',
      type: 'multiselect',
      defaultCollapsed: true,
      tooltipText: '',
      expandArrow: true,
    },
    {
      id: 'license',
      filter: 'license',
      label: 'License',
      type: 'multiselect',
      defaultCollapsed: true,
      tooltipText: '',
      expandArrow: true,
    },
    {
      id: 'language',
      filter: 'language',
      label: 'Language',
      type: 'multiselect',
      defaultCollapsed: true,
      tooltipText: '',
      customSort: alphanumericFilterSort,
      expandArrow: true,
    },
    {
      id: 'publisher',
      filter: 'publisher',
      label: 'Publisher',
      type: 'tag',
      defaultCollapsed: false,
      tooltipText: '',
    },
    {
      id: 'keywords',
      filter: 'keywords',
      label: 'Keywords',
      type: 'tag',
      defaultCollapsed: false,
      tooltipText: '',
    },
  ],
};
