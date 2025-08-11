import { useState } from 'react';
import './App.css';
import TableRow from './components/TableRow';
import EditDrawer from './components/EditDrawer';
import type { Ticker } from './types';
import { ModeToggle } from '@/components/mode-toggle';

const emptyTicker: Ticker = {
  symbol: '',
  name: '',
  fairValue: undefined,
  fairAsOf: '',
  priceClose: undefined,
  priceAsOf: '',
  earningsDate: '',
  notes: '',
  edited: false,
};

const initialData: Ticker[] = [
  {
    symbol: 'MCD',
    name: 'McDonald\u2019s Corporation',
    fairValue: 150,
    fairAsOf: '2025-07-01',
    priceClose: 120,
    priceAsOf: '2025-08-10',
    earningsDate: '2025-10-25',
    notes: '',
    edited: false,
  },
  {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    fairValue: 180,
    fairAsOf: '2025-07-02',
    priceClose: 195,
    priceAsOf: '2025-08-10',
    earningsDate: '2025-10-30',
    notes: '',
    edited: false,
  },
];

function App() {
  const [tickers, setTickers] = useState<Ticker[]>(initialData);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [filterDate, setFilterDate] = useState('');
  const [search, setSearch] = useState('');

  const openEdit = (idx: number) => {
    setEditingIndex(idx);
    setDrawerOpen(true);
  };

  const addTicker = () => {
    setEditingIndex(null);
    setDrawerOpen(true);
  };

  const saveTicker = (t: Ticker) => {
    const list = [...tickers];
    if (editingIndex === null) {
      list.push({ ...t, edited: true });
    } else {
      list[editingIndex] = { ...t, edited: true };
    }
    setTickers(list);
    setDrawerOpen(false);
  };

  const cancelEdit = () => setDrawerOpen(false);

  const filtered = tickers.filter((t) => {
    const term = search.toLowerCase();
    const matchesSearch =
      t.symbol.toLowerCase().includes(term) || t.name.toLowerCase().includes(term);
    const matchesDate = filterDate ? t.priceAsOf === filterDate : true;
    return matchesSearch && matchesDate;
  });

  return (
    <div className="app-container">
      <div className="top-bar">
        <h1>Stock Watchlist</h1>
        <div className="controls">
          <button onClick={addTicker}>Add Ticker</button>
          <button onClick={() => alert('Export as CSV')}>Export CSV</button>
          <input
            type="date"
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            aria-label="Price As-Of"
          />
          <input
            type="text"
            placeholder="Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <ModeToggle />
        </div>
      </div>
      {filtered.length === 0 ? (
        <p className="empty-state">No tickers yet. Click Add Ticker to begin.</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Fair Value</th>
                <th>Fair As-Of</th>
                <th>Price Close</th>
                <th>Price As-Of</th>
                <th>Upcoming Earnings</th>
                <th>Upside %</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t, idx) => (
                <TableRow key={idx} ticker={t} onClick={() => openEdit(idx)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {drawerOpen && (
        <EditDrawer
          initial={editingIndex === null ? emptyTicker : tickers[editingIndex]}
          open={drawerOpen}
          onSave={saveTicker}
          onCancel={cancelEdit}
        />
      )}
    </div>
  );
}

export default App;
