'use client';

import { useEffect, useState } from 'react';
import type { Ticket, SimilarTicket } from '@/lib/types';
import { findSimilar } from '@/lib/api';
import { X, Loader2, Copy } from 'lucide-react';
import { Select, StatusBadge, useEscape, useDebounced, TYPES, TYPE_META, PRIORITIES, STATUSES } from './ui';

export function TicketModal({ ticket, onClose, onSave, onOpenTicket }: {
  ticket: Ticket | null;
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
  onOpenTicket?: (id: string) => void;
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
  const [similar, setSimilar] = useState<SimilarTicket[]>([]);
  const [checking, setChecking] = useState(false);
  useEscape(onClose);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  // Live duplicate check while drafting a new ticket.
  const query = useDebounced(`${form.title}\n${form.description}`, 400);
  useEffect(() => {
    if (ticket) return;
    const [title, ...rest] = query.split('\n');
    if (title.trim().length < 6) { setSimilar([]); return; }
    let cancelled = false;
    setChecking(true);
    findSimilar(title, rest.join('\n') || undefined).then(res => {
      if (cancelled) return;
      setSimilar(res.success && res.data ? res.data : []);
      setChecking(false);
    });
    return () => { cancelled = true; };
  }, [query, ticket]);

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
        className="animate-fade-up relative flex max-h-[92vh] w-full max-w-lg flex-col rounded-2xl border border-line bg-surface shadow-lift"
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

        <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-6 py-5">
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
            {!ticket && (similar.length > 0 || checking) && (
              <div className="mt-2 rounded-lg border border-butter-dot/50 bg-butter-soft/60 px-3 py-2.5" aria-live="polite">
                <p className="flex items-center gap-1.5 text-[13px] font-medium text-butter-ink">
                  {checking && similar.length === 0
                    ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />Checking for duplicates…</>
                    : <><Copy className="h-3.5 w-3.5" />Similar tickets already exist</>}
                </p>
                {similar.length > 0 && (
                  <ul className="mt-1.5 space-y-1">
                    {similar.map(s => (
                      <li key={s.ticket_id} className="flex items-center gap-2 text-[13px]">
                        <button type="button" onClick={() => onOpenTicket?.(s.ticket_id)}
                          className="font-mono text-xs text-accent hover:underline">{s.ticket_id}</button>
                        <span className="min-w-0 flex-1 truncate text-ink">{s.title}</span>
                        <StatusBadge status={s.status} />
                        <span className="w-9 shrink-0 text-right text-xs tabular-nums text-butter-ink">{Math.round(s.score * 100)}%</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
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
              <Select id="f-type" value={form.ticket_type} onChange={v => set('ticket_type', v)}>
                {TYPES.map(t => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
              </Select>
            </div>
            <div>
              <label htmlFor="f-priority" className="label">Priority</label>
              <Select id="f-priority" value={form.priority} onChange={v => set('priority', v)}>
                {PRIORITIES.map(p => <option key={p}>{p}</option>)}
              </Select>
            </div>
            {ticket && (
              <div>
                <label htmlFor="f-status" className="label">Status</label>
                <Select id="f-status" value={form.status} onChange={v => set('status', v)}>
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
