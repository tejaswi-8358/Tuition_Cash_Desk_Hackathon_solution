import { useEffect, useState } from "react";
import {
  getBills,
  createBill,
  updateBill,
  deleteBill,
  getRecurringFees,
  createRecurringFee,
  deleteRecurringFee,
  getCustomers,
} from "../api.js";
import { formatMoney, formatDate } from "../format.js";
import { Card, ErrorBox, Loading, EmptyState } from "../components/common.jsx";

const BILL_CATEGORIES = ["rent", "salary", "materials", "transport", "utilities", "other"];
const BILL_RECURRENCES = ["monthly", "weekly", "one_off"];
const FEE_CADENCES = ["monthly", "weekly"];

const EMPTY_BILL = {
  payee: "",
  category: "rent",
  amount: "",
  recurrence: "monthly",
  dueDay: "",
  nextDueDate: "",
};

const EMPTY_FEE = {
  customerId: "",
  amount: "",
  cadence: "monthly",
  dueDay: "",
  nextDueDate: "",
};

function labelize(text) {
  const spaced = String(text || "").replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

// Converts a rupee string into integer paise; returns null when invalid or not > 0.
function parseAmountMinor(value) {
  if (String(value).trim() === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 100);
}

// Returns an integer day 1-31, or null when invalid.
function parseDueDay(value) {
  if (String(value).trim() === "") return null;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 && n <= 31 ? n : null;
}

// Monthly items show the day of month; otherwise show the next due date.
function dueText(recurrence, dueDay, nextDueDate) {
  if (recurrence === "monthly") return `Day ${dueDay} of each month`;
  return nextDueDate ? formatDate(nextDueDate) : "-";
}

export default function Bills() {
  const [bills, setBills] = useState([]);
  const [fees, setFees] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [billForm, setBillForm] = useState(EMPTY_BILL);
  const [billFormError, setBillFormError] = useState(null);
  const [savingBill, setSavingBill] = useState(false);

  const [feeForm, setFeeForm] = useState(EMPTY_FEE);
  const [feeFormError, setFeeFormError] = useState(null);
  const [savingFee, setSavingFee] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getBills(), getRecurringFees(), getCustomers()])
      .then(([billData, feeData, customerData]) => {
        if (cancelled) return;
        setBills(billData || []);
        setFees(feeData || []);
        setCustomers(customerData || []);
        setError(null);
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
  }, [reloadKey]);

  function reload() {
    setReloadKey((key) => key + 1);
  }

  async function handleToggleBill(bill) {
    try {
      await updateBill(bill.id, { active: !bill.active });
      reload();
    } catch (err) {
      setError(err);
    }
  }

  async function handleDeleteBill(bill) {
    if (!window.confirm(`Delete bill "${bill.payee}"?`)) return;
    try {
      await deleteBill(bill.id);
      reload();
    } catch (err) {
      setError(err);
    }
  }

  async function handleCreateBill(event) {
    event.preventDefault();
    const payee = billForm.payee.trim();
    if (!payee) {
      setBillFormError("Payee is required.");
      return;
    }
    if (payee.length > 120) {
      setBillFormError("Payee must be 120 characters or fewer.");
      return;
    }
    const amountMinor = parseAmountMinor(billForm.amount);
    if (amountMinor === null) {
      setBillFormError("Amount must be greater than 0.");
      return;
    }

    const body = {
      payee,
      category: billForm.category,
      amount_minor: amountMinor,
      recurrence: billForm.recurrence,
    };
    if (billForm.recurrence === "monthly") {
      const dueDay = parseDueDay(billForm.dueDay);
      if (dueDay === null) {
        setBillFormError("Due day must be a whole number from 1 to 31.");
        return;
      }
      body.due_day = dueDay;
    } else {
      if (!billForm.nextDueDate) {
        setBillFormError("Next due date is required.");
        return;
      }
      body.next_due_date = billForm.nextDueDate;
    }

    setBillFormError(null);
    setSavingBill(true);
    try {
      await createBill(body);
      setBillForm(EMPTY_BILL);
      reload();
    } catch (err) {
      setBillFormError(err);
    } finally {
      setSavingBill(false);
    }
  }

  async function handleDeleteFee(fee) {
    if (!window.confirm(`Delete recurring fee for ${fee.customer_name}?`)) return;
    try {
      await deleteRecurringFee(fee.id);
      reload();
    } catch (err) {
      setError(err);
    }
  }

  async function handleCreateFee(event) {
    event.preventDefault();
    if (!feeForm.customerId) {
      setFeeFormError("Customer is required.");
      return;
    }
    const amountMinor = parseAmountMinor(feeForm.amount);
    if (amountMinor === null) {
      setFeeFormError("Amount must be greater than 0.");
      return;
    }

    const body = {
      customer_id: Number(feeForm.customerId),
      amount_minor: amountMinor,
      cadence: feeForm.cadence,
    };
    if (feeForm.cadence === "monthly") {
      const dueDay = parseDueDay(feeForm.dueDay);
      if (dueDay === null) {
        setFeeFormError("Due day must be a whole number from 1 to 31.");
        return;
      }
      body.due_day = dueDay;
    } else {
      if (!feeForm.nextDueDate) {
        setFeeFormError("Next due date is required.");
        return;
      }
      body.next_due_date = feeForm.nextDueDate;
    }

    setFeeFormError(null);
    setSavingFee(true);
    try {
      await createRecurringFee(body);
      setFeeForm(EMPTY_FEE);
      reload();
    } catch (err) {
      setFeeFormError(err);
    } finally {
      setSavingFee(false);
    }
  }

  function updateBillField(field, value) {
    setBillForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateFeeField(field, value) {
    setFeeForm((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <div className="bills-page">
      <h1>Bills</h1>
      <ErrorBox error={error} />
      {loading && <Loading label="Loading bills, recurring fees and customers..." />}

      <div className="two-col">
        <Card title="Bills">
          {!loading && bills.length === 0 && <EmptyState text="No bills yet." />}
          {bills.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Payee</th>
                  <th>Category</th>
                  <th>Amount</th>
                  <th>Recurrence</th>
                  <th>Due</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bills.map((bill) => (
                  <tr key={bill.id}>
                    <td>{bill.payee}</td>
                    <td>{labelize(bill.category)}</td>
                    <td>{formatMoney(bill.amount_minor)}</td>
                    <td>{labelize(bill.recurrence)}</td>
                    <td>{dueText(bill.recurrence, bill.due_day, bill.next_due_date)}</td>
                    <td>
                      <span className={`badge ${bill.active ? "badge-green" : "badge-grey"}`}>
                        {bill.active ? "Active" : "Paused"}
                      </span>
                    </td>
                    <td>
                      <div className="actions-row">
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          onClick={() => handleToggleBill(bill)}
                        >
                          {bill.active ? "Pause" : "Activate"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-small"
                          onClick={() => handleDeleteBill(bill)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Add bill">
          <form className="form-grid" onSubmit={handleCreateBill}>
            <ErrorBox error={billFormError} />
            <label className="full">
              Payee
              <input
                type="text"
                maxLength={120}
                value={billForm.payee}
                onChange={(e) => updateBillField("payee", e.target.value)}
                required
              />
            </label>
            <label>
              Category
              <select
                value={billForm.category}
                onChange={(e) => updateBillField("category", e.target.value)}
              >
                {BILL_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {labelize(c)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount (₹)
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={billForm.amount}
                onChange={(e) => updateBillField("amount", e.target.value)}
                required
              />
            </label>
            <label>
              Recurrence
              <select
                value={billForm.recurrence}
                onChange={(e) => updateBillField("recurrence", e.target.value)}
              >
                {BILL_RECURRENCES.map((r) => (
                  <option key={r} value={r}>
                    {labelize(r)}
                  </option>
                ))}
              </select>
            </label>
            {billForm.recurrence === "monthly" ? (
              <label>
                Due day (1-31)
                <input
                  type="number"
                  min="1"
                  max="31"
                  step="1"
                  value={billForm.dueDay}
                  onChange={(e) => updateBillField("dueDay", e.target.value)}
                  required
                />
              </label>
            ) : (
              <label>
                Next due date
                <input
                  type="date"
                  value={billForm.nextDueDate}
                  onChange={(e) => updateBillField("nextDueDate", e.target.value)}
                  required
                />
              </label>
            )}
            <div className="full actions-row">
              <button type="submit" className="btn btn-primary" disabled={savingBill}>
                {savingBill ? "Saving..." : "Add bill"}
              </button>
            </div>
          </form>
        </Card>
      </div>

      <div className="two-col">
        <Card title="Recurring fees">
          {!loading && fees.length === 0 && <EmptyState text="No recurring fees yet." />}
          {fees.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Amount</th>
                  <th>Cadence</th>
                  <th>Due</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {fees.map((fee) => (
                  <tr key={fee.id}>
                    <td>{fee.customer_name}</td>
                    <td>{formatMoney(fee.amount_minor)}</td>
                    <td>{labelize(fee.cadence)}</td>
                    <td>{dueText(fee.cadence, fee.due_day, fee.next_due_date)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-danger btn-small"
                        onClick={() => handleDeleteFee(fee)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Add recurring fee">
          <form className="form-grid" onSubmit={handleCreateFee}>
            <ErrorBox error={feeFormError} />
            <label className="full">
              Customer
              <select
                value={feeForm.customerId}
                onChange={(e) => updateFeeField("customerId", e.target.value)}
                required
              >
                <option value="">Select a customer...</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount (₹)
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={feeForm.amount}
                onChange={(e) => updateFeeField("amount", e.target.value)}
                required
              />
            </label>
            <label>
              Cadence
              <select
                value={feeForm.cadence}
                onChange={(e) => updateFeeField("cadence", e.target.value)}
              >
                {FEE_CADENCES.map((c) => (
                  <option key={c} value={c}>
                    {labelize(c)}
                  </option>
                ))}
              </select>
            </label>
            {feeForm.cadence === "monthly" ? (
              <label>
                Due day (1-31)
                <input
                  type="number"
                  min="1"
                  max="31"
                  step="1"
                  value={feeForm.dueDay}
                  onChange={(e) => updateFeeField("dueDay", e.target.value)}
                  required
                />
              </label>
            ) : (
              <label>
                Next due date
                <input
                  type="date"
                  value={feeForm.nextDueDate}
                  onChange={(e) => updateFeeField("nextDueDate", e.target.value)}
                  required
                />
              </label>
            )}
            <div className="full actions-row">
              <button type="submit" className="btn btn-primary" disabled={savingFee}>
                {savingFee ? "Saving..." : "Add recurring fee"}
              </button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
