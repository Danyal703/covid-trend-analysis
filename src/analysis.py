"""Historical reported COVID-19 case trends; run with python -m src.analysis."""
import json
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from .common import ROOT, load_source, plot_style, save_run

NON_GEOGRAPHIC = {'Diamond Princess', 'MS Zaandam'}


def clean_cases(raw):
    """Aggregate provinces, reshape dates, retain negative reporting revisions."""
    required = {'Province/State', 'Country/Region', 'Lat', 'Long'}
    if not required.issubset(raw.columns):
        raise ValueError('Missing expected Johns Hopkins metadata columns.')
    dates = [c for c in raw.columns if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{2}', c)]
    if not dates or raw['Country/Region'].isna().any():
        raise ValueError('Missing dates or country/region labels.')
    if raw.duplicated(['Country/Region', 'Province/State']).any():
        raise ValueError('Duplicate geographic rows must be reviewed before aggregation.')
    counts = raw[dates].apply(pd.to_numeric, errors='raise')
    if counts.isna().any().any() or (counts < 0).any().any() or (counts % 1 != 0).any().any():
        raise ValueError('Cumulative counts must be nonnegative, nonmissing integers.')
    keep = ~raw['Country/Region'].isin(NON_GEOGRAPHIC)
    geographic = pd.concat([raw.loc[keep, ['Country/Region']], counts.loc[keep]], axis=1)
    grouped = geographic.groupby('Country/Region', sort=True)[dates].sum()
    tidy = grouped.reset_index().melt(id_vars='Country/Region', var_name='date', value_name='cumulative_cases')
    tidy = tidy.rename(columns={'Country/Region': 'country'})
    tidy['date'] = pd.to_datetime(tidy['date'], format='%m/%d/%y')
    tidy = tidy.sort_values(['country', 'date']).reset_index(drop=True)
    unique_dates = pd.DatetimeIndex(sorted(tidy['date'].unique()))
    if len(unique_dates) != len(pd.date_range(unique_dates.min(), unique_dates.max())):
        raise ValueError('Missing calendar dates: daily differences would be misleading.')
    tidy['net_new_cases'] = tidy.groupby('country')['cumulative_cases'].diff()
    tidy['negative_revision'] = tidy['net_new_cases'].lt(0)
    tidy['new_cases_7d'] = tidy.groupby('country')['net_new_cases'].transform(lambda x: x.rolling(7, min_periods=7).mean())
    audit = {
        'source_geographic_rows': int(len(raw)),
        'source_daily_cells': int(len(raw) * len(dates)),
        'excluded_non_geographic_rows': int(len(raw) - len(geographic)),
        'country_day_records': int(len(tidy)),
        'countries_and_regions': int(tidy['country'].nunique()),
        'negative_country_day_revisions': int(tidy['negative_revision'].sum()),
        'first_day_differences_unavailable': int(tidy['net_new_cases'].isna().sum()),
        'missing_cumulative_values': int(counts.isna().sum().sum()),
    }
    return tidy, audit


def run():
    tidy, metrics = clean_cases(pd.read_csv(load_source('confirmed.csv')))
    global_daily = tidy.groupby('date')['cumulative_cases'].sum().to_frame()
    global_daily['net_new_cases'] = global_daily['cumulative_cases'].diff()
    global_daily['new_cases_7d'] = global_daily['net_new_cases'].rolling(7, min_periods=7).mean()
    peak_date = global_daily['new_cases_7d'].idxmax()
    metrics.update({
        'date_start': str(tidy['date'].min().date()), 'date_end': str(tidy['date'].max().date()),
        'global_peak_7d_window_end': str(peak_date.date()),
        'global_peak_7d_net_cases_per_day': float(global_daily.loc[peak_date, 'new_cases_7d']),
        'final_cumulative_reported_cases': int(global_daily['cumulative_cases'].iloc[-1]),
        'global_negative_revision_days': int(global_daily['net_new_cases'].lt(0).sum()),
        'method': 'Province sums; ship rows excluded; first difference unknown; negative revisions retained; trailing 7-day mean.',
    })
    reports = save_run(metrics, ['pandas', 'numpy', 'matplotlib'])
    processed = ROOT / 'data/processed'
    processed.mkdir(parents=True, exist_ok=True)
    tidy.to_csv(processed / 'country_daily.csv', index=False)
    global_daily.to_csv(reports / 'global_daily.csv')
    peaks = tidy.loc[tidy.groupby('country')['new_cases_7d'].idxmax(), ['country', 'date', 'new_cases_7d']]
    peaks.sort_values('new_cases_7d', ascending=False).to_csv(reports / 'country_peaks.csv', index=False)
    tidy.loc[tidy['negative_revision'], ['country', 'date', 'net_new_cases']].to_csv(reports / 'negative_revisions.csv', index=False)
    plot_style()
    fig, ax = plt.subplots(figsize=(11, 4.8), layout='constrained')
    ax.plot(global_daily.index, global_daily['net_new_cases'] / 1e6, color='#b4c7d9', lw=.6, label='Daily net change')
    ax.plot(global_daily.index, global_daily['new_cases_7d'] / 1e6, color='#007f86', lw=2, label='Trailing 7-day mean')
    ax.axvline(peak_date, color='#e48b32', ls='--', label=f'Peak window ends {peak_date.date()}')
    ax.set(title='Global reported COVID-19 case trends', ylabel='Net reported cases per day (millions)', xlabel='Report date')
    ax.legend(loc='upper right', frameon=False)
    fig.savefig(reports / 'global_trends.png')
    plt.close(fig)
    latest = tidy[tidy['date'].eq(tidy['date'].max())].nlargest(6, 'cumulative_cases')['country']
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.5), layout='constrained')
    for ax, country in zip(axes.flat, latest):
        subset = tidy[tidy['country'].eq(country)]
        ax.plot(subset['date'], subset['new_cases_7d'] / 1e3, color='#007f86')
        ax.set(title=country, ylabel='7-day net cases (thousands)')
        ax.tick_params(axis='x', rotation=30)
    fig.suptitle('Six largest final reported totals | independent vertical scales')
    fig.savefig(reports / 'country_comparison.png')
    plt.close(fig)
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == '__main__':
    run()
