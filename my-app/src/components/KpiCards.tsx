import type { Ticker } from '../types';
import { differenceInDays } from 'date-fns';

interface KpiCardsProps {
  tickers: Ticker[];
  isLoading: boolean;
  isError: boolean;
}

export default function KpiCards({ tickers, isLoading, isError }: KpiCardsProps) {
  if (isLoading) {
    return (
      <div className="kpi-container">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="kpi-card skeleton" />
        ))}
      </div>
    );
  }

  if (isError) {
    return <div className="kpi-error">Failed to load KPIs.</div>;
  }

  const total = tickers.length;

  const { totalUpside, count } = tickers.reduce(
    (acc, t) => {
      if (t.fairValue !== undefined && t.priceClose !== undefined) {
        acc.totalUpside += ((t.fairValue - t.priceClose) / t.priceClose) * 100;
        acc.count += 1;
      }
      return acc;
    },
    { totalUpside: 0, count: 0 }
  );

  const avgUpside = count > 0 ? totalUpside / count : 0;

  const soonCount = tickers.filter((t) => {
    if (!t.earningsDate) return false;
    const days = differenceInDays(new Date(t.earningsDate), new Date());
    return days >= 0 && days <= 21;
  }).length;

  return (
    <div className="kpi-container">
      <div className="kpi-card">
        <span className="label">Total Tickers</span>
        <span className="value">{total}</span>
      </div>
      <div className="kpi-card">
        <span className="label">Avg Upside %</span>
        <span className="value">{avgUpside.toFixed(1)}%</span>
      </div>
      <div className="kpi-card">
        <span className="label">Next Earnings Soon</span>
        <span className="value">{soonCount}</span>
      </div>
    </div>
  );
}

