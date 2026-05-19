import { queryChanger, queryChangerAdv } from './utils';

describe('queryChanger', () => {
  it('does not add fuzzy matching for medium-length terms anymore', () => {
    expect(queryChanger('science', false)).toBe('science');
    expect(queryChangerAdv('science', false)).toBe('science');
  });

  it('keeps fuzzy matching for longer terms in non-exact mode', () => {
    expect(queryChanger('repository', false)).toBe('repository~1');
    expect(queryChangerAdv('repository', false)).toBe('repository~1');
  });

  it('only applies fuzzy matching to long segments in hyphenated terms', () => {
    expect(queryChanger('data-repository', false)).toBe('data repository~1');
    expect(queryChangerAdv('data-repository', false)).toBe(
      'data repository~1'
    );
  });
});
