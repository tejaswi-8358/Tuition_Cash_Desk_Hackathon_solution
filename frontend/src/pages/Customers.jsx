import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getCustomers, createCustomer, updateCustomer, getCustomer } from '../api.js';
import { Card, ErrorBox, Loading, EmptyState, StatusBadge } from '../components/common.jsx';
import { formatMoney, formatDate } from '../format.js';

const EMPTY_FORM = { name: '', phone: '', delay: '0', notes: '' };

function displayPhone(phone) {
  const raw = String(phone || '');
  const digits = raw.replace(/[\s+-]/g, '');
  if (/^91\d{10}$/.test(digits)) {
    return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  }
  return raw;
}

function isValidPhone(phone) {
  return /^\d{8,15}$/.test(phone.replace(/[\s+-]/g, ''));
}

// Returns the delay as an integer 0-180, or null when the input is not valid.
function parseDelay(value) {
  const text = String(value).trim();
  if (text === '') return null;
  const n = Number(text);
  if (!Number.isInteger(n) || n < 0 || n > 180) return null;
  return n;
}

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState({ id: null, loading: false, error: null, invoices: [] });
  const [delayInput, setDelayInput] = useState('0');
  const [delayMessage, setDelayMessage] = useState(null);
  const [delayError, setDelayError] = useState(null);
  const [savingDelay, setSavingDelay] = useState(false);

  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState(null);
  const [formMessage, setFormMessage] = useState(null);
  const [savingCustomer, setSavingCustomer] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCustomers()
      .then((rows) => {
        if (!cancelled) setCustomers(rows || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (expandedId === null) return undefined;
    let cancelled = false;
    setDetail({ id: expandedId, loading: true, error: null, invoices: [] });
    getCustomer(expandedId)
      .then((data) => {
        if (!cancelled) {
          setDetail({ id: expandedId, loading: false, error: null, invoices: (data && data.invoices) || [] });
        }
      })
      .catch((err) => {
        if (!cancelled) setDetail({ id: expandedId, loading: false, error: err, invoices: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [expandedId]);

  async function loadCustomers() {
    try {
      const rows = await getCustomers();
      setCustomers(rows || []);
    } catch (err) {
      setError(err);
    }
  }

  function toggleRow(customer) {
    setDelayMessage(null);
    setDelayError(null);
    if (expandedId === customer.id) {
      setExpandedId(null);
      return;
    }
    setDelayInput(String(customer.default_delay_days ?? 0));
    setExpandedId(customer.id);
  }

  async function handleSaveDelay(customerId) {
    setDelayMessage(null);
    setDelayError(null);
    const days = parseDelay(delayInput);
    if (days === null) {
      setDelayError(new Error('Delay days must be a whole number from 0 to 180'));
      return;
    }
    setSavingDelay(true);
    try {
      await updateCustomer(customerId, { default_delay_days: days });
      await loadCustomers();
      setDelayMessage('Saved');
    } catch (err) {
      setDelayError(err);
    } finally {
      setSavingDelay(false);
    }
  }

  async function handleCreate(event) {
    event.preventDefault();
    setFormError(null);
    setFormMessage(null);

    const name = form.name.trim();
    const phone = form.phone.trim();
    const days = parseDelay(form.delay);
    const notes = form.notes.trim();

    if (!name) {
      setFormError(new Error('Name is required'));
      return;
    }
    if (!phone) {
      setFormError(new Error('Phone is required'));
      return;
    }
    if (!isValidPhone(phone)) {
      setFormError(new Error('Phone must have 8 to 15 digits (spaces, + and - are ignored)'));
      return;
    }
    if (days === null) {
      setFormError(new Error('Default delay days must be a whole number from 0 to 180'));
      return;
    }

    setSavingCustomer(true);
    try {
      await createCustomer({ name, phone, default_delay_days: days, notes });
      await loadCustomers();
      setForm(EMPTY_FORM);
      setFormMessage('Customer added');
    } catch (err) {
      setFormError(err);
    } finally {
      setSavingCustomer(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Customers</h1>
      </div>

      <ErrorBox error={error} />

      {loading ? (
        <Loading label="Loading customers..." />
      ) : customers.length === 0 ? (
        <EmptyState text="No customers yet. Add one below." />
      ) : (
        <div className="table-wrap">
          <table className="table clickable">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th className="num">Delay days</th>
                <th className="num">Outstanding</th>
                <th className="num">Overdue</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <Fragment key={c.id}>
                  <tr onClick={() => toggleRow(c)}>
                    <td>{c.name}</td>
                    <td>{displayPhone(c.phone)}</td>
                    <td className="num">{c.default_delay_days}</td>
                    <td className="num">{formatMoney(c.outstanding_minor)}</td>
                    <td className="num">{formatMoney(c.overdue_minor)}</td>
                  </tr>
                  {expandedId === c.id && (
                    <tr>
                      <td colSpan={5}>
                        <div className="customer-detail">
                          <div className="form-row">
                            <label className="field">
                              <span>Default delay (days)</span>
                              <input
                                type="number"
                                min="0"
                                max="180"
                                step="1"
                                value={delayInput}
                                onChange={(e) => setDelayInput(e.target.value)}
                              />
                            </label>
                            <div className="form-actions">
                              <button
                                type="button"
                                className="btn btn-primary"
                                disabled={savingDelay}
                                onClick={() => handleSaveDelay(c.id)}
                              >
                                {savingDelay ? 'Saving...' : 'Save delay'}
                              </button>
                            </div>
                          </div>
                          {delayMessage && <p className="saved-msg">{delayMessage}</p>}
                          <ErrorBox error={delayError} />

                          <h3>Invoices</h3>
                          {detail.id !== c.id || detail.loading ? (
                            <Loading label="Loading invoices..." />
                          ) : detail.error ? (
                            <ErrorBox error={detail.error} />
                          ) : detail.invoices.length === 0 ? (
                            <EmptyState text="No invoices for this customer." />
                          ) : (
                            <ul className="plain-list">
                              {detail.invoices.map((inv) => (
                                <li key={inv.id}>
                                  <Link to={`/invoices/${inv.id}`}>{inv.number}</Link>
                                  {' · due '}
                                  {formatDate(inv.due_date)}
                                  {' · '}
                                  <StatusBadge status={inv.status} />
                                  {' · balance '}
                                  {formatMoney(inv.balance_minor)}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card title="Add customer">
        <ErrorBox error={formError} />
        {formMessage && <p className="saved-msg">{formMessage}</p>}
        <form className="form" onSubmit={handleCreate}>
          <div className="form-row">
            <label className="field">
              <span>Name</span>
              <input
                type="text"
                value={form.name}
                maxLength={120}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Phone</span>
              <input
                type="tel"
                value={form.phone}
                placeholder="e.g. +91 98765 43210"
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Default delay (days)</span>
              <input
                type="number"
                min="0"
                max="180"
                step="1"
                value={form.delay}
                onChange={(e) => setForm({ ...form, delay: e.target.value })}
              />
            </label>
          </div>
          <label className="field">
            <span>Notes</span>
            <textarea
              rows={2}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </label>
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={savingCustomer}>
              {savingCustomer ? 'Adding...' : 'Add customer'}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
