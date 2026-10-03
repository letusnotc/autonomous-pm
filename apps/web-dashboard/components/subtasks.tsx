'use client';

import { useState } from 'react';
import type { Ticket, BreakdownProposal, ProposedSubtask } from '@/lib/types';
import { proposeBreakdown, applyBreakdown, addSubtasks } from '@/lib/api';
import { Sparkles, Loader2, Plus, X, AlertCircle, Clock3, CornerDownRight } from 'lucide-react';
import { StatusBadge, TypeTag, SectionTitle, DONE_STATUSES, TYPE_META } from './ui';

export function Subtasks({ ticket, subtasks, onChanged, onOpenTicket }: {
  ticket: Ticket;
  subtasks: Ticket[];
  onChanged: () => void;
  onOpenTicket: (id: string) => void;
}) {
  const [proposal, setProposal] = useState<BreakdownProposal | null>(null);
  const [selected, setSelected] = useState<boolean[]>([]);
  const [busy, setBusy] = useState<'propose' | 'apply' | 'add' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const done = subtasks.filter(s => DONE_STATUSES.includes(s.status)).length;
  const pct = subtasks.length ? Math.round((done / subtasks.length) * 100) : 0;

  const propose = async () => {
    setBusy('propose'); setError(null);
    const res = await proposeBreakdown(ticket.ticket_id);
    setBusy(null);
    if (res.success && res.data) {
      setProposal(res.data);
      setSelected(res.data.subtasks.map(() => true));
    } else {
      setError(res.error || 'Breakdown failed');
    }
  };

  const apply = async () => {
    if (!proposal) return;
    // Re-number dependencies so they still point at the right items after deselection.
    const keep = proposal.subtasks.map((_, i) => i).filter(i => selected[i]);
    const newIndex = new Map(keep.map((old, i) => [old + 1, i + 1]));
    const chosen: ProposedSubtask[] = keep.map(i => ({
      ...proposal.subtasks[i],
      depends_on: proposal.subtasks[i].depends_on.filter(d => newIndex.has(d)).map(d => newIndex.get(d)!),
    }));
    setBusy('apply'); setError(null);
    const res = await applyBreakdown(ticket.ticket_id, chosen);
    setBusy(null);
    if (res.success) { setProposal(null); onChanged(); }
    else setError(res.error || 'Could not create sub-tasks');
  };

  const addOne = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = draft.trim();
    if (!title) return;
    setBusy('add'); setError(null);
    const res = await addSubtasks(ticket.ticket_id, [{ title }]);
    setBusy(null);
    if (res.success) { setDraft(''); onChanged(); }
    else setError(res.error || 'Could not add sub-task');
  };

  const selectedCount = selected.filter(Boolean).length;

  return (
    <section>
      <SectionTitle
        action={!proposal && (
          <button onClick={propose} disabled={busy !== null} className="btn-ghost px-2 py-1 text-xs text-accent hover:text-accent">
            {busy === 'propose' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            {busy === 'propose' ? 'Thinking…' : 'Break down with AI'}
          </button>
        )}
      >
        Sub-tasks {subtasks.length > 0 && <span className="normal-case tracking-normal">· {done}/{subtasks.length} done</span>}
      </SectionTitle>

      {subtasks.length > 0 && (
        <>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-sage-dot transition-all" style={{ width: `${pct}%` }} />
          </div>
          <ul className="mb-3 divide-y divide-line overflow-hidden rounded-xl border border-line">
            {subtasks.map(s => (
              <li key={s.ticket_id}>
                <button onClick={() => onOpenTicket(s.ticket_id)}
                  className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-sunken/70">
                  <span className="w-14 shrink-0 font-mono text-[11px] text-ink-faint">{s.ticket_id}</span>
                  <span className={`min-w-0 flex-1 truncate text-sm ${DONE_STATUSES.includes(s.status) ? 'text-ink-faint line-through' : 'text-ink'}`}>
                    {s.title}
                  </span>
                  <StatusBadge status={s.status} />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {proposal && (
        <div className="mb-3 rounded-xl border border-accent/30 bg-accent-soft/30 p-3">
          <div className="mb-2 flex items-start gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Suggested breakdown</p>
              {proposal.summary && <p className="mt-0.5 text-[13px] text-ink-muted">{proposal.summary}</p>}
            </div>
          </div>
          <ul className="space-y-1.5">
            {proposal.subtasks.map((s, i) => (
              <li key={i}>
                <label className={`flex cursor-pointer gap-3 rounded-lg border bg-surface p-2.5 transition-colors ${
                  selected[i] ? 'border-line-strong' : 'border-line opacity-60'}`}>
                  <input
                    type="checkbox"
                    checked={selected[i]}
                    onChange={e => setSelected(sel => sel.map((v, j) => (j === i ? e.target.checked : v)))}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-ink">{i + 1}. {s.title}</span>
                    {s.description && <span className="mt-0.5 block text-[13px] leading-snug text-ink-muted">{s.description}</span>}
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
                      <TypeTag type={s.ticket_type in TYPE_META ? s.ticket_type : 'task'} />
                      {s.estimate_hours != null && (
                        <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3" />~{s.estimate_hours}h</span>
                      )}
                      {s.depends_on.length > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <CornerDownRight className="h-3 w-3" />after {s.depends_on.map(d => `#${d}`).join(', ')}
                        </span>
                      )}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-xs text-ink-faint">via {proposal.model}</span>
            <div className="flex gap-2">
              <button onClick={() => setProposal(null)} className="btn-ghost px-2.5 py-1.5 text-xs">Discard</button>
              <button onClick={apply} disabled={busy !== null || selectedCount === 0} className="btn-primary px-3 py-1.5 text-xs">
                {busy === 'apply' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Create {selectedCount} sub-task{selectedCount === 1 ? '' : 's'}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-3 flex items-start gap-2 rounded-lg bg-rose-soft px-3 py-2 text-[13px] text-rose-ink">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      <form onSubmit={addOne} className="relative">
        <Plus className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        <input
          className="field py-1.5 pl-9"
          placeholder="Add a sub-task and press Enter"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          disabled={busy === 'add'}
          aria-label="New sub-task title"
        />
      </form>
    </section>
  );
}
