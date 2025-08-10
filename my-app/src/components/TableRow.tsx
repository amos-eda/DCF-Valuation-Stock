import React from 'react';
import Badge from './Badge';
import type { Ticker, Status } from '../types';

interface RowProps {
  ticker: Ticker;
  onClick: () => void;
}

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

const calcUpside = (t: Ticker): number | null => {
  if (t.fairValue == null || t.priceClose == null || t.priceClose === 0) return null;
  return ((t.fairValue - t.priceClose) / t.priceClose) * 100;
};

const statusFromUpside = (t: Ticker, up: number | null): Status => {
  if (t.fairValue == null || t.priceClose == null) return 'INCOMPLETE';
  if (up != null) {
    if (up >= 20) return 'UNDERVALUED';
    if (up <= -10) return 'OVERVALUED';
    return 'FAIR';
  }
  return 'INCOMPLETE';
};

const isSoon = (date?: string): boolean => {
  if (!date) return false;
  const now = new Date();
  const d = new Date(date);
  const diff = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 21;
};

const TableRow: React.FC<RowProps> = ({ ticker, onClick }) => {
  const upside = calcUpside(ticker);
  const status = statusFromUpside(ticker, upside);
  const soon = isSoon(ticker.earningsDate);
  const upsideText =
    upside == null ? '' : `${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`;
  let upsideClass = 'upside-neutral';
  if (upside != null) {
    if (upside >= 20) upsideClass = 'upside-positive';
    else if (upside <= -10) upsideClass = 'upside-negative';
  }

  return (
    <tr className={ticker.edited ? 'edited' : ''} onClick={onClick}>
      <td>
        <div className="symbol">{ticker.symbol}</div>
        <div className="name">{ticker.name}</div>
      </td>
      <td>{ticker.fairValue != null ? currency.format(ticker.fairValue) : ''}</td>
      <td>{ticker.fairAsOf}</td>
      <td>{ticker.priceClose != null ? currency.format(ticker.priceClose) : ''}</td>
      <td>{ticker.priceAsOf}</td>
      <td>
        {ticker.earningsDate}
        {soon && <Badge text="Soon" type="SOON" />}
      </td>
      <td className={upsideClass} title="(Fair − Price) / Price">{upsideText}</td>
      <td>
        <Badge text={status} type={status} />
      </td>
    </tr>
  );
};

export default TableRow;
