const BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

async function request(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  const res = await fetch(BASE + path, options);
  if (res.status === 204) return null;

  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    const detail = data && typeof data === 'object' ? data.detail : null;
    if (Array.isArray(detail)) {
      message = detail.map((item) => item.msg).join('; ');
    } else if (typeof detail === 'string' && detail) {
      message = detail;
    }
    throw new Error(message);
  }

  return data;
}

function query(params) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      qs.set(key, String(value));
    }
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

// Health and settings
export const getHealth = () => request('GET', '/api/health');
export const getDashboard = () => request('GET', '/api/dashboard');
export const getSettings = () => request('GET', '/api/settings');
export const updateSettings = (patch) => request('PATCH', '/api/settings', patch);

// Customers
export const getCustomers = () => request('GET', '/api/customers');
export const createCustomer = (data) => request('POST', '/api/customers', data);
export const updateCustomer = (id, patch) => request('PATCH', `/api/customers/${id}`, patch);
export const getCustomer = (id) => request('GET', `/api/customers/${id}`);

// Invoices
export const getInvoices = (params = {}) =>
  request('GET', '/api/invoices' + query({ status: params.status, customer_id: params.customer_id }));
export const createInvoice = (data) => request('POST', '/api/invoices', data);
export const getInvoice = (id) => request('GET', `/api/invoices/${id}`);
export const updateInvoiceStatus = (id, status) =>
  request('PATCH', `/api/invoices/${id}/status`, { status });
export const recordPayment = (invoiceId, data) =>
  request('POST', `/api/invoices/${invoiceId}/payments`, data);
export const deletePayment = (invoiceId, paymentId) =>
  request('DELETE', `/api/invoices/${invoiceId}/payments/${paymentId}`);
export const sendReminder = (invoiceId, message = '') =>
  request('POST', `/api/invoices/${invoiceId}/reminders`, { message });

// Bills
export const getBills = () => request('GET', '/api/bills');
export const createBill = (data) => request('POST', '/api/bills', data);
export const updateBill = (id, patch) => request('PATCH', `/api/bills/${id}`, patch);
export const deleteBill = (id) => request('DELETE', `/api/bills/${id}`);

// Recurring fees
export const getRecurringFees = () => request('GET', '/api/recurring-fees');
export const createRecurringFee = (data) => request('POST', '/api/recurring-fees', data);
export const deleteRecurringFee = (id) => request('DELETE', `/api/recurring-fees/${id}`);

// Forecast and scenarios
export const getForecast = (days = 90, scenarioId = null) =>
  request('GET', '/api/forecast' + query({ days, scenario_id: scenarioId }));
export const getScenarios = () => request('GET', '/api/scenarios');
export const createScenario = (data) => request('POST', '/api/scenarios', data);
export const deleteScenario = (id) => request('DELETE', `/api/scenarios/${id}`);

// Alerts, chase list, insights
export const getAlerts = () => request('GET', '/api/alerts');
export const getChaseList = () => request('GET', '/api/chase-list');
export const getInsights = () => request('GET', '/api/insights');
