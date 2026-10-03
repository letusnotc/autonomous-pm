'use client';

import { useCallback, useEffect, useState } from 'react';
import type { AgentKind, AgentSession, RepoStatus, Ticket } from '@/lib/types';
import { getSession, prepareSession, getRepoStatus, getBrief } from '@/lib/api';
import {
  TerminalSquare, Loader2, GitBranch, FolderGit2, FileText, RefreshCw, AlertTriangle,
  Settings2, ExternalLink, ChevronDown, Plug, Info, Sparkles,
} from 'lucide-react';
import { CopyButton, SectionTitle, ago } from './ui';

const AGENTS: { key: AgentKind; label: string; hint: string }[] = [
  { key: 'claude-code', label: 'Claude Code', hint: 'Terminal agent by Anthropic' },
  { key: 'codex',       label: 'Codex',       hint: 'Terminal agent by OpenAI' },
  { key: 'cursor',      label: 'Cursor',      hint: 'AI code editor' },
];

function CommandBlock({ lines }: { lines: string[] }) {
  const text = lines.join('\n');
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-sunken/70">
      <div className="flex items-center justify-between border-b border-line px-3 py-1">
        <span className="text-[11px] font-medium text-ink-faint">Terminal</span>
        <CopyButton text={text} />
      </div>
      <pre className="scrollbar-thin overflow-x-auto px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink">
        {lines.map((l, i) => <div key={i}><span className="select-none text-ink-faint">$ </span>{l}</div>)}
      </pre>
    </div>
  );
}

function Disclosure({ title, icon: Icon, children }: { title: string; icon: typeof Info; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-line">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink hover:bg-sunken/60">
        <Icon className="h-4 w-4 text-ink-faint" />
        <span className="flex-1">{title}</span>
        <ChevronDown className={`h-4 w-4 text-ink-faint transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="border-t border-line px-3 py-3">{children}</div>}
    </div>
  );
}

function SessionView({ session, agent, setAgent, ticketId }: {
  session: AgentSession; agent: AgentKind; setAgent: (a: AgentKind) => void; ticketId: string;
}) {
  const [brief, setBrief] = useState<string | null>(null);
  const cmd = session.commands[agent];

  const loadBrief = async () => {
    if (brief !== null) return;
    const res = await getBrief(ticketId);
    setBrief(res.success && typeof res.data === 'string' ? res.data : 'Brief unavailable.');
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-sunken/40 p-3.5">
        <dl className="space-y-2 text-sm">
          {session.branch && (
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 shrink-0 text-ink-faint" />
              <dt className="sr-only">Branch</dt>
              <dd className="min-w-0 truncate font-mono text-[12.5px] text-ink">{session.branch}</dd>
              {!session.branch_created && <span className="shrink-0 text-xs text-ink-faint">(suggested)</span>}
            </div>
          )}
          {session.workdir && (
            <div className="flex items-center gap-2">
              <FolderGit2 className="h-4 w-4 shrink-0 text-ink-faint" />
              <dt className="sr-only">Working directory</dt>
              <dd className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink-muted" title={session.workdir}>{session.workdir}</dd>
              <CopyButton text={session.workdir} label="Path" />
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-ink-faint">
            <span>Prepared {ago(session.updated_at)}</span>
            <span>·</span>
            <span>{session.relevant_files.length} relevant files</span>
            {session.ai_plan && (<><span>·</span><span className="inline-flex items-center gap-1"><Sparkles className="h-3 w-3" />AI plan</span></>)}
          </div>
        </dl>
      </div>

      <div>
        <div className="mb-2 flex rounded-lg border border-line bg-surface p-0.5" role="tablist" aria-label="Coding agent">
          {AGENTS.map(a => (
            <button key={a.key} role="tab" aria-selected={agent === a.key} onClick={() => setAgent(a.key)} title={a.hint}
              className={`flex-1 rounded-md px-2 py-1 text-sm transition-colors ${
                agent === a.key ? 'bg-sunken font-medium text-ink shadow-soft' : 'text-ink-muted hover:text-ink'}`}>
              {a.label}
            </button>
          ))}
        </div>

        {agent === 'cursor' ? (
          <div className="space-y-2">
            {cmd.lines.length > 0 && <CommandBlock lines={cmd.lines} />}
            {cmd.deeplink && (
              <a href={cmd.deeplink} className="btn-outline w-full text-sm">
                <ExternalLink className="h-4 w-4" /> Send the prompt to Cursor chat
              </a>
            )}
            <p className="text-xs text-ink-muted">
              Open the folder first, then send the prompt. Prefer the terminal? Use the Cursor CLI:
            </p>
            {cmd.cli_lines && <CommandBlock lines={cmd.cli_lines} />}
          </div>
        ) : (
          <CommandBlock lines={cmd.lines} />
        )}
        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          The agent reads the brief, summarises the ticket and proposes a plan – it waits for your go-ahead before changing code.
        </p>
      </div>

      {session.relevant_files.length > 0 && (
        <section>
          <SectionTitle>Where the agent will start looking</SectionTitle>
          <ul className="space-y-1">
            {session.relevant_files.map(f => (
              <li key={f.path} className="flex items-baseline gap-2 text-[13px]">
                <span className="min-w-0 truncate font-mono text-[12px] text-ink">{f.path}</span>
                <span className="shrink-0 truncate text-xs text-ink-faint">{f.matched.slice(0, 3).join(', ')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="space-y-2">
        <Disclosure title="Preview the context brief" icon={FileText}>
          <div onMouseEnter={loadBrief} onFocus={loadBrief}>
            {brief === null ? (
              <button onClick={loadBrief} className="btn-ghost px-2 py-1 text-xs">Load brief</button>
            ) : (
              <>
                <div className="mb-2 flex justify-end"><CopyButton text={brief} label="Copy brief" /></div>
                <pre className="scrollbar-thin max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-sunken/70 p-3 font-mono text-[11.5px] leading-relaxed text-ink-muted">
                  {brief}
                </pre>
              </>
            )}
          </div>
        </Disclosure>
        <Disclosure title="Ticket tools for the agent (MCP)" icon={Plug}>
          <div className="space-y-2 text-[13px] leading-relaxed text-ink-muted">
            <p>
              The agent can read this ticket, log progress notes and move it to In Review through the
              <span className="font-medium text-ink"> autonomous-pm</span> MCP server.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li><b className="text-ink">Claude Code</b>: already wired in via <code className="font-mono text-xs">--mcp-config</code>.</li>
              <li><b className="text-ink">Cursor</b>: picked up from <code className="font-mono text-xs">.cursor/mcp.json</code> in the worktree.</li>
              <li><b className="text-ink">Codex</b>: add this once to <code className="font-mono text-xs">~/.codex/config.toml</code>:</li>
            </ul>
            <div className="relative">
              <pre className="scrollbar-thin overflow-x-auto rounded-lg bg-sunken/70 p-3 font-mono text-[11.5px] text-ink">{session.codex_mcp_toml}</pre>
              <div className="absolute right-1 top-1"><CopyButton text={session.codex_mcp_toml} /></div>
            </div>
          </div>
        </Disclosure>
      </div>

      {session.notes.length > 0 && (
        <ul className="space-y-1.5">
          {session.notes.map((n, i) => (
            <li key={i} className="flex gap-2 rounded-lg bg-butter-soft px-3 py-2 text-[13px] text-butter-ink">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />{n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AgentPanel({ ticket, onOpenSettings, onPrepared }: {
  ticket: Ticket;
  onOpenSettings: () => void;
  onPrepared: () => void;
}) {
  const [session, setSession] = useState<AgentSession | null>(null);
  const [repo, setRepo] = useState<RepoStatus | null>(null);
  const [agent, setAgent] = useState<AgentKind>('claude-code');
  const [aiPlan, setAiPlan] = useState(true);
  const [loading, setLoading] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    const [s, r] = await Promise.all([getSession(ticket.ticket_id), getRepoStatus()]);
    if (s.success && s.data) { setSession(s.data); setAgent(s.data.agent); } else setSession(null);
    if (r.success && r.data) { setRepo(r.data); setOffline(false); } else setOffline(true);
    setLoading(false);
  }, [ticket.ticket_id]);

  useEffect(() => { load(); }, [load]);

  const prepare = async () => {
    setPreparing(true); setError(null);
    const res = await prepareSession(ticket.ticket_id, agent, aiPlan);
    setPreparing(false);
    if (res.success && res.data) { setSession(res.data); onPrepared(); }
    else setError(res.error || 'Could not prepare the session');
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>;
  }

  if (offline) {
    return (
      <div className="rounded-xl border border-line bg-sunken/50 p-4 text-sm text-ink-muted">
        <p className="font-medium text-ink">Dev Agent Service is offline</p>
        <p className="mt-1">Start it on port 3007 to prepare coding-agent sessions.</p>
      </div>
    );
  }

  const repoLine = repo?.configured ? (
    repo.ok ? (
      <span className="min-w-0 truncate">Linked repo <span className="font-mono text-xs text-ink">{repo.path?.split(/[\\/]/).pop()}</span> · base <span className="font-mono text-xs text-ink">{repo.base_branch}</span></span>
    ) : (
      <span className="min-w-0 truncate text-rose-ink">Repository error: {repo.error}</span>
    )
  ) : (
    <span className="min-w-0 truncate">No repository linked – the brief will contain ticket context only.</span>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-[13px] text-ink-muted">
        {repo?.configured && repo.ok ? <FolderGit2 className="h-4 w-4 shrink-0 text-sage-ink" /> : <AlertTriangle className="h-4 w-4 shrink-0 text-butter-ink" />}
        {repoLine}
        <button onClick={onOpenSettings} className="btn-ghost ml-auto shrink-0 px-2 py-1 text-xs">
          <Settings2 className="h-3.5 w-3.5" /> Settings
        </button>
      </div>

      {!session && (
        <div className="rounded-xl border border-dashed border-line-strong p-5 text-center">
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-accent-soft text-accent">
            <TerminalSquare className="h-5 w-5" />
          </span>
          <h3 className="mt-3 font-display text-lg font-semibold">Hand this ticket to a coding agent</h3>
          <p className="mx-auto mt-1 max-w-sm text-[13px] leading-relaxed text-ink-muted">
            Prepares a branch and worktree, a context brief with the relevant code, related tickets and
            conventions, and a one-line command to start the agent. Nothing is changed until you say so.
          </p>
          <div className="mx-auto mt-4 flex max-w-xs rounded-lg border border-line bg-surface p-0.5" role="radiogroup" aria-label="Agent">
            {AGENTS.map(a => (
              <button key={a.key} role="radio" aria-checked={agent === a.key} onClick={() => setAgent(a.key)}
                className={`flex-1 rounded-md px-2 py-1 text-sm transition-colors ${
                  agent === a.key ? 'bg-sunken font-medium text-ink shadow-soft' : 'text-ink-muted hover:text-ink'}`}>
                {a.label}
              </button>
            ))}
          </div>
          <label className="mt-3 inline-flex cursor-pointer items-center gap-2 text-[13px] text-ink-muted">
            <input type="checkbox" checked={aiPlan} onChange={e => setAiPlan(e.target.checked)}
              className="h-4 w-4 accent-[rgb(var(--accent))]" />
            Draft acceptance criteria and a plan with AI {repo && !repo.llm_configured && <span className="text-ink-faint">(needs an LLM key)</span>}
          </label>
          <div className="mt-4">
            <button onClick={prepare} disabled={preparing} className="btn-primary">
              {preparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <TerminalSquare className="h-4 w-4" />}
              {preparing ? 'Preparing context…' : 'Prepare agent session'}
            </button>
          </div>
        </div>
      )}

      {session && (
        <>
          <SessionView session={session} agent={agent} setAgent={setAgent} ticketId={ticket.ticket_id} />
          <button onClick={prepare} disabled={preparing} className="btn-outline w-full text-sm">
            {preparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {preparing ? 'Refreshing context…' : 'Refresh context'}
          </button>
        </>
      )}

      {error && (
        <p className="flex items-start gap-2 rounded-lg bg-rose-soft px-3 py-2 text-[13px] text-rose-ink">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{error}
        </p>
      )}
    </div>
  );
}
