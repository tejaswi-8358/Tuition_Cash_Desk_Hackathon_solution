const inrFormatter = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export function formatMoney(minor) {
  const value = minor === null || minor === undefined ? 0 : Number(minor);
  return inrFormatter.format(value / 100);
}

export function formatDate(iso) {
  if (!iso) return '-';
  const date = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function daysLabel(n) {
  const days = Number(n) || 0;
  if (days <= 0) return 'Not yet overdue';
  return `${days} day(s) overdue`;
}
