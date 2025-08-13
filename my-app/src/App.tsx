import { useEffect, useRef, useState } from 'react';
import { format } from 'date-fns';
import './App.css';
import TableRow from './components/TableRow';
import EditDrawer from './components/EditDrawer';
import KpiCards from './components/KpiCards';
import type { Ticker } from './types';
import { ModeToggle } from '@/components/mode-toggle';
import AppShell from '@/components/AppShell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { useTheme } from '@/components/theme-provider';

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
  const [tickers, setTickers] = useState<Ticker[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [filterDate, setFilterDate] = useState<Date | undefined>();
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const { theme, setTheme } = useTheme();

  // mimic async load
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        setTickers(initialData);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, []);

  const openEdit = (idx: number) => {
    if (idx >= 0) {
      setEditingIndex(idx);
      setDrawerOpen(true);
    }
  };

  const addTicker = () => {
    setEditingIndex(null);
    setDrawerOpen(true);
  };

  const exportCsv = () => {
    alert('Export as CSV');
  };

  const saveTicker = (t: Ticker) => {
    const list = tickers ? [...tickers] : [];
    if (editingIndex === null) {
      list.push({ ...t, edited: true });
    } else if (editingIndex >= 0 && editingIndex < list.length) {
      list[editingIndex] = { ...t, edited: true };
    }
    setTickers(list);
    setDrawerOpen(false);
  };

  const cancelEdit = () => setDrawerOpen(false);

  // keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== searchRef.current) {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === 'a') {
        e.preventDefault();
        addTicker();
      }
      if (e.key === 'e') {
        e.preventDefault();
        exportCsv();
      }
      if (e.key === 't') {
        e.preventDefault();
        setTheme(theme === 'light' ? 'dark' : 'light');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [theme, setTheme]);

  const filtered = (tickers ?? []).filter((t) => {
    const term = search.toLowerCase();
    const matchesSearch =
      t.symbol.toLowerCase().includes(term) || t.name.toLowerCase().includes(term);
    const matchesDate = filterDate ? t.priceAsOf === format(filterDate, 'yyyy-MM-dd') : true;
    return matchesSearch && matchesDate;
  });

  return (
    <AppShell
      toolbar={
        <>
          <h1 className="text-xl font-semibold">Stock Watchlist</h1>
          <div className="flex items-center gap-2">
            <Button onClick={addTicker}>Add Ticker</Button>
            <Button variant="outline" onClick={exportCsv}>
              Export CSV
            </Button>
            <Popover>
              <PopoverTrigger>
                <Button variant="outline" className="w-[150px] justify-start text-left font-normal">
                  {filterDate ? format(filterDate, 'yyyy-MM-dd') : 'Price As-Of'}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="p-0">
                <Calendar selected={filterDate} onSelect={setFilterDate} />
              </PopoverContent>
            </Popover>
            <Input
              ref={searchRef}
              type="text"
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-[150px]"
            />
            <ModeToggle />
          </div>
        </>
      }
    >
      {/* KPI cards honor loading/error */}
      <KpiCards tickers={filtered} isLoading={loading} isError={error} />

      {loading ? (
        <p className="empty-state">Loading tickers...</p>
      ) : error ? (
        <p className="empty-state">Failed to load tickers.</p>
      ) : filtered.length === 0 ? (
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
              {filtered.map((t) => {
                // ensure we edit the correct row from the original list even when filtered
                const originalIndex = (tickers ?? []).indexOf(t);
                return (
                  <TableRow
                    key={t.symbol}
                    ticker={t}
                    onClick={() => openEdit(originalIndex)}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {drawerOpen && tickers && (
        <EditDrawer
          initial={editingIndex === null ? emptyTicker : tickers[editingIndex]}
          open={drawerOpen}
          onSave={saveTicker}
          onCancel={cancelEdit}
        />
      )}
    </AppShell>
  );
}

export default App;
