'use client';

import type { TicketEvent } from '@/lib/types';
import {
  Bot, Github, User, CirclePlus, ArrowRightLeft, Gauge, UserRound, PencilLine,
  Link2, Copy, ListTree, TerminalSquare, MessageSquareText,
} from 'lucide-react';
import { format } from 'date-fns';
import { HUE, Hue, ago, parseDate } from './ui';

const KIND: Record<string, { icon: typeof Bot; hue: Hue }> = {
  created:             { icon: CirclePlus,        hue: 'sky' },
  status_changed:      { icon: ArrowRightLeft,    hue: 'butter' },
  priority_changed:    { icon: Gauge,             hue: 'peach' },
  assigned:            { icon: UserRound,         hue: 'lavender' },
  edited:              { icon: PencilLine,        hue: 'stone' },
  linked:              { icon: Link2,             hue: 'stone' },
  possible_duplicates: { icon: Copy,              hue: 'rose' },
  subtasks_created:    { icon: ListTree,          hue: 'sage' },
  agent_session:       { icon: TerminalSquare,    hue: 'lavender' },
  note:                { icon: MessageSquareText, hue: 'sky' },
};

const AGENTS: Record<string, string> = {
  'priority-agent':     'Priority agent',
  'breakdown-agent':    'Breakdown agent',
  'duplicate-detector': 'Duplicate detector',
  'dev-agent':          'Dev agent',
  'coding-agent':       'Coding agent',
};

function Actor({ actor }: { actor: string | null }) {
  const name = actor || 'system';
  const isAgent = name in AGENTS;
  const Icon = isAgent ? Bot : name === 'github' ? Github : User;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
      isAgent ? 'bg-accent-soft text-accent' : 'bg-sunken text-ink-muted'}`}>
      <Icon className="h-3 w-3" />
      {AGENTS[name] ?? (name === 'github' ? 'GitHub' : name)}
    </span>
  );
}

export function Timeline({ events, loading, onOpenTicket }: {
  events: TicketEvent[];
  loading: boolean;
  onOpenTicket: (id: string) => void;
}) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map(i => (
          <div key={i} className="flex gap-3">
            <div className="h-7 w-7 animate-pulse rounded-full bg-sunken" />
            <div className="flex-1 space-y-2 pt-1">
              <div className="h-3 w-2/3 animate-pulse rounded bg-sunken" />
              <div className="h-3 w-1/3 animate-pulse rounded bg-sunken" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (events.length === 0) {
    return <p className="text-sm text-ink-faint">No activity recorded yet.</p>;
  }

  // Newest first – what changed most recently is what people look for.
  const ordered = [...events].reverse();
  return (
    <ol className="relative">
      {ordered.map((e, i) => {
        const meta = KIND[e.kind] ?? KIND.note;
        const Icon = meta.icon;
        const reason: string | undefined = e.data?.reason;
        const matches: { ticket_id: string; title: string; score: number }[] = e.data?.matches ?? [];
        return (
          <li key={e.id} className="relative flex gap-3 pb-5 last:pb-0">
            {i < ordered.length - 1 && (
              <span className="absolute left-[13px] top-8 h-[calc(100%-1.75rem)] w-px bg-line" aria-hidden />
            )}
            <span className={`relative z-[1] flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${HUE[meta.hue].soft} ${HUE[meta.hue].ink}`}>
              <Icon className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className="text-sm leading-snug text-ink">{e.summary}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-faint">
                <Actor actor={e.actor} />
                <span title={format(parseDate(e.created_at), 'PPpp')}>{ago(e.created_at)}</span>
              </div>
              {reason && (
                <blockquote className="mt-2 rounded-lg border-l-2 border-accent/50 bg-sunken/60 px-3 py-2 text-[13px] leading-relaxed text-ink-muted">
                  {reason}
                </blockquote>
              )}
              {e.kind === 'possible_duplicates' && matches.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {matches.map(m => (
                    <li key={m.ticket_id} className="flex items-center gap-2 text-[13px] text-ink-muted">
                      <button onClick={() => onOpenTicket(m.ticket_id)}
                        className="font-mono text-xs text-accent hover:underline">{m.ticket_id}</button>
                      <span className="truncate">{m.title}</span>
                      <span className="ml-auto shrink-0 tabular-nums text-ink-faint">{Math.round(m.score * 100)}%</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
