import { useEffect } from 'react';

export function Card({ title, actions, children }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-header">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

const STATUS_LABELS = {
  paid: { label: 'Paid', className: 'badge-paid' },
  part_paid: { label: 'Part paid', className: 'badge-part-paid' },
  sent: { label: 'Sent', className: 'badge-sent' },
  draft: { label: 'Draft', className: 'badge-draft' },
  void: { label: 'Void', className: 'badge-void' },
  overdue: { label: 'Overdue', className: 'badge-overdue' },
};

export function StatusBadge({ status }) {
  const entry = STATUS_LABELS[status] || { label: status || '-', className: 'badge-draft' };
  const style = status === 'void' ? { textDecoration: 'line-through' } : undefined;
  return (
    <span className={`badge ${entry.className}`} style={style}>
      {entry.label}
    </span>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  const message = error.message || String(error);
  return (
    <div className="error-box" role="alert">
      {message}
    </div>
  );
}

export function Loading({ label }) {
  return <div className="loading">{label || 'Loading...'}</div>;
}

export function EmptyState({ text }) {
  return <div className="empty-state">{text}</div>;
}

export function Modal({ open, title, onClose, children }) {
  useEffect(() => {
    if (!open) return undefined;
    function handleKey(event) {
      if (event.key === 'Escape' && onClose) onClose();
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={() => onClose && onClose()}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
