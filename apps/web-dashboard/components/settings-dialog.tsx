'use client';

import { useEffect, useState } from 'react';
import type { AgentKind, AgentSettings, RepoStatus } from '@/lib/types';
import { getAgentSettings, saveAgentSettings, getRepoStatus } from '@/lib/api';
import { X, Loader2, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { useEscape } from './ui';

const AGENTS: { key: AgentKind; label: string }[] = [
  { key: 'claude-code', label: 'Claude Code' },
  { key: 'codex',       label: 'Codex' },
  { key: 'cursor',      label: 'Cursor' },
];

function Toggle({ checked, onChange, label, hint }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; hint: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? 'bg-accent' : 'bg-line-strong'}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface shadow-soft transition-all ${checked ? 'left-[18px]' : 'left-0.5'}`} />
      </button>
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="block text-[13px] leading-snug text-ink-muted">{hint}</span>
      </span>
    </label>
  );
}

function RepoBadge({ status }: { status: RepoStatus | null }) {
  if (!status) return null;
  return (
    <div className="space-y-1.5 rounded-xl border border-line bg-sunken/50 px-3.5 py-3 text-[13px]">
      {!status.configured ? (
        <p className="text-ink-muted">No repository linked yet.</p>
      ) : status.ok ? (
        <p className="flex items-start gap-2 text-ink">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-sage-ink" />
          <span className="min-w-0">
            Connected on <span className="font-mono text-xs">{status.branch}</span> · {status.commit}
            {status.workspaces_dir && <span className="block truncate text-xs text-ink-faint">Worktrees: {status.workspaces_dir}</span>}
          </span>
        </p>
      ) : (
        <p className="flex items-start gap-2 text-rose-ink"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{status.error}</p>
      )}
      <p className={`flex items-center gap-2 ${status.llm_configured ? 'text-ink-muted' : 'text-butter-ink'}`}>
        <Sparkles className="h-4 w-4 shrink-0" />
        {status.llm_configured
          ? 'AI breakdown and plans are enabled.'
          : 'No LLM key configured – AI breakdown and plans are disabled.'}
      </p>
    </div>
  );
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [status, setStatus] = useState<RepoStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEscape(onClose);

  useEffect(() => {
    (async () => {
      const [s, r] = await Promise.all([getAgentSettings(), getRepoStatus()]);
      if (s.success && s.data) setSettings(s.data); else setError(s.error || 'Dev Agent Service is offline');
      if (r.success && r.data) setStatus(r.data);
    })();
  }, []);

  const set = <K extends keyof AgentSettings>(k: K, v: AgentSettings[K]) => {
    setSettings(s => (s ? { ...s, [k]: v } : s));
    setSaved(false);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true); setError(null);
    const res = await saveAgentSettings(settings);
    if (res.success && res.data) {
      setSettings(res.data);
      const r = await getRepoStatus();
      if (r.success && r.data) setStatus(r.data);
      setSaved(true);
    } else {
      setError(res.error || 'Could not save settings');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="animate-fade absolute inset-0 bg-[rgb(var(--shadow)/0.35)] backdrop-blur-[2px] dark:bg-black/60" onClick={onClose} />
      <form onSubmit={save} role="dialog" aria-modal="true" aria-labelledby="settings-title"
        className="animate-fade-up relative flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl border border-line bg-surface shadow-lift">
        <div className="flex items-start justify-between px-6 pt-5">
          <div>
            <h2 id="settings-title" className="font-display text-xl font-semibold tracking-tight">Agent settings</h2>
            <p className="mt-0.5 text-sm text-ink-muted">Connect your codebase so tickets come with code context.</p>
          </div>
          <button type="button" onClick={onClose} className="icon-btn -mr-2 -mt-1" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {!settings && !error && <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>}
          {settings && (
            <>
              <RepoBadge status={status} />
              <div>
                <label htmlFor="s-path" className="label">Local repository path</label>
                <input id="s-path" className="field font-mono text-[13px]" placeholder="C:\code\my-app  or  ~/code/my-app"
                  value={settings.repo_path ?? ''} onChange={e => set('repo_path', e.target.value)} />
              </div>
              <div>
                <label htmlFor="s-url" className="label">…or Git URL to clone</label>
                <input id="s-url" className="field font-mono text-[13px]" placeholder="https://github.com/org/repo.git"
                  value={settings.repo_url ?? ''} onChange={e => set('repo_url', e.target.value)} />
                <p className="mt-1 text-xs text-ink-faint">Used only when no local path is set.</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="s-base" className="label">Base branch</label>
                  <input id="s-base" className="field font-mono text-[13px]" placeholder={status?.base_branch || 'repo default'}
                    value={settings.base_branch ?? ''} onChange={e => set('base_branch', e.target.value)} />
                </div>
                <div>
                  <label htmlFor="s-ws" className="label">Worktrees folder</label>
                  <input id="s-ws" className="field font-mono text-[13px]" placeholder="~/apm-workspaces"
                    value={settings.workspaces_dir ?? ''} onChange={e => set('workspaces_dir', e.target.value)} />
                </div>
              </div>
              <div>
                <span className="label">Default coding agent</span>
                <div className="flex rounded-lg border border-line bg-surface p-0.5" role="radiogroup" aria-label="Default coding agent">
                  {AGENTS.map(a => (
                    <button type="button" key={a.key} role="radio" aria-checked={settings.default_agent === a.key}
                      onClick={() => set('default_agent', a.key)}
                      className={`flex-1 rounded-md px-2 py-1.5 text-sm transition-colors ${
                        settings.default_agent === a.key ? 'bg-sunken font-medium text-ink shadow-soft' : 'text-ink-muted hover:text-ink'}`}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                <Toggle checked={settings.use_worktrees} onChange={v => set('use_worktrees', v)}
                  label="Create a branch and worktree per ticket"
                  hint="Each ticket gets its own folder on branch apm/APM-x, so your main checkout is never touched." />
                <Toggle checked={settings.auto_prepare} onChange={v => set('auto_prepare', v)}
                  label="Prepare a session for every new ticket"
                  hint="Manual mode: the context is ready when someone picks the ticket up. No code is written automatically." />
              </div>
            </>
          )}
          {error && <p className="flex items-start gap-2 rounded-lg bg-rose-soft px-3 py-2 text-[13px] text-rose-ink"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 rounded-b-2xl border-t border-line bg-sunken/60 px-6 py-3.5">
          {saved && <span className="mr-auto inline-flex items-center gap-1.5 text-sm text-sage-ink"><CheckCircle2 className="h-4 w-4" />Saved</span>}
          <button type="button" onClick={onClose} className="btn-ghost">Close</button>
          <button type="submit" disabled={!settings || saving} className="btn-primary">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Save settings
          </button>
        </div>
      </form>
    </div>
  );
}
