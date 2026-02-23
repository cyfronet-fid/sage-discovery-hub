import { IAdapter, IResult } from '../../repositories/types';
import { URL_PARAM_NAME } from './nav-config.data';
import { COLLECTION } from './search-metadata.data';
import { IOpenAIREResult } from '@collections/data/openair.model';
import { formatPublicationDate } from '@collections/data/utils';
import { IDataSource } from '@collections/data/data-sources/data-source.model';
import { ITraining } from '@collections/data/trainings/training.model';
import { IGuideline } from '@collections/data/guidelines/guideline.model';
import { IService } from '@collections/data/services/service.model';
import {
  toArray,
  toValueWithLabel,
} from '@collections/filters-serializers/utils';
import {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  transformLanguages,
} from '@collections/data/shared-tags';
import {
  parseStatistics,
  toKeywordsSecondaryTag,
} from '@collections/data/utils';
import { ConfigService } from '../../../services/config.service';
import { IBundle } from '@collections/data/bundles/bundle.model';
import { IProvider } from '@collections/data/providers/provider.model';

export const redirectUrlAdapter = (
  type: string,
  data: Partial<
    IOpenAIREResult &
      IDataSource &
      IService &
      ITraining &
      IGuideline &
      IBundle &
      IProvider
  >
) => {
  switch (type) {
    case 'dataset':
    case 'publication':
    case 'software':
    case 'other':
      return `${
        ConfigService.config?.eosc_explore_url
      }/search/result?id=${encodeURIComponent(
        data.id?.split('|')?.pop() || ''
      )}`;
    case 'data source':
      return data?.pid
        ? `${
            ConfigService.config?.eu_marketplace_url
          }/services/${encodeURIComponent(data.pid || '')}`
        : '';
    case 'service':
      return `${
        ConfigService.config?.eu_marketplace_url
      }/services/${encodeURIComponent(data.slug || '')}`;
    case 'bundle':
      return `${
        ConfigService.config?.eu_marketplace_url
      }/services/${encodeURIComponent(data.service_id || '')}`;
    case 'provider':
      return `${
        ConfigService.config?.eu_marketplace_url
      }/providers/${encodeURIComponent(data.pid || '')}`;
    case 'training':
      return '/trainings/' + encodeURIComponent(data.id || '');
    case 'interoperability guideline':
      return '/guidelines/' + encodeURIComponent(data.id || '');
    default:
      return '';
  }
};

export const logoUrlAdapter = (
  type: string,
  data: Partial<
    IOpenAIREResult &
      IDataSource &
      IService &
      ITraining &
      IGuideline &
      IBundle &
      IProvider
  >
) => {
  switch (type) {
    case 'data source':
      return data.pid
        ? `${
            ConfigService.config?.eu_marketplace_url
          }/services/${encodeURIComponent(data.pid || '')}/logo`
        : '';
    case 'service':
      return data.slug
        ? `${
            ConfigService.config?.eu_marketplace_url
          }/services/${encodeURIComponent(data.slug || '')}/logo`
        : '';
    case 'provider':
      return `${
        ConfigService.config?.eu_marketplace_url
      }/providers/${encodeURIComponent(data?.pid || '')}/logo`;
    default:
      return '';
  }
};

export const orderUrlAdapter = (
  type: string,
  data: Partial<
    IOpenAIREResult &
      IDataSource &
      IService &
      ITraining &
      IGuideline &
      IBundle &
      IProvider
  >
) => {
  switch (type) {
    case 'data source':
      return data.pid
        ? `${
            ConfigService.config?.eu_marketplace_url
          }/services/${encodeURIComponent(data.pid || '')}/offers`
        : '';
    case 'service':
      return data.slug
        ? `${
            ConfigService.config?.eu_marketplace_url
          }/services/${encodeURIComponent(data.slug || '')}/offers`
        : '';
    case 'bundle':
      return `${
        ConfigService.config?.eu_marketplace_url
      }/services/${encodeURIComponent(data.service_id || '')}/offers`;
    default:
      return '';
  }
};

const extractDate = (
  data: Partial<
    IOpenAIREResult &
      IDataSource &
      IService &
      ITraining &
      IGuideline &
      IBundle &
      IProvider
  >
) => {
  switch (data.type) {
    case 'interoperability guideline':
      return data['publication_year']
        ? data['publication_year'].toString()
        : '';
    case 'publication':
    case 'software':
    case 'dataset':
    case 'training':
    case 'other':
      return formatPublicationDate(data['publication_date']);
    default:
      return undefined;
  }
};

const setIsResearchProduct = (
  data: Partial<
    IOpenAIREResult &
      IDataSource &
      IService &
      ITraining &
      IGuideline &
      IBundle &
      IProvider
  >
) => {
  switch (data.type) {
    case 'publication':
    case 'software':
    case 'dataset':
    case 'other':
      return true;
    default:
      return false;
  }
};

export const allCollectionsAdapter: IAdapter = {
  id: URL_PARAM_NAME,
  adapter: (
    data: Partial<
      IOpenAIREResult &
        ITraining &
        IDataSource &
        IService &
        IGuideline &
        IBundle &
        IProvider
    > & {
      id: string;
    }
  ): IResult => ({
    isResearchProduct: setIsResearchProduct(data),
    id: data.id,
    title: data?.title?.join(' ') || '',
    catalogue: data?.catalogue || '',
    description: data?.description?.join(' ') || '',
    date: extractDate(data),
    languages: transformLanguages(data?.language),
    redirectUrl: redirectUrlAdapter(data.type || '', data),
    logoUrl: logoUrlAdapter(data.type || '', data),
    orderUrl: orderUrlAdapter(data.type || '', data),
    urls: data.url,
    license: data?.license,
    version: data?.version,
    contentType: data?.content_type,
    granularity: data?.granularity,
    dataQuality: data?.data_quality,
    coloredTags: [],
    tags: [
      {
        label: 'Publisher',
        values: toValueWithLabel(toArray(data?.publisher)),
        filter: 'publisher',
        showMoreThreshold: 10,
      },
    ],
    type: {
      label: data.type || '',
      value: data.type || '',
    },
    collection: COLLECTION,
    secondaryTags: [toKeywordsSecondaryTag(data.keywords ?? [], 'keywords')],
    offers: data.offers ?? [],
    ...parseStatistics(data),
  }),
};
