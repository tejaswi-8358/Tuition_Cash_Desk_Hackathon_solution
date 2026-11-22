import { useEffect, useState } from 'react';
import { getForecast, getCustomers, getScenarios, createScenario, deleteScenario, getSettings } from '../api.js';
import { Card, ErrorBox, Loading, EmptyState } from '../components/common.jsx';
import { formatMoney, formatDate } from '../format.js';
import {
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts';

const DAY_OPTIONS = [30, 60, 90];
const CATEGORIES = ['rent', 'salary', 'materials', 'transport', 'utilities', 'other'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const EMPTY_FORM = {
  name: '',
  lateCustomer: '',
  lateDays: '',
  expensePct: '',
  expenseCategory: '',
  lostCustomer: '',
};

// "2024-11-12" -> "12 Nov" (string-based so no timezone shift)
function shortDate(iso) {
  if (!iso) return '';
  const parts = String(iso).slice(0, 10).split('-');
  if (parts.length !== 3) return String(iso);
  const month = MONTHS[Number(parts[1]) - 1] || '';
  return `${Number(parts[2])} ${month}`.trim();
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function customerName(id, customers) {
  const match = customers.find((c) => Number(c.id) === Number(id));
  return match ? match.name : `Customer ${id}`;
}

// Build the overrides object from the form, keeping only the keys that have values.
function buildOverrides(form) {
  const overrides = {};
  if (form.lateCustomer !== '') {
    overrides.late_customer_id = Number(form.lateCustomer);
    if (form.lateDays !== '' && Number(form.lateDays) > 0) {
      overrides.late_days = Number(form.lateDays);
    }
  }
  if (form.expensePct !== '' && Number(form.expensePct) > 0) {
    overrides.expense_increase_pct = Number(form.expensePct);
    if (form.expenseCategory) {
      overrides.expense_increase_category = form.expenseCategory;
    }
  }
  if (form.lostCustomer !== '') {
    overrides.lost_customer_id = Number(form.lostCustomer);
  }
  return overrides;
}

// Human-readable summary of a scenario's overrides, e.g. "Customer 3 pays 15 days late; rent +10%".
function describeOverrides(overrides, customers) {
  const parts = [];
  if (overrides.late_customer_id != null) {
    const who = customerName(overrides.late_customer_id, customers);
    parts.push(
      overrides.late_days
        ? `${who} pays ${overrides.late_days} days late`
        : `${who} pays late`
    );
  }
  if (overrides.expense_increase_pct != null) {
    const category = overrides.expense_increase_category
      ? capitalize(overrides.expense_increase_category)
      : 'All expenses';
    parts.push(`${category} +${overrides.expense_increase_pct}%`);
  }
  if (overrides.lost_customer_id != null) {
    parts.push(`${customerName(overrides.lost_customer_id, customers)} is lost`);
  }
  return parts.length > 0 ? parts.join('; ') : 'No changes';
}

function signedMoney(minor) {
  const value = Number(minor || 0);
  return `${value >= 0 ? '+' : '-'}${formatMoney(Math.abs(value))}`;
}

// Money in minor units, or an em dash when the API did not supply the field.
function moneyOrDash(minor) {
  return minor === undefined || minor === null ? '—' : formatMoney(minor);
}

function FlowTable({ rows, emptyText }) {
  if (!rows || rows.length === 0) return <EmptyState text={emptyText} />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Label</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${row.date}-${i}`}>
              <td>{formatDate(row.date)}</td>
              <td>{row.label}</td>
              <td className="num">{formatMoney(row.amount_minor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Forecast() {
  const [days, setDays] = useState(90);
  const [scenarioId, setScenarioId] = useState(null);
  const [data, setData] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [form, setForm] = useState(EMPTY_FORM);
  const [formMessage, setFormMessage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [scenarioError, setScenarioError] = useState(null);

  // Load settings, customers and scenarios once on mount.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getSettings(), getCustomers(), getScenarios()])
      .then(([settingsData, customerList, scenarioList]) => {
        if (!cancelled) {
          setSettings(settingsData);
          setCustomers(customerList || []);
          setScenarios(scenarioList || []);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Reload the forecast whenever the horizon or active scenario changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getForecast(days, scenarioId)
      .then((result) => {
        if (!cancelled) setData(result);
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
  }, [days, scenarioId]);

  function loadScenarios() {
    return getScenarios().then((list) => setScenarios(list || []));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormMessage(null);
    setScenarioError(null);

    if (!form.name.trim()) {
      setFormMessage('Scenario name is required.');
      return;
    }
    const lateDays = Number(form.lateDays);
    if (form.lateDays !== '' && (lateDays < 0 || lateDays > 120)) {
      setFormMessage('Late days must be between 0 and 120.');
      return;
    }
    const pct = Number(form.expensePct);
    if (form.expensePct !== '' && (pct < 0 || pct > 200)) {
      setFormMessage('Expense increase must be between 0 and 200%.');
      return;
    }

    const overrides = buildOverrides(form);
    if (Object.keys(overrides).length === 0) {
      setFormMessage('Pick at least one change.');
      return;
    }

    setSaving(true);
    try {
      await createScenario({ name: form.name.trim(), overrides });
      await loadScenarios();
      setForm(EMPTY_FORM);
    } catch (err) {
      setScenarioError(err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(scenario) {
    if (!window.confirm(`Delete scenario "${scenario.name}"?`)) return;
    setScenarioError(null);
    try {
      await deleteScenario(scenario.id);
      if (scenarioId === scenario.id) setScenarioId(null);
      await loadScenarios();
    } catch (err) {
      setScenarioError(err);
    }
  }

  function updateForm(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const safeBalance = Number((settings && settings.safe_balance_minor) || 0);
  const scenarioActive = Boolean(data && data.scenario);
  const baseline = data ? data.baseline : null;
  const scenarioDaily = scenarioActive ? data.scenario.daily : null;

  const chartData = baseline
    ? baseline.daily.map((row, i) => ({
        label: shortDate(row.date),
        balance: Number(row.closing_minor) / 100,
        scenarioBalance:
          scenarioDaily && scenarioDaily[i] ? Number(scenarioDaily[i].closing_minor) / 100 : undefined,
      }))
    : [];

  return (
    <div className="page">
      <h1>Forecast</h1>

      <div className="toolbar">
        {DAY_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            className={days === option ? 'btn active' : 'btn'}
            onClick={() => setDays(option)}
          >
            {option} days
          </button>
        ))}
      </div>

      <ErrorBox error={error} />
      {loading && <Loading label="Loading forecast..." />}

      {baseline && (
        <>
          <div className="kpi-grid">
            <Card title="Opening cash">
              <div className="kpi-value">{formatMoney(baseline.opening_cash_minor)}</div>
            </Card>
            <Card title="Lowest balance">
              <div className="kpi-value">{formatMoney(baseline.min_balance_minor)}</div>
              <div className="kpi-sub">{formatDate(baseline.min_balance_date)}</div>
            </Card>
            <Card title="First shortfall">
              <div className="kpi-value">
                {baseline.first_negative_date ? formatDate(baseline.first_negative_date) : 'No shortfall'}
              </div>
            </Card>
            <Card title="Total inflow">
              <div className="kpi-value">{formatMoney(baseline.total_inflow_minor)}</div>
            </Card>
            <Card title="Total outflow">
              <div className="kpi-value">{formatMoney(baseline.total_outflow_minor)}</div>
            </Card>
          </div>

          <Card title="Projected balance">
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" minTickGap={20} />
                  <YAxis tickFormatter={(value) => value.toLocaleString('en-IN')} />
                  <Tooltip formatter={(value) => Number(value).toLocaleString('en-IN')} />
                  <Legend />
                  <ReferenceLine y={0} stroke="red" />
                  <ReferenceLine y={safeBalance / 100} stroke="#f59e0b" label="Safe balance" />
                  <Area type="monotone" dataKey="balance" name="Baseline" stroke="#2563eb" fill="#bfdbfe" />
                  {scenarioActive && (
                    <Line
                      type="monotone"
                      dataKey="scenarioBalance"
                      name="Scenario"
                      stroke="#9333ea"
                      dot={false}
                    />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="kpi-grid">
            <Card title="Expected income">
              <div className="kpi-value">{moneyOrDash(baseline.expected_income_minor)}</div>
            </Card>
            <Card title="Expected expenses">
              <div className="kpi-value">{moneyOrDash(baseline.expected_expenses_minor)}</div>
            </Card>
            <Card title="Lowest projected balance">
              <div className="kpi-value">{moneyOrDash(baseline.min_balance_minor)}</div>
              <div className="kpi-sub">
                {baseline.min_balance_date ? formatDate(baseline.min_balance_date) : '—'}
              </div>
            </Card>
            <Card title="Balance turns negative">
              <div className="kpi-value">
                {baseline.first_negative_date ? formatDate(baseline.first_negative_date) : 'None in window'}
              </div>
            </Card>
            <Card title="Balance below safe level">
              <div className="kpi-value">
                {baseline.first_below_safe_date ? formatDate(baseline.first_below_safe_date) : 'None in window'}
              </div>
            </Card>
          </div>

          <Card title="Assumptions">
            {Array.isArray(baseline.assumptions) && baseline.assumptions.length > 0 ? (
              <ul>
                {baseline.assumptions.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            ) : (
              <EmptyState text="No assumptions listed." />
            )}
          </Card>
        </>
      )}

      <div className="two-col">
        <Card title="What-if scenarios">
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <label>
                Name
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateForm('name', e.target.value)}
                  required
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                Late customer
                <select value={form.lateCustomer} onChange={(e) => updateForm('lateCustomer', e.target.value)}>
                  <option value="">None</option>
                  {customers.map((c) => (
                    <option key={c.id} value={String(c.id)}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Late days
                <input
                  type="number"
                  min="0"
                  max="120"
                  value={form.lateDays}
                  onChange={(e) => updateForm('lateDays', e.target.value)}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                Expense increase %
                <input
                  type="number"
                  min="0"
                  max="200"
                  value={form.expensePct}
                  onChange={(e) => updateForm('expensePct', e.target.value)}
                />
              </label>
              <label>
                Expense category
                <select
                  value={form.expenseCategory}
                  onChange={(e) => updateForm('expenseCategory', e.target.value)}
                >
                  <option value="">All categories</option>
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {capitalize(cat)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="form-row">
              <label>
                Lost customer
                <select value={form.lostCustomer} onChange={(e) => updateForm('lostCustomer', e.target.value)}>
                  <option value="">None</option>
                  {customers.map((c) => (
                    <option key={c.id} value={String(c.id)}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {formMessage && <div className="form-message">{formMessage}</div>}
            <button type="submit" className="btn" disabled={saving}>
              {saving ? 'Saving...' : 'Save scenario'}
            </button>
          </form>

          <ErrorBox error={scenarioError} />

          <h3>Saved scenarios</h3>
          {scenarios.length === 0 ? (
            <EmptyState text="No saved scenarios yet." />
          ) : (
            <ul className="scenario-list">
              {scenarios.map((s) => (
                <li key={s.id}>
                  <div>
                    <strong>{s.name}</strong>
                    {scenarioId === s.id && <span> (active)</span>}
                  </div>
                  <div className="kpi-sub">{describeOverrides(s.overrides || {}, customers)}</div>
                  <div className="btn-row">
                    <button type="button" className="btn" onClick={() => setScenarioId(s.id)}>
                      Run
                    </button>
                    <button type="button" className="btn danger" onClick={() => handleDelete(s)}>
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {data && scenarioId !== null && (
          <Card title="Scenario comparison">
            {data.comparison ? (
              <table className="table">
                <tbody>
                  <tr>
                    <th>Lowest balance (baseline)</th>
                    <td className="num">{formatMoney(data.comparison.baseline_min_minor)}</td>
                  </tr>
                  <tr>
                    <th>Lowest balance (scenario)</th>
                    <td className="num">{formatMoney(data.comparison.scenario_min_minor)}</td>
                  </tr>
                  <tr>
                    <th>Change in lowest balance</th>
                    <td className="num">{signedMoney(data.comparison.delta_min_minor)}</td>
                  </tr>
                  <tr>
                    <th>First shortfall (baseline)</th>
                    <td>
                      {data.comparison.baseline_first_negative
                        ? formatDate(data.comparison.baseline_first_negative)
                        : 'None'}
                    </td>
                  </tr>
                  <tr>
                    <th>First shortfall (scenario)</th>
                    <td>
                      {data.comparison.scenario_first_negative
                        ? formatDate(data.comparison.scenario_first_negative)
                        : 'None'}
                    </td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <EmptyState text="No comparison available." />
            )}
            <div className="btn-row">
              <button type="button" className="btn" onClick={() => setScenarioId(null)}>
                Clear scenario
              </button>
            </div>
          </Card>
        )}
      </div>

      {baseline && (
        <div className="two-col">
          <Card title="Upcoming receipts">
            <FlowTable rows={baseline.receipts.slice(0, 40)} emptyText="No upcoming receipts." />
          </Card>
          <Card title="Upcoming payments">
            <FlowTable rows={baseline.payments.slice(0, 40)} emptyText="No upcoming payments." />
          </Card>
        </div>
      )}
    </div>
  );
}
