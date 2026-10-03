'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  Ticket, DashboardStats, TicketFilter, TicketStatus, TicketPriority, TicketType,
} from '@/lib/types';
import { getStats, getTickets, createTicket, updateTicket, deleteTicket } from '@/lib/api';
import { ThemeToggle } from '@/components/theme-toggle';
import {
  Plus, Search, RotateCw, LayoutGrid, Rows3, X, ChevronDown, ChevronLeft, ChevronRight,
  Loader2, Bug, Lightbulb, CheckSquare, Siren, GitPullRequest, Layers, BookOpen,
  FlaskConical, Inbox, AlertCircle, Pencil, Trash2,
} from 'lucide-react';
import { formatDistanceToNowStrict, formatDistanceToNow, format } from 'date-fns';

// ── Vocabulary ────────────────────────────────────────────────────────────────

type Hue = 'sky' | 'butter' | 'lavender' | 'sage' | 'rose' | 'peach' | 'stone';

// Full class strings so Tailwind can see them at build time.
const HUE: Record<Hue, { soft: string; dot: string; ink: string; bar: string }> = {
  sky:      { soft: 'bg-sky-soft',      dot: 'bg-sky-dot',      ink: 'text-sky-ink',      bar: 'bg-sky-ink' },
  butter:   { soft: 'bg-butter-soft',   dot: 'bg-butter-dot',   ink: 'text-butter-ink',   bar: 'bg-butter-ink' },
  lavender: { soft: 'bg-lavender-soft', dot: 'bg-lavender-dot', ink: 'text-lavender-ink', bar: 'bg-lavender-ink' },
  sage:     { soft: 'bg-sage-soft',     dot: 'bg-sage-dot',     ink: 'text-sage-ink',     bar: 'bg-sage-ink' },
  rose:     { soft: 'bg-rose-soft',     dot: 'bg-rose-dot',     ink: 'text-rose-ink',     bar: 'bg-rose-ink' },
  peach:    { soft: 'bg-peach-soft',    dot: 'bg-peach-dot',    ink: 'text-peach-ink',    bar: 'bg-peach-ink' },
  stone:    { soft: 'bg-stone-soft',    dot: 'bg-stone-dot',    ink: 'text-stone-ink',    bar: 'bg-stone-ink' },
};

const STATUSES: TicketStatus[] = ['Open', 'In Progress', 'In Review', 'Blocked', 'Done', 'Closed'];
const STATUS_HUE: Record<TicketStatus, Hue> = {
  'Open':        'sky',
  'In Progress': 'butter',
  'In Review':   'lavender',
  'Blocked':     'rose',
  'Done':        'sage',
  'Closed':      'stone',
};

const PRIORITIES: TicketPriority[] = ['Low', 'Medium', 'High', 'Critical'];
const PRIORITY_META: Record<TicketPriority, { level: number; hue: Hue }> = {
  'Low':      { level: 1, hue: 'stone' },
  'Medium':   { level: 2, hue: 'sky' },
  'High':     { level: 3, hue: 'peach' },
  'Critical': { level: 4, hue: 'rose' },
};

const TYPES: TicketType[] = ['task', 'bug', 'feature', 'incident', 'code_review', 'epic', 'story', 'spike'];
const TYPE_META: Record<TicketType, { label: string; icon: typeof Bug }> = {
  task:        { label: 'Task',        icon: CheckSquare },
  bug:         { label: 'Bug',         icon: Bug },
  feature:     { label: 'Feature',     icon: Lightbulb },
  incident:    { label: 'Incident',    icon: Siren },
  code_review: { label: 'Code review', icon: GitPullRequest },
  epic:        { label: 'Epic',        icon: Layers },
  story:       { label: 'Story',       icon: BookOpen },
  spike:       { label: 'Spike',       icon: FlaskConical },
};

const BOARD_COLUMNS: TicketStatus[] = ['Open', 'In Progress', 'In Review', 'Blocked', 'Done'];

// The ticket service returns naive UTC timestamps; treat them as UTC.
function parseDate(s: string) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}
const ago = (s: string) => formatDistanceToNow(parseDate(s), { addSuffix: true });
const agoShort = (s: string) => {
  const d = parseDate(s);
  return Date.now() - d.getTime() < 60_000 ? 'just now' : formatDistanceToNowStrict(d, { addSuffix: true });
};

// ── Small pieces ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: TicketStatus }) {
  const h = HUE[STATUS_HUE[status]];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${h.soft} ${h.ink}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${h.dot}`} />
      {status}
    </span>
  );
}

function PriorityBars({ priority }: { priority: TicketPriority }) {
  const { level, hue } = PRIORITY_META[priority];
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

function PriorityLabel({ priority }: { priority: TicketPriority }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink">
      <PriorityBars priority={priority} />
      {priority}
    </span>
  );
}

function TypeTag({ type }: { type: TicketType }) {
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
function Avatar({ name, size = 'sm' }: { name: string; size?: 'sm' | 'md' }) {
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

function Assignee({ name }: { name: string | null }) {
  if (!name) return <span className="text-sm text-ink-faint">Unassigned</span>;
  return (
    <span className="inline-flex min-w-0 items-center gap-2 text-sm text-ink">
      <Avatar name={name} />
      <span className="truncate">{name}</span>
    </span>
  );
}

function Select({ value, onChange, children, active, className = '', ...rest }: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  active?: boolean;
  className?: string;
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

function useEscape(handler: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handler(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handler]);
}

// ── Create / edit modal ──────────────────────────────────────────────────────

function TicketModal({ ticket, onClose, onSave }: {
  ticket: Ticket | null;
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
}) {
  const [form, setForm] = useState({
    title:       ticket?.title       || '',
    description: ticket?.description || '',
    ticket_type: ticket?.ticket_type || 'task',
    priority:    ticket?.priority    || 'Medium',
    assignee:    ticket?.assignee    || '',
    status:      ticket?.status      || 'Open',
  });
  const [saving, setSaving] = useState(false);
  useEscape(onClose);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const save = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    try { await onSave(form); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="animate-fade absolute inset-0 bg-[rgb(var(--shadow)/0.35)] backdrop-blur-[2px] dark:bg-black/60" onClick={onClose} />
      <form
        onSubmit={save}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticket-modal-title"
        className="animate-fade-up relative w-full max-w-lg rounded-2xl border border-line bg-surface shadow-lift"
      >
        <div className="flex items-start justify-between px-6 pt-5">
          <div>
            <h2 id="ticket-modal-title" className="font-display text-xl font-semibold tracking-tight">
              {ticket ? 'Edit ticket' : 'New ticket'}
            </h2>
            <p className="mt-0.5 text-sm text-ink-muted">
              {ticket ? ticket.ticket_id : 'Your agents will triage it once it’s created.'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="icon-btn -mr-2 -mt-1" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <label htmlFor="f-title" className="label">Title</label>
            <input
              id="f-title"
              autoFocus
              className="field"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="What needs to happen?"
            />
          </div>
          <div>
            <label htmlFor="f-desc" className="label">Description</label>
            <textarea
              id="f-desc"
              className="field resize-none leading-relaxed"
              rows={4}
              value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="Context, steps to reproduce, acceptance criteria…"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="f-type" className="label">Type</label>
              <Select aria-label="Type" value={form.ticket_type} onChange={v => set('ticket_type', v)}>
                {TYPES.map(t => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
              </Select>
            </div>
            <div>
              <label htmlFor="f-priority" className="label">Priority</label>
              <Select aria-label="Priority" value={form.priority} onChange={v => set('priority', v)}>
                {PRIORITIES.map(p => <option key={p}>{p}</option>)}
              </Select>
            </div>
            {ticket && (
              <div>
                <label className="label">Status</label>
                <Select aria-label="Status" value={form.status} onChange={v => set('status', v)}>
                  {STATUSES.map(s => <option key={s}>{s}</option>)}
                </Select>
              </div>
            )}
            <div className={ticket ? '' : 'col-span-2'}>
              <label htmlFor="f-assignee" className="label">Assignee</label>
              <input
                id="f-assignee"
                className="field"
                value={form.assignee}
                onChange={e => set('assignee', e.target.value)}
                placeholder="Name or email"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 rounded-b-2xl border-t border-line bg-sunken/60 px-6 py-3.5">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button type="submit" disabled={saving || !form.title.trim()} className="btn-primary">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {ticket ? 'Save changes' : 'Create ticket'}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Detail drawer ────────────────────────────────────────────────────────────

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="min-w-0 text-right text-sm text-ink">{children}</dd>
    </div>
  );
}

function TicketDetail({ ticket, onClose, onUpdated, onDeleted }: {
  ticket: Ticket;
  onClose: () => void;
  onUpdated: (t: Ticket) => void;
  onDeleted: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  useEscape(useCallback(() => { if (!editing) onClose(); }, [editing, onClose]));

  const handleSave = async (data: any) => {
    const res = await updateTicket(ticket.ticket_id, data);
    if (res.success && res.data) { onUpdated(res.data); setEditing(false); }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete ${ticket.ticket_id}? This can’t be undone.`)) return;
    setDeleting(true);
    const res = await deleteTicket(ticket.ticket_id);
    if (res.success) onDeleted(ticket.ticket_id);
    setDeleting(false);
  };

  return (
    <>
      {editing && <TicketModal ticket={ticket} onClose={() => setEditing(false)} onSave={handleSave} />}
      <div className="animate-fade fixed inset-0 z-40 bg-[rgb(var(--shadow)/0.2)] dark:bg-black/45" onClick={onClose} />
      <aside
        className="animate-slide-in fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line bg-surface shadow-lift"
        aria-label={`Ticket ${ticket.ticket_id}`}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-3">
          <span className="font-mono text-xs text-ink-muted">{ticket.ticket_id}</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setEditing(true)} className="icon-btn" aria-label="Edit" title="Edit">
              <Pencil className="h-4 w-4" />
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="icon-btn hover:bg-rose-soft hover:text-rose-ink"
              aria-label="Delete"
              title="Delete"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            </button>
            <span className="mx-1 h-5 w-px bg-line" />
            <button onClick={onClose} className="icon-btn" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-6">
          <TypeTag type={ticket.ticket_type} />
          <h2 className="mt-2 font-display text-2xl font-semibold leading-snug tracking-tight">{ticket.title}</h2>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <StatusBadge status={ticket.status} />
            <PriorityLabel priority={ticket.priority} />
          </div>

          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-faint">Description</h3>
            {ticket.description ? (
              <p className="mt-2 whitespace-pre-wrap text-[15px] leading-relaxed text-ink">{ticket.description}</p>
            ) : (
              <p className="mt-2 text-sm italic text-ink-faint">No description provided.</p>
            )}
          </section>

          {ticket.priority_score != null && (
            <section className="mt-7 rounded-xl border border-line bg-sunken/60 p-4">
              <div className="flex items-baseline justify-between">
                <h3 className="text-sm font-medium text-ink">AI priority score</h3>
                <span className="font-display text-2xl font-semibold tabular-nums">
                  {ticket.priority_score}<span className="text-sm text-ink-faint">/100</span>
                </span>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
                <div
                  className={`h-full rounded-full ${HUE[PRIORITY_META[ticket.priority].hue].dot}`}
                  style={{ width: `${ticket.priority_score}%` }}
                />
              </div>
            </section>
          )}

          <section className="mt-7">
            <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-faint">Details</h3>
            <dl className="mt-1 divide-y divide-line">
              <DetailRow label="Assignee"><Assignee name={ticket.assignee} /></DetailRow>
              <DetailRow label="Reporter">{ticket.reported_by || <span className="text-ink-faint">—</span>}</DetailRow>
              <DetailRow label="Source"><span className="capitalize">{ticket.source || '—'}</span></DetailRow>
              {ticket.channel && <DetailRow label="Channel">{ticket.channel}</DetailRow>}
              <DetailRow label="Created">
                <span title={format(parseDate(ticket.created_at), 'PPpp')}>{ago(ticket.created_at)}</span>
              </DetailRow>
              <DetailRow label="Updated">
                <span title={format(parseDate(ticket.updated_at), 'PPpp')}>{ago(ticket.updated_at)}</span>
              </DetailRow>
            </dl>
          </section>
        </div>
      </aside>
    </>
  );
}

// ── Overview ─────────────────────────────────────────────────────────────────

function Overview({ stats }: { stats: DashboardStats | null }) {
  const total = stats?.total_tickets ?? 0;
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);
  const cells = [
    { label: 'Total tickets', value: total,                        note: `${stats?.critical_tickets ?? 0} critical` },
    { label: 'Active',        value: stats?.active_tickets ?? 0,    note: `${pct(stats?.active_tickets ?? 0)}% of all work` },
    { label: 'Completed',     value: stats?.completed_tickets ?? 0, note: `${pct(stats?.completed_tickets ?? 0)}% done` },
    { label: 'Blocked',       value: stats?.blocked_tickets ?? 0,   note: (stats?.blocked_tickets ?? 0) ? 'Needs attention' : 'Nothing stuck' },
  ];
  const byStatus = stats?.by_status ?? {};

  return (
    <section className="card overflow-hidden" aria-label="Overview">
      <div className="grid grid-cols-2 lg:grid-cols-4">
        {cells.map((c, i) => (
          <div
            key={c.label}
            className={`px-5 py-5 ${i % 2 ? 'border-l border-line' : ''} ${i >= 2 ? 'border-t border-line lg:border-t-0' : ''} ${i === 2 ? 'lg:border-l' : ''}`}
          >
            <p className="text-sm text-ink-muted">{c.label}</p>
            {stats ? (
              <p className="mt-1.5 font-display text-[34px] font-semibold leading-none tracking-tight tabular-nums">{c.value}</p>
            ) : (
              <div className="mt-2 h-8 w-12 animate-pulse rounded bg-sunken" />
            )}
            <p className="mt-2 text-xs text-ink-faint">{stats ? c.note : ' '}</p>
          </div>
        ))}
      </div>

      <div className="border-t border-line bg-sunken/40 px-5 py-4">
        <div className="flex h-2 gap-[3px] overflow-hidden rounded-full bg-line/60">
          {total > 0 && STATUSES.filter(s => byStatus[s]).map(s => (
            <div
              key={s}
              className={`${HUE[STATUS_HUE[s]].dot} first:rounded-l-full last:rounded-r-full`}
              style={{ width: `${(byStatus[s] / total) * 100}%` }}
              title={`${s}: ${byStatus[s]}`}
            />
          ))}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {STATUSES.map(s => (
            <li key={s} className="flex items-center gap-1.5 text-xs text-ink-muted">
              <span className={`h-2 w-2 rounded-full ${HUE[STATUS_HUE[s]].dot}`} />
              {s}
              <span className="tabular-nums text-ink-faint">{byStatus[s] ?? 0}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ── Views ────────────────────────────────────────────────────────────────────

function ListView({ tickets, loading, onSelect, onCreate }: {
  tickets: Ticket[];
  loading: boolean;
  onSelect: (t: Ticket) => void;
  onCreate: () => void;
}) {
  if (loading) {
    return (
      <div className="card divide-y divide-line">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-5 py-4">
            <div className="h-3 w-12 animate-pulse rounded bg-sunken" />
            <div className="h-3 flex-1 animate-pulse rounded bg-sunken" />
            <div className="h-5 w-20 animate-pulse rounded-full bg-sunken" />
          </div>
        ))}
      </div>
    );
  }

  if (tickets.length === 0) {
    return (
      <div className="card flex flex-col items-center px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Inbox className="h-5 w-5" />
        </span>
        <h3 className="mt-4 font-display text-lg font-semibold">No tickets here</h3>
        <p className="mt-1 max-w-sm text-sm text-ink-muted">
          Try clearing your filters, or create a ticket — it’ll also arrive automatically from Slack and GitHub.
        </p>
        <button onClick={onCreate} className="btn-primary mt-5">
          <Plus className="h-4 w-4" /> New ticket
        </button>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full table-fixed text-left">
        <thead className="border-b border-line bg-sunken/60">
          <tr className="text-xs font-medium text-ink-muted">
            <th className="w-24 px-5 py-2.5 font-medium">ID</th>
            <th className="px-3 py-2.5 font-medium">Title</th>
            <th className="w-36 px-3 py-2.5 font-medium">Status</th>
            <th className="hidden w-32 px-3 py-2.5 font-medium sm:table-cell">Priority</th>
            <th className="hidden w-44 px-3 py-2.5 font-medium md:table-cell">Assignee</th>
            <th className="hidden w-36 px-5 py-2.5 text-right font-medium lg:table-cell">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {tickets.map(t => (
            <tr
              key={t.ticket_id}
              onClick={() => onSelect(t)}
              onKeyDown={e => { if (e.key === 'Enter') onSelect(t); }}
              tabIndex={0}
              className="group cursor-pointer transition-colors hover:bg-sunken/70 focus:bg-sunken/70 focus:outline-none"
            >
              <td className="px-5 py-3.5 font-mono text-xs text-ink-muted">{t.ticket_id}</td>
              <td className="px-3 py-3.5">
                <p className="truncate text-sm font-medium text-ink group-hover:text-accent">{t.title}</p>
                <div className="mt-0.5"><TypeTag type={t.ticket_type} /></div>
              </td>
              <td className="px-3 py-3.5"><StatusBadge status={t.status} /></td>
              <td className="hidden px-3 py-3.5 sm:table-cell"><PriorityLabel priority={t.priority} /></td>
              <td className="hidden px-3 py-3.5 md:table-cell"><Assignee name={t.assignee} /></td>
              <td className="hidden whitespace-nowrap px-5 py-3.5 text-right text-xs text-ink-muted lg:table-cell">{agoShort(t.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BoardView({ tickets, onSelect }: { tickets: Ticket[]; onSelect: (t: Ticket) => void }) {
  return (
    <div className="scrollbar-thin -mx-4 flex gap-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6">
      {BOARD_COLUMNS.map(status => {
        const col = tickets.filter(t => t.status === status);
        const h = HUE[STATUS_HUE[status]];
        return (
          <section key={status} className="flex w-72 shrink-0 flex-col rounded-xl bg-sunken/70 p-2">
            <header className="flex items-center gap-2 px-2 pb-2.5 pt-1.5">
              <span className={`h-2 w-2 rounded-full ${h.dot}`} />
              <h3 className="text-sm font-medium">{status}</h3>
              <span className="ml-auto text-xs tabular-nums text-ink-faint">{col.length}</span>
            </header>
            <div className="min-h-24 space-y-2">
              {col.map(t => (
                <button
                  key={t.ticket_id}
                  onClick={() => onSelect(t)}
                  className="block w-full rounded-lg border border-line bg-surface p-3.5 text-left shadow-soft transition hover:-translate-y-px hover:border-line-strong hover:shadow-lift"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] text-ink-faint">{t.ticket_id}</span>
                    <PriorityBars priority={t.priority} />
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-sm font-medium leading-snug text-ink">{t.title}</p>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <TypeTag type={t.ticket_type} />
                    {t.assignee && <Avatar name={t.assignee} />}
                  </div>
                </button>
              ))}
              {col.length === 0 && (
                <p className="rounded-lg border border-dashed border-line-strong/70 py-6 text-center text-xs text-ink-faint">
                  No tickets
                </p>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [stats,      setStats]      = useState<DashboardStats | null>(null);
  const [tickets,    setTickets]    = useState<Ticket[]>([]);
  const [total,      setTotal]      = useState(0);
  const [page,       setPage]       = useState(1);
  const [filters,    setFilters]    = useState<TicketFilter>({});
  const [search,     setSearch]     = useState('');
  const [view,       setView]       = useState<'list' | 'board'>('list');
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected,   setSelected]   = useState<Ticket | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const PAGE_SIZE = 20;

  const loadStats = useCallback(async () => {
    const res = await getStats();
    if (res.success && res.data) setStats(res.data);
  }, []);

  const loadTickets = useCallback(async () => {
    setError(null);
    const f = { ...filters, search: search || undefined };
    const res = await getTickets(page, PAGE_SIZE, f);
    if (res.success && res.data) {
      setTickets(res.data.tickets);
      setTotal(res.data.total);
    } else {
      setError(res.error || 'Failed to load tickets');
    }
    setLoading(false);
  }, [page, filters, search]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { loadTickets(); }, [loadTickets]);

  // "/" focuses search, "n" opens the new-ticket dialog
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest('input, textarea, select, [contenteditable]')) return;
      if (e.key === '/') { e.preventDefault(); searchRef.current?.focus(); }
      if (e.key === 'n' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); setShowCreate(true); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const refresh = async () => {
    setRefreshing(true);
    await Promise.all([loadTickets(), loadStats()]);
    setRefreshing(false);
  };

  const handleCreate = async (data: any) => {
    const res = await createTicket(data);
    if (res.success) { setShowCreate(false); loadTickets(); loadStats(); }
  };

  const handleUpdated = (updated: Ticket) => {
    setTickets(ts => ts.map(t => t.ticket_id === updated.ticket_id ? updated : t));
    setSelected(updated);
    loadStats();
  };

  const handleDeleted = (id: string) => {
    setTickets(ts => ts.filter(t => t.ticket_id !== id));
    setSelected(null);
    loadStats();
  };

  const applyFilter = (key: keyof TicketFilter, val: string) => {
    setFilters(f => ({ ...f, [key]: val || undefined }));
    setPage(1);
  };

  const hasFilters = Boolean(filters.status || filters.priority || filters.ticket_type || search);
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const closeDetail = useCallback(() => setSelected(null), []);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <a href="/dashboard" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg shadow-sm">
              <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor" aria-hidden>
                <rect x="2" y="3"   width="12" height="2.2" rx="1.1" />
                <rect x="2" y="6.9" width="8"  height="2.2" rx="1.1" opacity=".8" />
                <rect x="2" y="10.8" width="5" height="2.2" rx="1.1" opacity=".6" />
              </svg>
            </span>
            <span className="hidden font-display text-[17px] font-semibold tracking-tight sm:block">Autonomous PM</span>
          </a>

          <div className="relative mx-auto w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <input
              ref={searchRef}
              className="field py-1.5 pl-9 pr-10"
              placeholder="Search tickets"
              aria-label="Search tickets"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
            <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-line bg-sunken px-1.5 font-mono text-[11px] text-ink-faint sm:block">
              /
            </kbd>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <ThemeToggle />
            <button onClick={refresh} className="icon-btn" aria-label="Refresh" title="Refresh">
              <RotateCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={() => setShowCreate(true)} className="btn-primary ml-2" title="New ticket (N)">
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New ticket</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-6">
        {/* Title */}
        <div className="mb-6">
          <p className="text-sm text-ink-muted" suppressHydrationWarning>{format(new Date(), 'EEEE, d MMMM')}</p>
          <h1 className="mt-1 font-display text-[32px] font-semibold leading-tight tracking-tight">Tickets</h1>
          <p className="mt-1 text-[15px] text-ink-muted">
            Everything the team is working on — triaged and prioritised by your agents.
          </p>
        </div>

        <Overview stats={stats} />

        {/* Toolbar */}
        <div className="mb-4 mt-8 flex flex-wrap items-center gap-2">
          <Select aria-label="Filter by status" value={filters.status || ''} active={!!filters.status}
            onChange={v => applyFilter('status', v)}>
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s}>{s}</option>)}
          </Select>
          <Select aria-label="Filter by priority" value={filters.priority || ''} active={!!filters.priority}
            onChange={v => applyFilter('priority', v)}>
            <option value="">All priorities</option>
            {PRIORITIES.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Select aria-label="Filter by type" value={filters.ticket_type || ''} active={!!filters.ticket_type}
            onChange={v => applyFilter('ticket_type', v)}>
            <option value="">All types</option>
            {TYPES.map(t => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
          </Select>
          {hasFilters && (
            <button
              onClick={() => { setFilters({}); setSearch(''); setPage(1); }}
              className="btn-ghost px-2.5 py-1.5"
            >
              <X className="h-3.5 w-3.5" /> Clear
            </button>
          )}

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-ink-muted sm:inline">
              {total} {total === 1 ? 'ticket' : 'tickets'}
            </span>
            <div className="flex rounded-lg border border-line bg-surface p-0.5" role="tablist" aria-label="View">
              {([['list', 'List', Rows3], ['board', 'Board', LayoutGrid]] as const).map(([key, label, Icon]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={view === key}
                  onClick={() => setView(key)}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm transition-colors ${
                    view === key ? 'bg-sunken font-medium text-ink shadow-soft' : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" /> {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-3 rounded-xl border border-rose-dot/40 bg-rose-soft px-4 py-3 text-sm text-rose-ink">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Couldn’t load tickets</p>
              <p className="opacity-80">{error}. Check that the Ticket Service is running on port 3001.</p>
            </div>
          </div>
        )}

        {view === 'list'
          ? <ListView tickets={tickets} loading={loading} onSelect={setSelected} onCreate={() => setShowCreate(true)} />
          : <BoardView tickets={tickets} onSelect={setSelected} />}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between text-sm text-ink-muted">
            <span>Page {page} of {totalPages}</span>
            <div className="flex items-center gap-1">
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)} className="btn-outline px-2 py-1.5" aria-label="Previous page">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="btn-outline px-2 py-1.5" aria-label="Next page">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </main>

      {showCreate && <TicketModal ticket={null} onClose={() => setShowCreate(false)} onSave={handleCreate} />}
      {selected && (
        <TicketDetail ticket={selected} onClose={closeDetail} onUpdated={handleUpdated} onDeleted={handleDeleted} />
      )}
    </div>
  );
}
