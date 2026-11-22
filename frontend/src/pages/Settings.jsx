import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api.js';
import { Card, ErrorBox, Loading } from '../components/common.jsx';

// Converts a minor-unit value (paise, possibly a string) to a rupees string for the form.
function toRupees(minor) {
  return (Number(minor || 0) / 100).toFixed(2);
}

// Returns the amount in rupees as a number (>= 0), or null when the input is not valid.
function parseRupees(value) {
  const text = String(value).trim();
  if (text === '') return null;
  const n = Number(text);
  if (Number.isNaN(n) || n < 0) return null;
  return n;
}

export default function Settings() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [dataMode, setDataMode] = useState('');

  const [form, setForm] = useState({
    businessName: '',
    currencySymbol: '',
    openingCash: '0.00',
    safeBalance: '0.00',
  });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((s) => {
        if (cancelled) return;
        setDataMode(s.data_mode || '');
        setForm({
          businessName: s.business_name || '',
          currencySymbol: s.currency_symbol || '',
          openingCash: toRupees(s.opening_cash_minor),
          safeBalance: toRupees(s.safe_balance_minor),
        });
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(event) {
    event.preventDefault();
    setSaveError(null);
    setSaved(false);

    const businessName = form.businessName.trim();
    const currencySymbol = form.currencySymbol.trim();

    if (!businessName) {
      setSaveError(new Error('Business name is required'));
      return;
    }
    if (businessName.length > 120) {
      setSaveError(new Error('Business name must be 120 characters or fewer'));
      return;
    }
    if (currencySymbol.length > 5) {
      setSaveError(new Error('Currency symbol must be 5 characters or fewer'));
      return;
    }

    const opening = parseRupees(form.openingCash);
    if (opening === null) {
      setSaveError(new Error('Opening cash must be zero or more'));
      return;
    }
    const safe = parseRupees(form.safeBalance);
    if (safe === null) {
      setSaveError(new Error('Safe balance must be zero or more'));
      return;
    }

    setSaving(true);
    try {
      const updated = await updateSettings({
        business_name: businessName,
        currency_symbol: currencySymbol,
        opening_cash_minor: Math.round(opening * 100),
        safe_balance_minor: Math.round(safe * 100),
      });
      if (updated && updated.data_mode) setDataMode(updated.data_mode);
      setSaved(true);
    } catch (err) {
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {loading ? (
        <Loading label="Loading settings..." />
      ) : loadError ? (
        <ErrorBox error={loadError} />
      ) : (
        <Card title="Business">
          <ErrorBox error={saveError} />
          {saved && <p className="saved-msg">Saved.</p>}
          <form className="form" onSubmit={handleSave}>
            <div className="form-row">
              <label className="field">
                <span>Business name</span>
                <input
                  type="text"
                  maxLength={120}
                  value={form.businessName}
                  onChange={(e) => setForm({ ...form, businessName: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Currency symbol</span>
                <input
                  type="text"
                  maxLength={5}
                  value={form.currencySymbol}
                  onChange={(e) => setForm({ ...form, currencySymbol: e.target.value })}
                />
              </label>
            </div>
            <div className="form-row">
              <label className="field">
                <span>Opening cash (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.openingCash}
                  onChange={(e) => setForm({ ...form, openingCash: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Safe balance (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.safeBalance}
                  onChange={(e) => setForm({ ...form, safeBalance: e.target.value })}
                />
              </label>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Saving...' : 'Save settings'}
              </button>
            </div>
          </form>

          <p>
            <strong>Data mode: </strong>
            {dataMode}
          </p>
          <p className="muted">
            sample means demo records are marked is_sample and can be deleted; live means real business data.
          </p>
        </Card>
      )}
    </div>
  );
}
