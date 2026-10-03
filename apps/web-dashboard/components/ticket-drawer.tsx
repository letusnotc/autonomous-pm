'use client';

import { useCallback, useEffect, useState } from 'react';
import type { Ticket, TicketEvent, SimilarTicket } from '@/lib/types';
import { updateTicket, deleteTicket, getEvents, getSimilar, getSubtasks } from '@/lib/api';
import { X, Loader2, Pencil, Trash2, CornerLeftUp, Copy, Link2Off, Sparkles } from 'lucide-react';
import { format } from 'date-fns';
import {
  HUE, PRIORITY_META, StatusBadge, PriorityLabel, TypeTag, Assignee, SectionTitle,
  TicketLink, ago, parseDate,
} from './ui';
import { TicketModal } from './ticket-modal';
import { Timeline } from './timeline';
import { Subtasks } from './subtasks';
import { AgentPanel } from './agent-panel';

type Tab = 'overview' | 'activity' | 'agent';

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="min-w-0 text-right text-sm text-ink">{children}</dd>
    </div>
  );
}

function DuplicateNotice({ ticket, similar, onLink, onUnlink, onOpenTicket, onDismiss }: {
  ticket: Ticket;
  similar: SimilarTicket[];
  onLink: (target: string) => Promise<void>;
  onUnlink: () => Promise<void>;
  onOpenTicket: (id: string) => void;
  onDismiss: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (key: string, fn: () => Promise<void>) => { setBusy(key); try { await fn(); } finally { setBusy(null); } };

  if (ticket.duplicate_of) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-line bg-stone-soft/70 px-3.5 py-2.5 text-sm text-stone-ink">
        <Copy className="h-4 w-4 shrink-0" />
        <span className="flex-1">Duplicate of <TicketLink id={ticket.duplicate_of} onOpen={onOpenTicket} /></span>
        <button onClick={() => run('unlink', onUnlink)} disabled={busy !== null} className="btn-ghost px-2 py-1 text-xs">
          {busy === 'unlink' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2Off className="h-3.5 w-3.5" />} Unlink
        </button>
      </div>
    );
  }
  if (similar.length === 0) return null;
  return (
    <div className="rounded-xl border border-butter-dot/50 bg-butter-soft/60 p-3.5">
      <div className="flex items-start gap-2">
        <Copy className="mt-0.5 h-4 w-4 shrink-0 text-butter-ink" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-butter-ink">This may be a duplicate</p>
          <p className="text-[13px] text-butter-ink/80">Detected from similar wording in existing tickets.</p>
        </div>
        <button onClick={onDismiss} className="icon-btn -mr-1 -mt-1 h-7 w-7 text-butter-ink hover:bg-butter-soft" aria-label="Dismiss">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <ul className="mt-2.5 space-y-1.5">
        {similar.map(s => (
          <li key={s.ticket_id} className="flex items-center gap-2 rounded-lg bg-surface/80 px-2.5 py-1.5">
            <TicketLink id={s.ticket_id} onOpen={onOpenTicket} />
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{s.title}</span>
            <span className="shrink-0 text-xs tabular-nums text-ink-faint">{Math.round(s.score * 100)}%</span>
            <button onClick={() => run(s.ticket_id, () => onLink(s.ticket_id))} disabled={busy !== null}
              className="btn-ghost shrink-0 px-2 py-0.5 text-xs" title={`Close as duplicate of ${s.ticket_id}`}>
              {busy === s.ticket_id && <Loader2 className="h-3 w-3 animate-spin" />}Mark duplicate
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TicketDrawer({ ticket, onClose, onUpdated, onDeleted, onOpenTicket, onOpenSettings, onChanged }: {
  ticket: Ticket;
  onClose: () => void;
  onUpdated: (t: Ticket) => void;
  onDeleted: (id: string) => void;
  onOpenTicket: (id: string) => void;
  onOpenSettings: () => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>('overview');
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [similar, setSimilar] = useState<SimilarTicket[]>([]);
  const [dismissed, setDismissed] = useState(false);
  const [subtasks, setSubtasks] = useState<Ticket[]>([]);

  const id = ticket.ticket_id;

  const loadEvents = useCallback(async () => {
    const res = await getEvents(id);
    setEvents(res.success && res.data ? res.data : []);
    setEventsLoading(false);
  }, [id]);

  const loadSubtasks = useCallback(async () => {
    const res = await getSubtasks(id);
    setSubtasks(res.success && res.data ? [...res.data.tickets].reverse() : []);
  }, [id]);

  useEffect(() => { setTab('overview'); setDismissed(false); setEventsLoading(true); }, [id]);
  useEffect(() => { loadEvents(); }, [loadEvents, ticket.updated_at]);

  // Coding agents log notes through MCP without changing the ticket itself, so
  // keep the timeline fresh while it is on screen.
  useEffect(() => {
    if (tab !== 'activity') return;
    loadEvents();
    const timer = setInterval(() => { if (!document.hidden) loadEvents(); }, 5000);
    // Background tabs skip polling; catch up as soon as the tab is visible again.
    const onVisible = () => { if (!document.hidden) loadEvents(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
  }, [tab, loadEvents]);
  useEffect(() => { loadSubtasks(); }, [loadSubtasks]);
  useEffect(() => {
    if (ticket.parent_id) { setSimilar([]); return; }   // sub-tasks are related by design
    getSimilar(id).then(res => setSimilar(res.success && res.data ? res.data : []));
  }, [id, ticket.parent_id]);

  // Escape closes the drawer, but not while the edit dialog is open on top of it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !editing) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [editing, onClose]);

  const save = async (data: any) => {
    const res = await updateTicket(id, data);
    if (res.success && res.data) { onUpdated(res.data); setEditing(false); }
  };

  const remove = async () => {
    if (!confirm(`Delete ${id}? This can’t be undone.`)) return;
    setDeleting(true);
    const res = await deleteTicket(id);
    if (res.success) onDeleted(id);
    setDeleting(false);
  };

  const linkDuplicate = async (target: string) => {
    const res = await updateTicket(id, { duplicate_of: target, status: 'Closed', reason: `Same issue as ${target}` });
    if (res.success && res.data) onUpdated(res.data);
  };
  const unlinkDuplicate = async () => {
    const res = await updateTicket(id, { duplicate_of: '' });
    if (res.success && res.data) onUpdated(res.data);
  };

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'activity', label: 'Activity', count: events.length },
    { key: 'agent',    label: 'Coding agent' },
  ];

  return (
    <>
      {editing && <TicketModal ticket={ticket} onClose={() => setEditing(false)} onSave={save} />}
      <div className="animate-fade fixed inset-0 z-40 bg-[rgb(var(--shadow)/0.2)] dark:bg-black/45" onClick={onClose} />
      <aside
        className="animate-slide-in fixed inset-y-0 right-0 z-40 flex w-full max-w-xl flex-col border-l border-line bg-surface shadow-lift"
        aria-label={`Ticket ${id}`}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-3">
          <div className="flex min-w-0 items-center gap-2 text-xs">
            <span className="font-mono text-ink-muted">{id}</span>
            {ticket.parent_id && (
              <span className="inline-flex items-center gap-1 text-ink-faint">
                <CornerLeftUp className="h-3.5 w-3.5" /> sub-task of <TicketLink id={ticket.parent_id} onOpen={onOpenTicket} />
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setEditing(true)} className="icon-btn" aria-label="Edit" title="Edit">
              <Pencil className="h-4 w-4" />
            </button>
            <button onClick={remove} disabled={deleting} className="icon-btn hover:bg-rose-soft hover:text-rose-ink" aria-label="Delete" title="Delete">
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            </button>
            <span className="mx-1 h-5 w-px bg-line" />
            <button onClick={onClose} className="icon-btn" aria-label="Close"><X className="h-4 w-4" /></button>
          </div>
        </div>

        <div className="px-6 pt-5">
          <TypeTag type={ticket.ticket_type} />
          <h2 className="mt-2 font-display text-2xl font-semibold leading-snug tracking-tight">{ticket.title}</h2>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <StatusBadge status={ticket.status} />
            <PriorityLabel priority={ticket.priority} />
          </div>
          <div className="mt-5 flex gap-5 border-b border-line" role="tablist">
            {tabs.map(t => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                className={`-mb-px border-b-2 pb-2.5 text-sm transition-colors ${
                  tab === t.key ? 'border-accent font-medium text-ink' : 'border-transparent text-ink-muted hover:text-ink'}`}>
                {t.label}
                {!!t.count && <span className="ml-1.5 rounded-full bg-sunken px-1.5 text-[11px] tabular-nums text-ink-faint">{t.count}</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-6">
          {tab === 'overview' && (
            <div className="space-y-7">
              {!dismissed && (
                <DuplicateNotice ticket={ticket} similar={similar} onLink={linkDuplicate} onUnlink={unlinkDuplicate}
                  onOpenTicket={onOpenTicket} onDismiss={() => setDismissed(true)} />
              )}

              <section>
                <SectionTitle>Description</SectionTitle>
                {ticket.description ? (
                  <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink">{ticket.description}</p>
                ) : (
                  <p className="text-sm italic text-ink-faint">No description provided.</p>
                )}
              </section>

              {ticket.priority_score != null && (
                <section className="rounded-xl border border-line bg-sunken/60 p-4">
                  <div className="flex items-baseline justify-between">
                    <h3 className="inline-flex items-center gap-1.5 text-sm font-medium text-ink">
                      <Sparkles className="h-3.5 w-3.5 text-accent" /> AI priority score
                    </h3>
                    <span className="font-display text-2xl font-semibold tabular-nums">
                      {ticket.priority_score}<span className="text-sm text-ink-faint">/100</span>
                    </span>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
                    <div className={`h-full rounded-full ${HUE[PRIORITY_META[ticket.priority].hue].dot}`}
                      style={{ width: `${ticket.priority_score}%` }} />
                  </div>
                  <button onClick={() => setTab('activity')} className="mt-2.5 text-xs text-accent hover:underline">
                    See the reasoning in Activity →
                  </button>
                </section>
              )}

              <Subtasks ticket={ticket} subtasks={subtasks} onOpenTicket={onOpenTicket}
                onChanged={() => { loadSubtasks(); loadEvents(); onChanged(); }} />

              <section>
                <SectionTitle>Details</SectionTitle>
                <dl className="divide-y divide-line">
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
          )}

          {tab === 'activity' && <Timeline events={events} loading={eventsLoading} onOpenTicket={onOpenTicket} />}

          {tab === 'agent' && <AgentPanel ticket={ticket} onOpenSettings={onOpenSettings} onPrepared={loadEvents} />}
        </div>
      </aside>
    </>
  );
}
