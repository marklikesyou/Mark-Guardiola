import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { it } from "../lib/strings";
import { clamp01, fmtElapsed, fmtPct } from "../lib/format";
import {
  IconChevron,
  MarkAsk,
  MarkCheck,
  MarkCross,
  MarkDot,
  MarkHalf,
  MarkRing,
  MarkWarn,
} from "./icons";

function playerInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "";
  return `${first}${last}`.toLocaleUpperCase("it-IT");
}

export function PlayerPortrait({
  name,
  photoUrl,
  size = "small",
  decorative = true,
  eager = false,
}: {
  name: string;
  photoUrl?: string | null;
  size?: "small" | "medium" | "large";
  decorative?: boolean;
  eager?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const showPhoto = Boolean(photoUrl) && failedUrl !== photoUrl;
  return (
    <span
      className={`portrait portrait--${size}${showPhoto ? " portrait--photo" : ""}`}
      {...(decorative
        ? { "aria-hidden": true }
        : {
            role: "img",
            "aria-label": showPhoto
              ? `Foto di ${name}`
              : `Iniziali di ${name}`,
          })}
    >
      {showPhoto ? (
        <img
          src={photoUrl ?? undefined}
          alt=""
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(photoUrl ?? null)}
        />
      ) : (
        <span>{playerInitials(name)}</span>
      )}
    </span>
  );
}



export function Board({
  title,
  meta,
  busy = false,
  flush = false,
  lead = false,
  foot,
  children,
  id,
}: {
  title: string;
  meta?: ReactNode;
  busy?: boolean;
  flush?: boolean;

  lead?: boolean;
  foot?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  const headingId = useId();
  return (
    <section
      className={`board${lead ? " board--lead" : ""}`}
      aria-busy={busy || undefined}
      aria-labelledby={headingId}
      {...(id ? { id } : {})}
    >
      <div className={`board__head${busy ? " board__head--busy" : ""}`}>
        <h2 className="board__title" id={headingId}>
          {title}
        </h2>
        {meta !== undefined && meta !== null ? (
          <div className="board__meta">{meta}</div>
        ) : null}
      </div>
      <div className={`board__body${flush ? " board__body--flush" : ""}`}>
        {children}
      </div>
      {foot ? <div className="board__foot">{foot}</div> : null}
    </section>
  );
}



export function Meter({
  value,
  label,
  ink = false,
}: {
  value: number;
  label: string;
  ink?: boolean;
}) {
  const level = Math.round(clamp01(value) * 10);
  return (
    <span className="meterline">
      <span
        className={`meter${ink ? " meter--ink" : ""}`}
        role="img"
        aria-label={`${label}: ${fmtPct(value)}`}
      >
        {Array.from({ length: 10 }, (_, index) => (
          <i key={index} className={index < level ? "on" : ""} />
        ))}
      </span>
      <span aria-hidden="true" className="num">
        {fmtPct(value)}
      </span>
    </span>
  );
}



export type MarkKind =
  | "ok"
  | "on"
  | "off"
  | "half"
  | "out"
  | "warn"
  | "ask"
  | "done";

const MARK_ICONS: Record<MarkKind, typeof MarkDot> = {
  ok: MarkCheck,
  done: MarkCheck,
  on: MarkDot,
  off: MarkRing,
  half: MarkHalf,
  out: MarkCross,
  warn: MarkWarn,
  ask: MarkAsk,
};

const MARK_TONES: Record<MarkKind, string> = {
  ok: "mark--ok",
  done: "mark--ok",
  on: "mark--accent",
  off: "mark--quiet",
  half: "mark--warn",
  out: "mark--bad",
  warn: "mark--warn",
  ask: "mark--warn",
};

export function Mark({ kind, label }: { kind: MarkKind; label?: string }) {
  const Icon = MARK_ICONS[kind];
  return (
    <span
      className={`mark ${MARK_TONES[kind]}`}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      <Icon />
    </span>
  );
}



export function Notice({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "warn" | "bad" | "ok";
  children: ReactNode;
}) {
  const toneClass =
    tone === "neutral" ? "" : ` notice--${tone}`;
  const kind: MarkKind =
    tone === "bad" ? "out" : tone === "ok" ? "ok" : tone === "warn" ? "warn" : "warn";
  return (
    <p className={`notice${toneClass}`}>
      <Mark kind={tone === "neutral" ? "ask" : kind} />
      <span>{children}</span>
    </p>
  );
}



export function EmptyState({
  title,
  body,
  children,
}: {
  title: string;
  body?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <h3 className="empty__title">{title}</h3>
      {body ? <p className="empty__body">{body}</p> : null}
      {children ? <div className="empty__actions">{children}</div> : null}
    </div>
  );
}



export function Skeleton({ lines = 4, label }: { lines?: number; label?: string }) {
  const widths = [92, 78, 85, 64, 88, 72, 81, 58];
  return (
    <div className="skeleton" role="status" aria-label={label ?? it.app.loading}>
      {Array.from({ length: lines }, (_, index) => (
        <i
          key={index}
          style={{ width: `${widths[index % widths.length]}%` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}



export function LongWait({
  title,
  body,
  onCancel,
}: {
  title: string;
  body: string;
  onCancel?: () => void;
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="longwait" role="status">
      <p className="longwait__title">{title}…</p>
      <p className="longwait__body">{body}</p>
      <p className="longwait__elapsed">
        {it.giornata.elapsed} {fmtElapsed(seconds)}
      </p>
      {onCancel ? (
        <button type="button" className="btn btn--secondary btn--small" onClick={onCancel}>
          {it.app.cancel}
        </button>
      ) : null}
    </div>
  );
}



export function Segmented<T extends string | number>({
  legend,
  options,
  value,
  onChange,
  disabled = false,
}: {
  legend: string;
  options: Array<{ value: T; label: string; title?: string }>;
  value: T;
  onChange: (next: T) => void;
  disabled?: boolean;
}) {
  const groupRef = useRef<HTMLDivElement>(null);

  function focusOption(index: number) {
    const buttons = groupRef.current?.querySelectorAll<HTMLButtonElement>("button");
    buttons?.[index]?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const last = options.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      next = index === last ? 0 : index + 1;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = index === 0 ? last : index - 1;
    }
    if (next !== null) {
      event.preventDefault();
      const option = options[next];
      if (option) {
        onChange(option.value);
        focusOption(next);
      }
    }
  }

  return (
    <div
      ref={groupRef}
      className="seg"
      role="radiogroup"
      aria-label={legend}
    >
      {options.map((option, index) => {
        const checked = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            className="seg__opt"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            disabled={disabled}
            {...(option.title ? { title: option.title } : {})}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}



export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      onClose={onClose}
      aria-labelledby={titleId}
    >
      <p className="dialog__head" id={titleId}>{title}</p>
      <div className="dialog__body">{body}</div>
      <div className="dialog__actions">
        <button type="button" className="btn btn--secondary" onClick={onClose}>
          {it.app.cancel}
        </button>
        <button
          type="button"
          className={`btn ${danger ? "btn--danger" : "btn--primary"}`}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}



export function Disclosure({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <details className="disclosure">
      <summary>
        <IconChevron />
        {label}
      </summary>
      <div className="disclosure__body">{children}</div>
    </details>
  );
}



export function InlineEdit({
  label,
  display,
  initial,
  savedText,
  validate,
  onSave,
}: {
  label: string;
  display: ReactNode;
  initial: string;
  savedText: string;
  validate: (text: string) => string | null;
  onSave: (normalized: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const normalized = validate(text);
    if (normalized === null) {
      setError(it.rosa.budgetInvalid);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(normalized);
      setEditing(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 4000);
    } catch {
      setError(it.app.errorBody);
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <span className="inline-edit">
        <span className="inline-edit__value">{display}</span>
        <button
          type="button"
          className="inline-edit__btn"
          onClick={() => {
            setText(initial);
            setError(null);
            setEditing(true);
          }}
        >
          {label}
        </button>
        {saved ? (
          <span role="status" className="field__hint">
            <Mark kind="ok" /> {savedText}
          </span>
        ) : null}
      </span>
    );
  }

  return (
    <span className="inline-edit">
      <form onSubmit={submit}>
        <label htmlFor={inputId} className="visually-hidden">
          {label}
        </label>
        <input
          ref={inputRef}
          id={inputId}
          className="input"
          value={text}
          onChange={(event) => setText(event.target.value)}
          aria-invalid={error !== null}

        />
        <button type="submit" className="btn btn--primary btn--small" disabled={saving}>
          {it.app.save}
        </button>
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={() => setEditing(false)}
        >
          {it.app.cancel}
        </button>
      </form>
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}



export function Steps({
  labels,
  current,
}: {
  labels: string[];
  current: number;
}) {
  return (
    <ol className="steps">
      {labels.map((labelText, index) => (
        <li
          key={labelText}
          className={`steps__item${index < current ? " steps__item--done" : ""}`}
          {...(index === current ? { "aria-current": "step" } : {})}
        >
          {labelText}
        </li>
      ))}
    </ol>
  );
}
