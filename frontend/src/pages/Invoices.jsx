import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getInvoices, getCustomers, createInvoice } from '../api.js';
import { Card, ErrorBox, Loading, EmptyState, StatusBadge } from '../components/common.jsx';
import { formatMoney, formatDate, daysLabel } from '../format.js';

const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'sent', label: 'sent' },
  { value: 'part_paid', label: 'part_paid' },
  { value: 'paid', label: 'paid' },
  { value: 'draft', label: 'draft' },
  { value: 'void', label: 'void' },
];

function isoFromOffset(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function newItem() {
  return { description: '', quantity: '1', rate: '' };
}

function newForm() {
  return {
    customerId: '',
    issueDate: isoFromOffset(0),
    dueDate: isoFromOffset(7),
    notes: '',
    items: [newItem()],
  };
}

export default function Invoices() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [customers, setCustomers] = useState([]);
  const [customersError, setCustomersError] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(newForm);
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInvoices({ status })
      .then((rows) => {
        if (!cancelled) setInvoices(rows || []);
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
  }, [status]);

  useEffect(() => {
    let cancelled = false;
    getCustomers()
      .then((rows) => {
        if (!cancelled) setCustomers(rows || []);
      })
      .catch((err) => {
        if (!cancelled) setCustomersError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return invoices;
    return invoices.filter(
      (inv) =>
        String(inv.number || '').toLowerCase().includes(q) ||
        String(inv.customer_name || '').toLowerCase().includes(q)
    );
  }, [invoices, search]);

  function updateItem(index, field, value) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, i) => (i === index ? { ...item, [field]: value } : item)),
    }));
  }

  function addItem() {
    setForm((current) => ({ ...current, items: [...current.items, newItem()] }));
  }

  function removeItem(index) {
    setForm((current) => {
      if (current.items.length <= 1) return current;
      return { ...current, items: current.items.filter((_, i) => i !== index) };
    });
  }

  function toggleForm() {
    setFormError(null);
    setShowForm((open) => !open);
  }

  async function handleCreate(event) {
    event.preventDefault();
    setFormError(null);

    if (!form.customerId) {
      setFormError(new Error('Choose a customer'));
      return;
    }

    const items = [];
    for (const [index, item] of form.items.entries()) {
      const description = item.description.trim();
      const quantity = Number(item.quantity);
      const rate = Number(item.rate);
      if (!description) {
        setFormError(new Error(`Item ${index + 1}: description is required`));
        return;
      }
      if (!Number.isInteger(quantity) || quantity < 1) {
        setFormError(new Error(`Item ${index + 1}: quantity must be a whole number of at least 1`));
        return;
      }
      if (item.rate === '' || Number.isNaN(rate) || rate < 0) {
        setFormError(new Error(`Item ${index + 1}: rate must be zero or more`));
        return;
      }
      items.push({
        description,
        quantity,
        unit_price_minor: Math.round(rate * 100),
      });
    }

    setSaving(true);
    try {
      const created = await createInvoice({
        customer_id: Number(form.customerId),
        issue_date: form.issueDate,
        due_date: form.dueDate,
        items,
        notes: form.notes,
        status: 'sent',
      });
      navigate(`/invoices/${created.id}`);
    } catch (err) {
      setFormError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Invoices</h1>
        <button type="button" className="btn btn-primary" onClick={toggleForm}>
          {showForm ? 'Close form' : 'New invoice'}
        </button>
      </div>

      {showForm && (
        <Card title="New invoice">
          <ErrorBox error={customersError} />
          <ErrorBox error={formError} />
          <form className="form" onSubmit={handleCreate}>
            <div className="form-row">
              <label className="field">
                <span>Customer</span>
                <select
                  value={form.customerId}
                  onChange={(e) => setForm({ ...form, customerId: e.target.value })}
                >
                  <option value="">Select a customer</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Issue date</span>
                <input
                  type="date"
                  value={form.issueDate}
                  onChange={(e) => setForm({ ...form, issueDate: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Due date</span>
                <input
                  type="date"
                  value={form.dueDate}
                  onChange={(e) => setForm({ ...form, dueDate: e.target.value })}
                />
              </label>
            </div>

            <h3>Items</h3>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th className="num">Quantity</th>
                    <th className="num">Rate (₹)</th>
                    <th className="num">Amount</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, index) => {
                    const amount = Math.round(Number(item.rate || 0) * 100) * Math.max(Number(item.quantity) || 0, 0);
                    return (
                      <tr key={index}>
                        <td>
                          <input
                            type="text"
                            value={item.description}
                            onChange={(e) => updateItem(index, 'description', e.target.value)}
                            maxLength={200}
                          />
                        </td>
                        <td className="num">
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={item.quantity}
                            onChange={(e) => updateItem(index, 'quantity', e.target.value)}
                          />
                        </td>
                        <td className="num">
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={item.rate}
                            onChange={(e) => updateItem(index, 'rate', e.target.value)}
                          />
                        </td>
                        <td className="num">{formatMoney(amount)}</td>
                        <td>
                          <button
                            type="button"
                            className="btn"
                            disabled={form.items.length <= 1}
                            onClick={() => removeItem(index)}
                          >
                            Remove item
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div>
              <button type="button" className="btn" onClick={addItem}>
                Add item
              </button>
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
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Creating...' : 'Create invoice'}
              </button>
            </div>
          </form>
        </Card>
      )}

      <div className="filters">
        <label className="field">
          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Search</span>
          <input
            type="search"
            placeholder="Invoice number or customer"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>

      <ErrorBox error={error} />

      {loading ? (
        <Loading label="Loading invoices..." />
      ) : visible.length === 0 ? (
        <EmptyState text="No invoices match these filters." />
      ) : (
        <div className="table-wrap">
          <table className="table clickable">
            <thead>
              <tr>
                <th>Number</th>
                <th>Customer</th>
                <th>Issue date</th>
                <th>Due date</th>
                <th className="num">Total</th>
                <th className="num">Paid</th>
                <th className="num">Balance</th>
                <th>Status</th>
                <th>Overdue</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((inv) => (
                <tr key={inv.id} onClick={() => navigate(`/invoices/${inv.id}`)}>
                  <td>{inv.number}</td>
                  <td>{inv.customer_name}</td>
                  <td>{formatDate(inv.issue_date)}</td>
                  <td>{formatDate(inv.due_date)}</td>
                  <td className="num">{formatMoney(inv.total_minor)}</td>
                  <td className="num">{formatMoney(inv.paid_minor)}</td>
                  <td className="num">{formatMoney(inv.balance_minor)}</td>
                  <td>
                    <StatusBadge status={inv.status} />
                  </td>
                  <td>{daysLabel(inv.days_overdue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
