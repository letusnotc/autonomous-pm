'use client';

import { useEffect, useState } from 'react';
import type { TicketStatus, TicketPriority, TicketType } from '@/lib/types';
import {
  Bug, Lightbulb, CheckSquare, Siren, GitPullRequest, Layers, BookOpen, FlaskConical,
  ChevronDown, Check, Copy,
} from 'lucide-react';
import { formatDistanceToNowStrict, formatDistanceToNow } from 'date-fns';

// ── Vocabulary ────────────────────────────────────────────────────────────────

export type Hue = 'sky' | 'butter' | 'lavender' | 'sage' | 'rose' | 'peach' | 'stone';

// Full class strings so Tailwind can see them at build time.
export const HUE: Record<Hue, { soft: string; dot: string; ink: string; bar: string }> = {
  sky:      { soft: 'bg-sky-soft',      dot: 'bg-sky-dot',      ink: 'text-sky-ink',      bar: 'bg-sky-ink' },
  butter:   { soft: 'bg-butter-soft',   dot: 'bg-butter-dot',   ink: 'text-butter-ink',   bar: 'bg-butter-ink' },
  lavender: { soft: 'bg-lavender-soft', dot: 'bg-lavender-dot', ink: 'text-lavender-ink', bar: 'bg-lavender-ink' },
  sage:     { soft: 'bg-sage-soft',     dot: 'bg-sage-dot',     ink: 'text-sage-ink',     bar: 'bg-sage-ink' },
  rose:     { soft: 'bg-rose-soft',     dot: 'bg-rose-dot',     ink: 'text-rose-ink',     bar: 'bg-rose-ink' },
  peach:    { soft: 'bg-peach-soft',    dot: 'bg-peach-dot',    ink: 'text-peach-ink',    bar: 'bg-peach-ink' },
  stone:    { soft: 'bg-stone-soft',    dot: 'bg-stone-dot',    ink: 'text-stone-ink',    bar: 'bg-stone-ink' },
};

export const STATUSES: TicketStatus[] = ['Open', 'In Progress', 'In Review', 'Blocked', 'Done', 'Closed'];
export const STATUS_HUE: Record<TicketStatus, Hue> = {
  'Open':        'sky',
  'In Progress': 'butter',
  'In Review':   'lavender',
  'Blocked':     'rose',
  'Done':        'sage',
  'Closed':      'stone',
};

export const PRIORITIES: TicketPriority[] = ['Low', 'Medium', 'High', 'Critical'];
export const PRIORITY_META: Record<TicketPriority, { level: number; hue: Hue }> = {
  'Low':      { level: 1, hue: 'stone' },
  'Medium':   { level: 2, hue: 'sky' },
  'High':     { level: 3, hue: 'peach' },
  'Critical': { level: 4, hue: 'rose' },
};

export const TYPES: TicketType[] = ['task', 'bug', 'feature', 'incident', 'code_review', 'epic', 'story', 'spike'];
export const TYPE_META: Record<TicketType, { label: string; icon: typeof Bug }> = {
  task:        { label: 'Task',        icon: CheckSquare },
  bug:         { label: 'Bug',         icon: Bug },
  feature:     { label: 'Feature',     icon: Lightbulb },
  incident:    { label: 'Incident',    icon: Siren },
  code_review: { label: 'Code review', icon: GitPullRequest },
  epic:        { label: 'Epic',        icon: Layers },
  story:       { label: 'Story',       icon: BookOpen },
  spike:       { label: 'Spike',       icon: FlaskConical },
};

export const DONE_STATUSES: TicketStatus[] = ['Done', 'Closed'];

// The ticket service returns naive UTC timestamps; treat them as UTC.
export function parseDate(s: string) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}
export const ago = (s: string) => formatDistanceToNow(parseDate(s), { addSuffix: true });
export const agoShort = (s: string) => {
  const d = parseDate(s);
  return Date.now() - d.getTime() < 60_000 ? 'just now' : formatDistanceToNowStrict(d, { addSuffix: true });
};

// ── Small pieces ──────────────────────────────────────────────────────────────

export function StatusBadge({ status }: { status: TicketStatus }) {
  const h = HUE[STATUS_HUE[status] ?? 'stone'];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${h.soft} ${h.ink}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${h.dot}`} />
      {status}
    </span>
  );
}

export function PriorityBars({ priority }: { priority: TicketPriority }) {
  const { level, hue } = PRIORITY_META[priority] ?? PRIORITY_META.Medium;
  return (
    <span className="inline-flex items-end gap-[2px]" aria-hidden>
      {[0, 1, 2, 3].map(i => (
        <span
          key={i}
          className={`w-[3px] rounded-sm ${i < level ? HUE[hue].bar : 'bg-line-strong'}`}
          style={{ height: 4 + i * 3 }}
        />
      ))}
    </span>
  );
}

export function PriorityLabel({ priority }: { priority: TicketPriority }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink">
      <PriorityBars priority={priority} />
      {priority}
    </span>
  );
}

export function TypeTag({ type }: { type: TicketType }) {
  const meta = TYPE_META[type] ?? { label: type, icon: CheckSquare };
  const Icon = meta.icon;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
      <Icon className="h-3.5 w-3.5 text-ink-faint" strokeWidth={1.75} />
      {meta.label}
    </span>
  );
}

const AVATAR_HUES: Hue[] = ['peach', 'sage', 'lavender', 'sky', 'butter', 'rose'];
export function Avatar({ name, size = 'sm' }: { name: string; size?: 'sm' | 'md' }) {
  const hash = [...name].reduce((a, c) => a + c.charCodeAt(0), 0);
  const h = HUE[AVATAR_HUES[hash % AVATAR_HUES.length]];
  const initials = name.split(/[\s._@-]+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase();
  const dim = size === 'sm' ? 'h-6 w-6 text-[10px]' : 'h-8 w-8 text-xs';
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${dim} ${h.soft} ${h.ink}`}>
      {initials || '?'}
    </span>
  );
}

export function Assignee({ name }: { name: string | null }) {
  if (!name) return <span className="text-sm text-ink-faint">Unassigned</span>;
  return (
    <span className="inline-flex min-w-0 items-center gap-2 text-sm text-ink">
      <Avatar name={name} />
      <span className="truncate">{name}</span>
    </span>
  );
}

export function Select({ value, onChange, children, active, className = '', ...rest }: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  active?: boolean;
  className?: string;
  id?: string;
  'aria-label'?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <select
        {...rest}
        value={value}
        onChange={e => onChange(e.target.value)}
        className={`field cursor-pointer appearance-none py-1.5 pl-3 pr-8 ${active ? 'border-accent/50 bg-accent-soft/50' : ''}`}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
    </div>
  );
}

export function TicketLink({ id, onOpen }: { id: string; onOpen?: (id: string) => void }) {
  if (!onOpen) return <span className="font-mono text-xs">{id}</span>;
  return (
    <button onClick={() => onOpen(id)} className="font-mono text-xs text-accent underline-offset-2 hover:underline">
      {id}
    </button>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3">
      <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-faint">{children}</h3>
      {action}
    </div>
  );
}

export function CopyButton({ text, label = 'Copy', className = '' }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable – user can select the text */ }
  };
  return (
    <button onClick={copy} className={`btn-ghost px-2 py-1 text-xs ${className}`} aria-label={label}>
      {copied ? <Check className="h-3.5 w-3.5 text-sage-ink" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : label}
    </button>
  );
}

export function useEscape(handler: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handler(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handler]);
}

export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
