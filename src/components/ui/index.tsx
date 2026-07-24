import {
  createContext,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type CSSProperties,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import './ui.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="ui-spinner" style={{ '--spinner-size': `${size}px` } as CSSProperties} aria-hidden="true" />;
}

export function Button({
  variant = 'secondary',
  loading = false,
  children,
  disabled,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  return (
    <button
      {...props}
      className={`ui-button ui-button--${variant} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <Spinner />}
      <span>{children}</span>
    </button>
  );
}

export function Input({ label, hint, error, id, className = '', ...props }: InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
}) {
  const helpId = id ? `${id}-help` : undefined;
  return (
    <label className={`ui-field ${className}`.trim()} htmlFor={id}>
      {label && <span className="ui-field__label">{label}</span>}
      <input {...props} id={id} className="ui-input" aria-invalid={Boolean(error)} aria-describedby={helpId} />
      {(error || hint) && <small id={helpId} className={error ? 'ui-field__error' : 'ui-field__hint'}>{error || hint}</small>}
    </label>
  );
}

export function Select({ label, hint, id, children, className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  hint?: string;
}) {
  return (
    <label className={`ui-field ${className}`.trim()} htmlFor={id}>
      {label && <span className="ui-field__label">{label}</span>}
      <select {...props} id={id} className="ui-select">{children}</select>
      {hint && <small className="ui-field__hint">{hint}</small>}
    </label>
  );
}

export type SegmentOption<T extends string> = { value: T; label: string; disabled?: boolean };

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  label?: string;
}) {
  return (
    <div className="ui-field">
      {label && <span className="ui-field__label">{label}</span>}
      <div className="ui-segmented" role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            type="button"
            role="radio"
            aria-checked={value === option.value}
            className={value === option.value ? 'active' : ''}
            disabled={option.disabled}
            key={option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Slider({
  label,
  value,
  valueLabel,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  valueLabel?: string;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="ui-field ui-slider">
      <span className="ui-slider__head"><span className="ui-field__label">{label}</span><output>{valueLabel ?? value}</output></span>
      <input type="range" value={value} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

export function Card({
  icon,
  title,
  description,
  actions,
  children,
  className = '',
}: {
  icon?: ReactNode;
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ui-card ${className}`.trim()}>
      {(title || description || icon || actions) && (
        <header className="ui-card__header">
          {icon && <span className="ui-card__icon">{icon}</span>}
          <div className="ui-card__heading">
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="ui-card__actions">{actions}</div>}
        </header>
      )}
      <div className="ui-card__body">{children}</div>
    </section>
  );
}

export type Status = 'pending' | 'running' | 'done' | 'error';
const statusLabels: Record<Status, string> = { pending: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn thành', error: 'Lỗi' };

export function Badge({ status, children }: { status: Status; children?: ReactNode }) {
  return <span className={`ui-badge ui-badge--${status}`}><i aria-hidden="true" />{children || statusLabels[status]}</span>;
}

export function ProgressBar({ value, max = 100, label, showValue = true }: {
  value: number;
  max?: number;
  label?: string;
  showValue?: boolean;
}) {
  const safeValue = Math.max(0, Math.min(value, max));
  const percent = max > 0 ? Math.round((safeValue / max) * 100) : 0;
  return (
    <div className="ui-progress">
      {(label || showValue) && <div className="ui-progress__head"><span>{label}</span>{showValue && <strong>{percent}%</strong>}</div>}
      <div className="ui-progress__track" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={safeValue}>
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

type ToastKind = 'success' | 'error' | 'info';
type ToastItem = { id: number; kind: ToastKind; title: string; message?: string };
type ToastContextValue = { showToast: (toast: Omit<ToastItem, 'id'>, duration?: number) => void };
const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const showToast = useCallback((toast: Omit<ToastItem, 'id'>, duration = 3500) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { ...toast, id }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), duration);
  }, []);
  const value = useMemo(() => ({ showToast }), [showToast]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-region" aria-live="polite" aria-label="Thông báo">
        {toasts.map((toast) => (
          <article key={toast.id} className={`ui-toast ui-toast--${toast.kind}`}>
            <i aria-hidden="true" />
            <div><strong>{toast.title}</strong>{toast.message && <p>{toast.message}</p>}</div>
            <button type="button" aria-label="Đóng" onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}>×</button>
          </article>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside ToastProvider');
  return context;
}
