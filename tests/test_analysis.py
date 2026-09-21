import pandas as pd
import pytest

from src.analysis import clean_cases


def example():
    return pd.DataFrame({'Province/State': ['North', 'South', None],
                         'Country/Region': ['Example', 'Example', 'Diamond Princess'],
                         'Lat': [0, 1, 2], 'Long': [0, 1, 2],
                         '1/1/20': [100, 50, 900], '1/2/20': [110, 55, 999],
                         '1/3/20': [108, 55, 999]})


def test_province_sums_and_revisions_are_not_clipped():
    tidy, audit = clean_cases(example())
    assert tidy['cumulative_cases'].tolist() == [150, 165, 163]
    assert pd.isna(tidy['net_new_cases'].iloc[0])
    assert tidy['net_new_cases'].iloc[1:].tolist() == [15, -2]
    assert audit['negative_country_day_revisions'] == 1
    assert audit['excluded_non_geographic_rows'] == 1
    assert tidy['new_cases_7d'].isna().all()


def test_first_rolling_window_needs_seven_observed_changes():
    raw = example().iloc[:1].drop(columns=['1/1/20', '1/2/20', '1/3/20'])
    for day in range(1, 10):
        raw[f'1/{day}/20'] = 100 + day
    tidy, _ = clean_cases(raw)
    assert tidy['new_cases_7d'].iloc[:7].isna().all()
    assert tidy['new_cases_7d'].iloc[7] == 1


def test_missing_calendar_day_rejected():
    with pytest.raises(ValueError, match='Missing calendar dates'):
        clean_cases(example().drop(columns='1/2/20'))


def test_missing_count_is_not_silently_zero_filled():
    raw = example()
    raw.loc[0, '1/2/20'] = float('nan')
    with pytest.raises(ValueError, match='nonmissing'):
        clean_cases(raw)


def test_duplicate_geographic_rows_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        clean_cases(pd.concat([example(), example().iloc[:1]], ignore_index=True))
