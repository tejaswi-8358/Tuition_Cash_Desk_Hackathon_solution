import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getDashboard,
  getForecast,
  getAlerts,
  getChaseList,
  getInsights,
  sendReminder,
} from '../api.js';
import { Card, ErrorBox, Loading, EmptyState } from '../components/common.jsx';
import { formatMoney, formatDate, daysLabel } from '../format.js';

function alertPath(alert) {
  switch (alert.action_type) {
    case 'chase_invoice':
      return alert.action_target ? `/invoices/${alert.action_target}` : null;
    case 'review_forecast':
    case 'collect':
      return '/forecast';
    case 'open_bill':
      return '/bills';
    default:
      return null;
  }
}

function insightText(item) {
  if (typeof item === 'string') return item;
  if (item && typeof item === 'object') {
    return item.text || item.title || item.message || JSON.stringify(item);
  }
  return String(item);
}

export default function Today() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [chase, setChase] = useState([]);
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [actionError, setActionError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getDashboard(), getForecast(90), getAlerts(), getChaseList(), getInsights()])
      .then(([dash, fc, al, chaseRows, ins]) => {
        if (cancelled) return;
        setDashboard(dash);
        setForecast(fc);
        setAlerts(al || []);
        setChase(chaseRows || []);
        setInsights(ins);
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

  async function handleWhatsApp(row) {
    setActionError(null);
    setBusyId(row.invoice_id);
    try {
      const res = await sendReminder(row.invoice_id);
      if (!res || !res.whatsapp_url) {
        throw new Error('No WhatsApp link was returned for this invoice');
      }
      window.open(res.whatsapp_url, '_blank');
    } catch (err) {
      setActionError(err);
    } finally {
      setBusyId(null);
    }
  }

  async function handleCopy(row) {
    setActionError(null);
    try {
      await navigator.clipboard.writeText(row.message);
      setCopiedId(row.invoice_id);
      setTimeout(() => {
        setCopiedId((current) => (current === row.invoice_id ? null : current));
      }, 1500);
    } catch (err) {
      setActionError(err);
    }
  }

  if (loading) return <Loading label="Loading today..." />;

  const cashText = forecast && forecast.first_negative_date
    ? `Cash goes negative on ${formatDate(forecast.first_negative_date)}`
    : 'No shortfall in 90 days';

  const insightLabel = insights && insights.source === 'llm' ? 'AI-assisted' : 'Rule-based insights';
  const insightList = (insights && insights.insights) || [];

  return (
    <div className="page">
      <h1>Today</h1>
      <ErrorBox error={error} />
      <ErrorBox error={actionError} />

      {dashboard && (
        <div className="summary-strip">
          <div className="summary-item">
            <span className="summary-label">Total overdue</span>
            <span className="summary-value">{formatMoney(dashboard.total_overdue_minor)}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Overdue invoices</span>
            <span className="summary-value">{dashboard.overdue_count}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Cash status</span>
            <span className="summary-value">{cashText}</span>
          </div>
        </div>
      )}

      <Card title="Alerts">
        {alerts.length === 0 ? (
          <EmptyState text="No alerts right now." />
        ) : (
          <ul className="alert-list">
            {alerts.map((alert) => {
              const path = alertPath(alert);
              return (
                <li key={alert.id} className={`alert alert-${alert.severity}`}>
                  <div className="alert-text">
                    <strong>{alert.title}</strong>
                    <div>{alert.detail}</div>
                  </div>
                  {path && (
                    <button type="button" className="btn" onClick={() => navigate(path)}>
                      {alert.action_label}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card title="Chase list">
        {chase.length === 0 ? (
          <EmptyState text="Nothing to chase." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Customer</th>
                  <th>Invoice</th>
                  <th className="num">Balance</th>
                  <th>Overdue</th>
                  <th>Tone</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {chase.map((row) => (
                  <tr key={row.invoice_id}>
                    <td>{row.priority_rank}</td>
                    <td>{row.customer_name}</td>
                    <td>{row.invoice_number}</td>
                    <td className="num">{formatMoney(row.balance_minor)}</td>
                    <td>{daysLabel(row.days_overdue)}</td>
                    <td>
                      <span className={`tone tone-${row.tone}`}>{row.tone}</span>
                    </td>
                    <td className="row-actions">
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={busyId === row.invoice_id}
                        onClick={() => handleWhatsApp(row)}
                      >
                        Send WhatsApp reminder
                      </button>
                      <button type="button" className="btn" onClick={() => handleCopy(row)}>
                        {copiedId === row.invoice_id ? 'Copied' : 'Copy message'}
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => navigate(`/invoices/${row.invoice_id}`)}
                      >
                        Open invoice
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={insightLabel}>
        {insightList.length === 0 ? (
          <EmptyState text="No insights yet." />
        ) : (
          <ul className="insight-list">
            {insightList.map((item, index) => (
              <li key={index}>{insightText(item)}</li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
