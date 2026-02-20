export interface IDataset {
  id: string;
  type: string;

  url: string[];
  version: string;
  title: string[];
  description?: string[];

  publication_date?: string;
  last_update?: string;

  language?: string[];
  publisher?: string;

  license?: string[];

  keywords?: string[];
  keywords_tg?: string[];

  data_quality?: string;
  granularity?: string;

  content_type?: string;
}
