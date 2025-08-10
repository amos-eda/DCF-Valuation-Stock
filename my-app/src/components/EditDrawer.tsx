import React, { useEffect, useState } from 'react';
import type { Ticker } from '../types';

interface Props {
  initial: Ticker;
  open: boolean;
  onSave: (t: Ticker) => void;
  onCancel: () => void;
}

const EditDrawer: React.FC<Props> = ({ initial, open, onSave, onCancel }) => {
  const [form, setForm] = useState<Ticker>(initial);

  useEffect(() => {
    setForm(initial);
  }, [initial]);

  const update = (field: keyof Ticker, value: string) => {
    setForm({ ...form, [field]: value });
  };

  const updateNumber = (field: keyof Ticker, value: string) => {
    const num = value === '' ? undefined : Number(value);
    setForm({ ...form, [field]: num });
  };

  return (
    <div className={`drawer ${open ? 'open' : ''}`}>
      <h2>{initial.symbol ? 'Edit Ticker' : 'Add Ticker'}</h2>
      <label>
        Symbol
        <input
          value={form.symbol || ''}
          onChange={(e) => update('symbol', e.target.value)}
        />
      </label>
      <label>
        Name
        <input value={form.name || ''} onChange={(e) => update('name', e.target.value)} />
      </label>
      <label>
        Fair Value
        <input
          type="number"
          value={form.fairValue ?? ''}
          onChange={(e) => updateNumber('fairValue', e.target.value)}
        />
      </label>
      <label>
        Fair As-Of
        <input
          type="date"
          value={form.fairAsOf || ''}
          onChange={(e) => update('fairAsOf', e.target.value)}
        />
      </label>
      <label>
        Price Close
        <input
          type="number"
          value={form.priceClose ?? ''}
          onChange={(e) => updateNumber('priceClose', e.target.value)}
        />
      </label>
      <label>
        Price As-Of
        <input
          type="date"
          value={form.priceAsOf || ''}
          onChange={(e) => update('priceAsOf', e.target.value)}
        />
      </label>
      <label>
        Upcoming Earnings
        <input
          type="date"
          value={form.earningsDate || ''}
          onChange={(e) => update('earningsDate', e.target.value)}
        />
      </label>
      <label>
        Notes
        <textarea
          rows={3}
          value={form.notes || ''}
          onChange={(e) => update('notes', e.target.value)}
        />
      </label>
      <div className="actions">
        <button onClick={() => onSave(form)}>Save</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
};

export default EditDrawer;
