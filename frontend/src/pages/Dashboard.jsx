import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDashboard } from '../api.js';
import { Card, ErrorBox, Loading, EmptyState } from '../components/common.jsx';
import { formatMoney, formatDate, daysLabel } from '../format.js';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

const BUCKETS = ['current', '1-30', '31-60', '61-90', '90+'];

export default function Dashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard()
      .then((data) => {
        if (!cancelled) setDashboard(data);
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

  if (loading) return <Loading label="Loading dashboard..." />;

  const chartData = BUCKETS.map((key) => ({
    bucket: key,
    amount: Number((dashboard && dashboard.aging && dashboard.aging[key] && dashboard.aging[key].amount_minor) || 0) / 100,
  }));

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <ErrorBox error={error} />

      {dashboard && (
        <>
          <div className="kpi-grid">
            <Card title="Outstanding">
              <div className="kpi-value">{formatMoney(dashboard.total_outstanding_minor)}</div>
            </Card>
            <Card title="Overdue">
              <div className="kpi-value">{formatMoney(dashboard.total_overdue_minor)}</div>
              <div className="kpi-sub">{dashboard.overdue_count} invoice(s)</div>
            </Card>
            <Card title="Received this month">
              <div className="kpi-value">
                {formatMoney(dashboard.payments ? dashboard.payments.received_this_month_minor : 0)}
              </div>
            </Card>
            <Card title="Customers">
              <div className="kpi-value">{dashboard.customer_count}</div>
            </Card>
          </div>

          <Card title="Aging buckets">
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" />
                  <YAxis />
                  <Tooltip formatter={(value) => formatMoney(Math.round(Number(value) * 100))} />
                  <Bar dataKey="amount" name="Amount" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Overdue invoices">
            {dashboard.overdue.length === 0 ? (
              <EmptyState text="No overdue invoices." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Customer</th>
                      <th>Invoice</th>
                      <th className="num">Balance</th>
                      <th>Due date</th>
                      <th>Overdue</th>
                      <th>Bucket</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.overdue.map((row) => (
                      <tr key={row.invoice_id}>
                        <td>{row.customer_name}</td>
                        <td>{row.invoice_number}</td>
                        <td className="num">{formatMoney(row.balance_minor)}</td>
                        <td>{formatDate(row.due_date)}</td>
                        <td>{daysLabel(row.days_overdue)}</td>
                        <td>{row.bucket}</td>
                        <td>
                          <Link to={`/invoices/${row.invoice_id}`}>Open invoice</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
