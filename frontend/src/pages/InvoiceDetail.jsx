import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  getInvoice,
  recordPayment,
  deletePayment,
  updateInvoiceStatus,
  sendReminder,
} from '../api.js';
import { Card, ErrorBox, Loading, EmptyState, StatusBadge } from '../components/common.jsx';
import { formatMoney, formatDate, daysLabel } from '../format.js';

const METHODS = ['cash', 'bank', 'upi', 'other'];

function todayIso() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function InvoiceDetail() {
  const { id } = useParams();
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [amount, setAmount] = useState('');
  const [paidOn, setPaidOn] = useState(todayIso());
  const [method, setMethod] = useState('upi');
  const [note, setNote] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInvoice(id)
      .then((data) => {
        if (!cancelled) setInvoice(data);
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
  }, [id, reloadKey]);

  function reload() {
    setReloadKey((k) => k + 1);
  }

  async function runAction(fn) {
    setActionError(null);
    setBusy(true);
    try {
      await fn();
      reload();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  function handleRecordPayment(event) {
    event.preventDefault();
    const value = Number(amount);
    if (!amount || Number.isNaN(value) || value <= 0) {
      setActionError(new Error('Enter an amount greater than zero'));
      return;
    }
    runAction(async () => {
      await recordPayment(id, {
        amount_minor: Math.round(value * 100),
        paid_on: paidOn,
        method,
        note,
      });
      setAmount('');
      setNote('');
    });
  }

  function handleDeletePayment(paymentId) {
    if (!window.confirm('Delete this payment?')) return;
    runAction(() => deletePayment(id, paymentId));
  }

  function handleStatus(status) {
    runAction(() => updateInvoiceStatus(id, status));
  }

  function handleVoid() {
    if (!window.confirm('Void this invoice?')) return;
    handleStatus('void');
  }

  function handleReminder() {
    runAction(async () => {
      const res = await sendReminder(id);
      if (res && res.whatsapp_url) {
        window.open(res.whatsapp_url, '_blank');
      }
    });
  }

  if (loading && !invoice) return <Loading label="Loading invoice..." />;

  if (!invoice) {
    return (
      <div className="page">
        <Link to="/invoices">← Invoices</Link>
        <ErrorBox error={error} />
      </div>
    );
  }

  const payments = invoice.payments || [];
  const items = invoice.items || [];
  const reminders = invoice.reminders || [];
  const hasPayments = payments.length > 0;
  const canMarkDraft = invoice.status !== 'paid' && !hasPayments && invoice.status !== 'draft';
  const canMarkSent = invoice.status !== 'paid' && !hasPayments && invoice.status !== 'sent';
  const canVoid = invoice.status !== 'paid' && invoice.status !== 'void';
  const canRecordPayment =
    invoice.status !== 'void' && invoice.status !== 'draft' && Number(invoice.balance_minor) > 0;

  return (
    <div className="page">
      <Link to="/invoices">← Invoices</Link>
      <ErrorBox error={error} />
      <ErrorBox error={actionError} />

      <div className="page-header">
        <h1>Invoice {invoice.number}</h1>
        <StatusBadge status={invoice.status} />
      </div>

      <Card title="Details">
        <dl className="details">
          <dt>Customer</dt>
          <dd>{invoice.customer_name}</dd>
          <dt>Phone</dt>
          <dd>{invoice.customer_phone || '-'}</dd>
          <dt>Issue date</dt>
          <dd>{formatDate(invoice.issue_date)}</dd>
          <dt>Due date</dt>
          <dd>{formatDate(invoice.due_date)}</dd>
          <dt>Overdue</dt>
          <dd>{daysLabel(invoice.days_overdue)}</dd>
        </dl>
      </Card>

      <Card title="Items">
        {items.length === 0 ? (
          <EmptyState text="No items." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th className="num">Qty</th>
                  <th className="num">Rate</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.description}</td>
                    <td className="num">{item.quantity}</td>
                    <td className="num">{formatMoney(item.unit_price_minor)}</td>
                    <td className="num">{formatMoney(item.line_total_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <dl className="totals">
          <dt>Total</dt>
          <dd>{formatMoney(invoice.total_minor)}</dd>
          <dt>Paid</dt>
          <dd>{formatMoney(invoice.paid_minor)}</dd>
          <dt>Balance</dt>
          <dd>{formatMoney(invoice.balance_minor)}</dd>
        </dl>
      </Card>

      <Card title="Payments">
        {payments.length === 0 ? (
          <EmptyState text="No payments recorded." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Paid on</th>
                  <th className="num">Amount</th>
                  <th>Method</th>
                  <th>Note</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td>{formatDate(p.paid_on)}</td>
                    <td className="num">{formatMoney(p.amount_minor)}</td>
                    <td>{p.method}</td>
                    <td>{p.note}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-danger"
                        disabled={busy}
                        onClick={() => handleDeletePayment(p.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h3>Record payment</h3>
        <form className="form" onSubmit={handleRecordPayment}>
          <div className="form-row">
            <label className="field">
              <span>Amount (₹)</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={amount}
                disabled={!canRecordPayment}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Paid on</span>
              <input
                type="date"
                value={paidOn}
                disabled={!canRecordPayment}
                onChange={(e) => setPaidOn(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Method</span>
              <select
                value={method}
                disabled={!canRecordPayment}
                onChange={(e) => setMethod(e.target.value)}
              >
                {METHODS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Note</span>
              <input
                type="text"
                maxLength={200}
                value={note}
                disabled={!canRecordPayment}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
          </div>
          {!canRecordPayment && (
            <p className="hint">
              Payments can only be recorded on sent or part-paid invoices with a balance.
            </p>
          )}
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={!canRecordPayment || busy}>
              Record payment
            </button>
          </div>
        </form>
      </Card>

      <Card title="Status">
        <div className="row-actions">
          {canMarkDraft && (
            <button type="button" className="btn" disabled={busy} onClick={() => handleStatus('draft')}>
              Mark as draft
            </button>
          )}
          {canMarkSent && (
            <button type="button" className="btn" disabled={busy} onClick={() => handleStatus('sent')}>
              Mark as sent
            </button>
          )}
          {canVoid && (
            <button type="button" className="btn btn-danger" disabled={busy} onClick={handleVoid}>
              Void invoice
            </button>
          )}
          {!canMarkDraft && !canMarkSent && !canVoid && <span>No status changes available.</span>}
        </div>
      </Card>

      <Card title="Reminders">
        <div className="form-actions">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={handleReminder}>
            Send WhatsApp reminder
          </button>
        </div>
        {reminders.length === 0 ? (
          <EmptyState text="No reminders sent yet." />
        ) : (
          <ul className="reminder-list">
            {reminders.map((r) => (
              <li key={r.id}>
                <span className="reminder-time">{r.sent_at ? new Date(r.sent_at).toLocaleString('en-IN') : '-'}</span>
                <span className="reminder-snippet">{String(r.message || '').slice(0, 120)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
