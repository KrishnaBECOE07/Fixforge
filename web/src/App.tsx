import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Box, Braces, Check,
  CheckCheck, CheckCircle2, ChevronDown, ChevronRight, Circle, CircleDot, Clock3, Code2,
  Copy, FileCode2, Fingerprint, FlaskConical, GitBranch, GitCompareArrows,
  GitPullRequest, Layers3, LoaderCircle, LockKeyhole, PanelLeftClose, Play, Plus,
  Search, Settings2, ShieldCheck, Sparkles, Terminal, Workflow, X, XCircle, Zap } from 'lucide-react'
import { api } from './api'
import type { Change, Check as TestCheck, Config, Fixture, InferenceProvider, Metrics, ModelOutcome, Publication,
  PublicationPreview, Run, SourcePreview } from './types'

type Page = 'runs' | 'benchmarks' | 'repositories' | 'settings' | 'guide'
const active = (run: Run) => ['running', 'queued'].includes(run.status)
const statusNames: Record<string, string> = {queued: 'Queued', running: 'In progress', review: 'Ready for review', approved: 'Approved', rejected: 'Rejected', failed: 'Stopped'}
const shortTime = (value: string) => new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
const duration = (ms?: number | null) => ms == null ? '—' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)}s`
const providerNames: Record<InferenceProvider, string> = {openai: 'OpenAI', ollama: 'Ollama'}

function readRoute(): {page: Page; runId: string | null} {
  const hash = window.location.hash.slice(1)
  const repair = /^repair\/([a-f0-9]{12})$/.exec(hash)
  if (repair) return {page: 'runs', runId: repair[1]}
  return {page: ['runs', 'benchmarks', 'repositories', 'settings', 'guide'].includes(hash) ? hash as Page : 'runs', runId: null}
}

function Brand({compact = false}: {compact?: boolean}) {
  return <div className="brand"><span className="brand-mark"><Braces size={23} strokeWidth={2.7} /></span>{!compact && <>FixForge<span className="version">BETA</span></>}</div>
}
function Status({run}: {run: Run}) {
  const Icon = run.status === 'review' ? GitPullRequest : run.status === 'approved' ? CheckCircle2 : run.status === 'failed' || run.status === 'rejected' ? XCircle : active(run) ? LoaderCircle : Circle
  return <span className={`status ${run.status}`}><Icon size={13} className={active(run) ? 'spin' : ''} />{statusNames[run.status] || run.status}</span>
}
function Empty({icon, title, children}: {icon: ReactNode; title: string; children: ReactNode}) {
  return <div className="empty"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{children}</p></div>
}

export default function App() {
  const [page, setPage] = useState<Page>(() => readRoute().page)
  const [runs, setRuns] = useState<Run[]>([])
  const [fixtures, setFixtures] = useState<Fixture[]>([])
  const [config, setConfig] = useState<Config | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [selected, setSelected] = useState<Run | null>(null)
  const [modal, setModal] = useState<boolean | Run>(false)
  const closeModal = useCallback(() => setModal(false), [])
  const [notice, setNotice] = useState('')
  const [connection, setConnection] = useState(true)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const selectedId = useRef<string | null>(readRoute().runId)
  const announce = (message: string) => setNotice(message)
  const refresh = useCallback(async () => {
    try {
      const [nextRuns, nextMetrics] = await Promise.all([api<Run[]>('/runs'), api<Metrics>('/metrics')])
      setRuns(nextRuns); setMetrics(nextMetrics); setConnection(true)
      if (selectedId.current) {
        const detail = await api<Run>(`/runs/${selectedId.current}`)
        if (detail.id === selectedId.current) setSelected(detail)
      }
    } catch { setConnection(false) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => {
    void refresh()
    Promise.all([api<Fixture[]>('/fixtures'), api<Config>('/config')])
      .then(([f, c]) => {setFixtures(f); setConfig(c)})
      .catch(() => setConnection(false))
    const timer = setInterval(() => {void refresh()}, 1600)
    return () => clearInterval(timer)
  }, [refresh])
  useEffect(() => {
    const route = () => {
      const next = readRoute()
      setPage(next.page)
      if (selectedId.current !== next.runId) setSelected(null)
      selectedId.current = next.runId
      if (next.runId) void refresh()
    }
    window.addEventListener('hashchange', route)
    return () => window.removeEventListener('hashchange', route)
  }, [refresh])
  useEffect(() => {if (!notice) return; const t = setTimeout(() => setNotice(''), 5500); return () => clearTimeout(t)}, [notice])
  const navigate = (next: Page) => {setPage(next); setSelected(null); selectedId.current = null; window.location.hash = next}
  const openRun = async (run: Run) => {
    selectedId.current = run.id; setSelected(run); setPage('runs')
    window.location.hash = `repair/${run.id}`
    try {const detail = await api<Run>(`/runs/${run.id}`); if (selectedId.current === run.id) setSelected(detail)}
    catch (error) {announce((error as Error).message)}
  }
  const start = async (body: unknown) => {
    setBusy(true)
    try {
      const run = await api<Run>('/runs', body)
      setModal(false); await openRun(run); await refresh()
      announce('Repair queued. Follow the evidence as it is collected.')
    } catch (error) {announce((error as Error).message); throw error}
    finally {setBusy(false)}
  }
  const review = async (decision: 'approve' | 'reject', note: string) => {
    if (!selected?.evidence) return
    setBusy(true)
    try {
      const updated = await api<Run>(`/runs/${selected.id}/review`, {decision, note, patch_sha256: selected.evidence.patch_sha256})
      setSelected(updated); await refresh()
      announce(decision === 'approve' ? 'Exact patch approved locally. Your review package is ready to export.' : 'Patch rejected. The decision is saved.')
    } catch (error) {announce((error as Error).message)}
    finally {setBusy(false)}
  }
  const waiting = runs.filter(r => r.status === 'review').length
  const filtered = runs.filter(r => (filter === 'all' || (filter === 'active' ? active(r) : r.status === filter)) &&
    `${r.title} ${r.repo} ${r.id}`.toLowerCase().includes(query.toLowerCase()))
  const header = {runs: 'Repair workbench', benchmarks: 'Benchmark lab', repositories: 'Repositories', settings: 'Workspace settings', guide: 'Field guide'}[page]

  return <div className="app-shell">
    <aside className="sidebar">
      <Brand />
      <button className="workspace-switch" onClick={() => navigate('settings')}><span className="workspace-avatar">K</span><span>Personal workspace<small>Local development</small></span><ChevronDown size={14} /></button>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button className={page === 'runs' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('runs')}><Workflow size={18} />Repair workbench{waiting > 0 && <span className="nav-count">{waiting}</span>}</button>
        <button className={page === 'repositories' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('repositories')}><Layers3 size={18} />Repositories</button>
        <button className={page === 'benchmarks' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('benchmarks')}><FlaskConical size={18} />Benchmark lab<span className="nav-new">LAB</span></button>
      </nav>
      <div className="nav-caption secondary-caption">RESOURCES</div>
      <nav aria-label="Resources">
        <button className={page === 'guide' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('guide')}><BookOpen size={18} />Field guide<ArrowUpRight size={13} className="nav-end" /></button>
        <button className={page === 'settings' ? 'nav-item active' : 'nav-item'} onClick={() => navigate('settings')}><Settings2 size={18} />Settings</button>
      </nav>
      <div className="sidebar-bottom"><div className="local-card"><span className="live-dot" /><b>Built to stay in your control</b><p>Every patch stops at your review.</p><div><LockKeyhole size={12} />Local-first workspace</div></div>
      <button className="profile" onClick={() => navigate('settings')}><span className="profile-avatar">K</span><span>Your workspace<small>Personal account</small></span><Settings2 size={16} /></button></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><PanelLeftClose size={17} /><span className="crumb-divider" />Workspace<ChevronRight size={13} /><b>{header}</b></div><div className="topbar-right"><span className="local-label"><span className={connection ? 'live-dot' : 'live-dot offline'} />{connection ? 'Local engine connected' : 'Engine disconnected'}</span><span className="key-hint">v{config?.version ?? '0.2.0'}</span><span className="mini-avatar">K</span></div></header>
      <main>
        {!connection && <div className="connection-banner" role="alert"><XCircle size={16} />Cannot reach the engine. Start it with <code>python -m fixforge</code>. Retrying automatically.</div>}
        {page === 'runs' && !selected && <>
          <div className="page-heading"><div className="eyebrow"><span />THE REPAIR WORKBENCH</div><div className="heading-line"><div><h1>Better fixes. Backed by evidence.</h1><p>Turn issues into verified patches. Keep the final call.</p></div><button className="button primary" onClick={() => setModal(true)}><Plus size={17} />New repair</button></div></div>
          <div className="hero-panel"><div className="hero-copy"><div className="hero-kicker"><Sparkles size={14} />SOFTWARE REPAIR, WITH RECEIPTS</div><h2>From a bug report<br />to a fix you can trust.</h2><p>FixForge connects the code, the cause, and the proof.<br className="desktop-break" /> See what changed. Know why it works.</p><button className="button dark" disabled={busy || !connection} onClick={() => {void start({provider: 'demo', fixture_id: 'payment-zero'}).catch(() => {})}}><Play size={14} fill="currentColor" />Try a live demo<ArrowRight size={15} /></button><span className="demo-caption">Real tests. Curated patches. No API key needed.</span></div>
          <div className="pipeline-art" aria-label="Issue, understand, repair, verify, review workflow"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-grid" /><div className="flow-issue"><CircleDot size={16} /><div><small>GITHUB ISSUE #142</small><b>Zero amount crashes payment API</b></div><span className="tiny-tag">bug</span></div><div className="flow-line line-one" /><div className="flow-steps"><div><Braces size={19} /><span>Understand</span></div><span className="step-connector" /><div className="forge-step"><Zap size={20} /><span>Repair</span></div><span className="step-connector" /><div><ShieldCheck size={19} /><span>Verify</span></div></div><div className="flow-line line-two" /><div className="flow-proof"><div className="proof-icon"><CheckCheck size={19} /></div><div><b>Evidence attached. Ready for you.</b><small><span className="live-dot" />Regression reproduced<span className="proof-divider">/</span>All tests passed</small></div><GitPullRequest size={18} /></div><span className="art-label"><Fingerprint size={12} />Every claim has a trace.</span></div></div>
          <div className="stats-grid"><Stat label="Total repairs" value={String(metrics?.total ?? 0)} detail="Across this workspace" icon={<Workflow size={17} />} /><Stat label="Verified fixes" value={String(metrics?.verified ?? 0)} detail="Regression proven, tests passed" icon={<ShieldCheck size={17} />} /><Stat label="Awaiting your review" value={String(waiting)} detail="Your approval is the final gate" icon={<GitPullRequest size={17} />} /><Stat label="Verification rate" value={metrics?.success_rate == null ? '—' : `${metrics.success_rate}%`} detail={metrics?.completed ? `${metrics.completed} completed local runs` : 'Measured once your first run finishes'} icon={<GitCompareArrows size={17} />} /></div>
          <section className="runs-section"><div className="section-heading"><div><h2>Repair activity<span className="count-chip">{runs.length}</span></h2><p>Every investigation, from first hypothesis to final review.</p></div><span className="quiet-label"><span className="live-dot" />Live updates</span></div>
          <div className="table-panel"><div className="table-toolbar"><div className="filter-tabs">{[['all', 'All repairs'], ['active', 'In progress'], ['review', 'Needs review'], ['approved', 'Approved']].map(([value, label]) => <button key={value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{label}{value === 'review' && waiting > 0 && <span>{waiting}</span>}</button>)}</div><label className="search-box"><Search size={15} /><input aria-label="Search repairs" placeholder="Search repairs..." value={query} onChange={e => setQuery(e.target.value)} /></label></div>
          {loading ? <div className="loading-row"><LoaderCircle size={18} className="spin" />Connecting to your workspace…</div> : filtered.length > 0 ? <div className="table-scroll"><table className="run-table"><thead><tr><th>ISSUE / REPAIR</th><th>STATUS</th><th>EVIDENCE</th><th>STARTED</th><th /></tr></thead><tbody>{filtered.map(run => <tr key={run.id} onClick={() => {void openRun(run)}}><td><button className="issue-cell" onClick={e => {e.stopPropagation(); void openRun(run)}}><span className="issue-icon"><CircleDot size={17} /></span><span><b>{run.title}</b><small>{run.repo}<span>·</span>{run.number ? `#${run.number}` : run.id}<span>·</span>{run.provider === 'demo' ? 'Demo' : 'AI repair'}</small></span></button></td><td><Status run={run} /></td><td>{run.evidence ? <span className="evidence-cell"><Fingerprint size={14} />{run.checks.length} gates verified</span> : <span className="muted">{run.status === 'failed' ? 'Incomplete' : 'Collecting…'}</span>}</td><td className="muted">{shortTime(run.created_at)}</td><td><ArrowUpRight size={16} /></td></tr>)}</tbody></table></div> : runs.length === 0 ? <div className="first-run"><div className="first-run-symbol"><GitBranch size={24} /><span><Plus size={11} /></span></div><div><h3>Your first verified fix starts here</h3><p>Run a sample issue or connect a Python repository to begin.</p></div><button className="button secondary" onClick={() => setModal(true)}>Start a repair<ArrowRight size={14} /></button></div> : <Empty icon={<Search size={22} />} title="No matching repairs">Try another search or activity filter.</Empty>}</div></section>
          <div className="principles"><div><Fingerprint size={19} /><span><b>Proof, before confidence</b><small>A failing test first. A verified fix second.</small></span></div><div><Box size={19} /><span><b>Bounded by design</b><small>Isolated runs. Minimal changes. Clear limits.</small></span></div><div><GitPullRequest size={19} /><span><b>Your code. Your decision.</b><small>Nothing ships without your review.</small></span></div></div>
        </>}
        {page === 'runs' && selected && <RunDetail run={selected} busy={busy} onBack={() => navigate('runs')} onReview={review} notify={announce} onRetry={() => {
          if (selected.provider !== 'demo') setModal(selected)
          else void start({provider: 'demo', fixture_id: selected.fixture_id}).catch(() => {})
        }} />}
        {page === 'benchmarks' && <>
          <PageHeading eyebrow="BENCHMARK LAB" title="Repair outcomes" description="Inspect local model runs and try the curated regression cases." />
          <div className="stats-grid">
            <Stat label="Curated cases" value={String(fixtures.length)} detail="Packaged regression challenges" icon={<FlaskConical size={17} />} />
            <Stat label="Demo runs" value={String(metrics?.demo_runs ?? 0)} detail="Use deterministic patches" icon={<Play size={17} />} />
            <Stat label="AI runs" value={String(metrics?.ai_runs ?? 0)} detail="Use your selected model" icon={<Sparkles size={17} />} />
            <Stat label="Mean run time" value={duration(metrics?.mean_duration_ms)} detail="All completed workspace runs" icon={<Clock3 size={17} />} />
          </div>
          <ModelOutcomes outcomes={metrics?.model_outcomes} />
          <section aria-labelledby="regression-challenge-title">
            <div className="section-heading"><div>
              <h2 id="regression-challenge-title">Regression challenge set</h2>
              <p>Curated demos use real tests and deterministic patches.</p>
            </div></div>
            <div className="case-grid">{fixtures.map(fixture => <article className="case-card" key={fixture.id}>
              <h3>{fixture.title}</h3>
              <p>{fixture.body}</p>
              <div className="tag-row">{fixture.tags.map(tag => <span key={tag}>{tag}</span>)}</div>
              <button className="button secondary" disabled={busy || !connection}
                onClick={() => {void start({provider: 'demo', fixture_id: fixture.id}).catch(() => {})}}>
                <Play size={13} />Run challenge<ArrowUpRight size={14} />
              </button>
            </article>)}</div>
          </section>
        </>}
        {page === 'repositories' && <><PageHeading eyebrow="REPOSITORY INTELLIGENCE" title="Understand the code before changing it." description="Server-registered repositories keep access explicit. FixForge works from bounded copies and never edits your original checkout." /><div className="panel"><div className="panel-heading"><h2>Registered repositories</h2><span className="count-chip">{config?.repositories.length ?? 0}</span></div>{config?.repositories.length ? config.repositories.map(repo => <div className="repo-row" key={repo}><Layers3 size={22} /><div><b>{repo}</b><small>Python AST indexing · unittest · Docker execution</small></div><button className="button secondary" onClick={() => setModal(true)}>New repair<Plus size={14} /></button></div>) : <Empty icon={<Layers3 size={25} />} title="Connect your first Python repository">Register a local path in your server configuration, then restart the engine.</Empty>}</div><div className="setup-panel"><div className="step-badge">01</div><div><h3>Add a repository to .env</h3><p>The browser selects a registered ID. It cannot request arbitrary filesystem paths.</p><pre>{'FIXFORGE_REPOSITORIES={"my-api":"C:/dev/my-api"}'}</pre></div></div><div className="setup-panel"><div className="step-badge">02</div><div><h3>Prepare the execution boundary</h3><p>Start the Linux Docker engine and pull the configured sandbox image. v0.2 supports standard-library Python projects with tests in <code>tests/test_*.py</code>.</p><pre>docker pull python:3.11-slim</pre></div></div><div className="setup-panel"><div className="step-badge">03</div><div><h3>Configure your AI provider</h3><p>{config?.ai_provider === 'ollama'
          ? <>Start Ollama at <code>127.0.0.1:11434</code> and pull the configured model. Use <code>python -m fixforge doctor</code> to check readiness.</>
          : <>Set <code>OPENAI_API_KEY</code> and <code>FIXFORGE_MODEL</code> in .env, then restart FixForge.</>}</p></div></div></>}
        {page === 'settings' && <><PageHeading eyebrow="YOUR WORKSPACE" title="Small permissions. Clear boundaries." description="Configuration lives on your machine. Secrets are never entered into or returned by this interface." /><div className="settings-grid"><section className="panel"><div className="panel-heading"><h2>Engine configuration</h2><Terminal size={18} /></div><Setting label="Edition" value="Local-first · v0.2.0" /><Setting label="Model" value={config?.model ?? 'Loading…'} /><Setting label="AI output ceiling" value={config?.limits ? `${config.limits.output_tokens.toLocaleString()} tokens` : '—'} /><Setting label="Provider request timeout" value={config?.limits ? `${config.limits.provider_timeout_seconds} seconds` : '—'} /><Setting label="AI provider" value={config?.ai_configured ? (config.ai_provider === 'ollama' ? 'Ollama · local' : 'OpenAI · API key configured') : 'Not configured'} state={!!config?.ai_configured} /><Setting label="GitHub issue access" value={config?.github_configured ? 'Token configured' : 'Public issues only'} /><Setting label="Repository scope" value="Python / unittest / stdlib" /><Setting label="Registered repositories" value={String(config?.repositories.length ?? 0)} /></section><section className="panel"><div className="panel-heading"><h2>Repair policy</h2><ShieldCheck size={18} /></div>{['Human review required', 'Existing tests preserved', 'Five production files per patch', 'Network disabled for Docker tests', 'No host fallback for AI code', 'No automated pushes or merges'].map(t => <div className="policy-row" key={t}><CheckCircle2 size={15} />{t}</div>)}</section></div><div className="info-callout"><LockKeyhole size={20} /><div><b>Built for a single local operator.</b><p>This version binds to loopback. Multi-user authentication, remote workers, external attestations, and production hardening are roadmap items. Docker limits reduce risk; they are not a guarantee against hostile code.</p></div></div></>}
        {page === 'guide' && <><PageHeading eyebrow="THE FIXFORGE METHOD" title="A green check should tell a story." description="One issue. A bounded investigation. Evidence you can inspect." /><div className="guide-grid">{[{icon: <CircleDot />, title: '01 / Start with a real contract', text: 'Pick a curated demo or provide an issue for a registered repository. State expected behavior and edge cases clearly.'}, {icon: <Braces />, title: '02 / Locate the cause', text: 'Python AST indexing identifies functions, classes and imports. Lexical relevance ranks source files for a bounded repair plan.'}, {icon: <FlaskConical />, title: '03 / Prove the bug exists', text: 'The existing suite must pass first. Then the new regression must fail against the original code. Import failures and zero discovered tests cannot pass the gate.'}, {icon: <ShieldCheck />, title: '04 / Verify the counterfactual', text: 'The identical named test set must pass on a patched copy. Then original production code is restored in a third copy: the same failure signatures must return. Existing tests stay intact.'}, {icon: <Fingerprint />, title: '05 / Inspect the receipts', text: 'Evidence binds the source revision, issue, explanation, patch, named outcomes and provider receipt. Repository approval checks for source drift. These hashes are local integrity checks, not external signatures.'}, {icon: <GitPullRequest />, title: '06 / Make the final call', text: 'Read the diff, inspect the logs, then approve or reject the exact patch digest. Export a patch, evidence JSON, or review description. Review the GitHub destination and confirm publication to open a draft for an approved repository repair.'}].map(item => <article className="guide-card" key={item.title}><span>{item.icon}</span><h3>{item.title}</h3><p>{item.text}</p></article>)}</div><button className="button primary" onClick={() => setModal(true)}>Start an investigation<ArrowRight size={15} /></button></>}
        <footer><span><Braces size={13} />FixForge <span className="footer-dot">·</span>Evidence-first software repair</span><span>Built for the fix. Designed for the review.</span></footer>
      </main>
    </div>
    {modal && <NewRepair fixtures={fixtures} config={config} busy={busy} initialRun={typeof modal === 'object' ? modal : undefined} onClose={closeModal} onStart={start} />}
    {notice && <div className="toast" role="status"><CircleDot size={16} /><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={14} /></button></div>}
  </div>
}

function Stat({label, value, detail, icon}: {label: string; value: string; detail: string; icon: ReactNode}) {
  return <article className="stat-card"><div><span>{label}</span>{icon}</div><strong>{value}</strong><p>{detail}</p></article>
}

const failureLabels: Record<string, string> = {
  setup: 'Source or Docker setup', baseline: 'Baseline', proposal: 'Proposal', reproduction: 'Reproduction',
  verification: 'Verification', evidence: 'Evidence', interrupted: 'Interrupted', unknown: 'Unclassified',
  provider_timeout: 'Provider timeout', test_timeout: 'Test timeout',
}

function ModelOutcomes({outcomes}: {outcomes: ModelOutcome[] | undefined}) {
  return <section className="model-outcomes" aria-labelledby="model-outcomes-title">
    <div className="section-heading">
      <div>
        <h2 id="model-outcomes-title">Model run outcomes</h2>
        <p>Local AI runs grouped by model and who wrote the regression. Reaching review means the verification gates passed.</p>
      </div>
    </div>
    <div className="table-panel">
      {outcomes === undefined ? <Empty icon={<Sparkles size={19} />} title="Model outcomes unavailable">The local engine has not returned model metrics.</Empty>
        : outcomes.length === 0 ? <Empty icon={<Sparkles size={19} />} title="No model runs yet">Start an AI repository repair to collect outcomes.</Empty>
        : <div className="table-scroll" tabIndex={0} role="region" aria-label="Model outcomes table">
          <table className="model-outcomes-table" aria-labelledby="model-outcomes-title">
            <thead><tr>
              <th scope="col">Provider and model</th><th scope="col">Regression author</th>
              <th scope="col">Reached review</th><th scope="col">In progress</th>
              <th scope="col">Stopped</th><th scope="col">Run time</th>
            </tr></thead>
            <tbody>{outcomes.map(row => <tr key={JSON.stringify([row.provider, row.model, row.regression_origin])}>
              <th scope="row">{providerNames[row.provider] || row.provider}<small>{row.model ?? 'Model unrecorded'}</small></th>
              <td>{row.regression_origin === 'operator' ? 'Operator' : 'Model'}</td>
              <td>{row.completed ? `${row.reached_review} of ${row.completed}` : '—'}</td>
              <td>{row.in_progress}</td>
              <td>{Object.keys(row.failures).length ? <ul>{Object.entries(row.failures).map(([category, count]) =>
                <li key={category}>{count} {failureLabels[category] ?? 'Unclassified'}</li>)}</ul> : '—'}</td>
              <td>{row.timed_runs ? <>
                <span>p50 {duration(row.p50_duration_ms)}</span>
                <small>p95 {duration(row.p95_duration_ms)} · {row.timed_runs} timed</small>
              </> : '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>}
    </div>
  </section>
}

function PageHeading({eyebrow, title, description}: {eyebrow: string; title: string; description: string}) {
  return <div className="page-heading"><div className="eyebrow"><span />{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
}
function Setting({label, value, state}: {label: string; value: string; state?: boolean}) {
  return <div className="setting-row"><span>{label}</span><b>{state !== undefined && <span className={state ? 'live-dot' : 'live-dot offline'} />}{value}</b></div>
}

function NewRepair({fixtures, config, busy, initialRun, onClose, onStart}: {
  fixtures: Fixture[]; config: Config | null; busy: boolean; initialRun?: Run
  onClose: () => void; onStart: (body: unknown) => Promise<void>
}) {
  const [mode, setMode] = useState<'demo' | 'ai'>(initialRun ? 'ai' : 'demo')
  const [fixture, setFixture] = useState('payment-zero')
  const [repository, setRepository] = useState(initialRun?.repository_id ?? config?.repositories[0] ?? '')
  const [title, setTitle] = useState(initialRun?.title ?? '')
  const [body, setBody] = useState(initialRun?.body ?? '')
  const [url, setUrl] = useState(initialRun?.issue_url ?? '')
  const [regression, setRegression] = useState(initialRun?.supplied_regression ?? '')
  const [preview, setPreview] = useState<SourcePreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState('')
  const pending = busy || previewing
  const inferenceProvider = config?.ai_provider
  const dialog = useRef<HTMLDivElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const pendingRef = useRef(false)
  useEffect(() => {pendingRef.current = pending}, [pending])
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    heading.current?.focus()
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pendingRef.current) onClose()
      if (event.key === 'Tab') {
        const elements = dialog.current?.querySelectorAll<HTMLElement>(
          'button:enabled, input:enabled, textarea:enabled, select:enabled, summary, pre[tabindex="0"]',
        )
        if (!elements?.length) return
        const first = elements[0], last = elements[elements.length - 1]
        if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      document.body.style.overflow = oldOverflow
      previous?.focus()
    }
  }, [onClose])
  useEffect(() => {
    if (!dialog.current) return
    dialog.current.scrollTop = 0
    heading.current?.focus()
  }, [preview])
  const changeMode = (next: 'demo' | 'ai') => {
    setMode(next)
    setError('')
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (pending) return
    setError('')
    const issue = {repository_id: repository, title, body, issue_url: url.trim(), supplied_regression: regression}
    try {
      if (mode === 'demo') {
        await onStart({provider: mode, fixture_id: fixture})
      } else if (preview) {
        if (!config?.ai_configured) return
        await onStart({provider: preview.provider, ...issue, source_review_sha256: preview.sha256})
      } else if (inferenceProvider) {
        setPreviewing(true)
        setPreview(await api<SourcePreview>('/source-preview', {...issue, provider: inferenceProvider}))
      }
    } catch (exc) {
      setPreview(null)
      setError((exc as Error).message)
    } finally {
      setPreviewing(false)
    }
  }
  const disabled = pending || (mode === 'ai' && (!inferenceProvider || !repository || (!!preview && !config?.ai_configured)))
  const action = previewing ? 'Preparing preview…' : busy ? 'Starting…' :
    preview ? (preview.provider === 'ollama' ? 'Start local repair' : 'Send to OpenAI and start') :
    mode === 'ai' ? 'Review source' : 'Start repair'
  return <div className="modal-overlay" onMouseDown={event => {
    if (event.target === event.currentTarget && !pending) onClose()
  }}>
    <div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="repair-title">
      <div className="modal-heading">
        <span className="modal-symbol"><GitBranch size={23} /></span>
        <button className="icon-button" aria-label="Close new repair" onClick={onClose} disabled={pending}><X size={19} /></button>
      </div>
      <h2 id="repair-title" ref={heading} tabIndex={-1}>{preview ? 'Review source for inference' : 'Start a new repair'}</h2>
      {!preview && <div className="mode-switch">
        <button className={mode === 'demo' ? 'selected' : ''} disabled={pending} onClick={() => changeMode('demo')}><Play size={14} />Curated demo</button>
        <button className={mode === 'ai' ? 'selected' : ''} disabled={pending} onClick={() => changeMode('ai')}><Sparkles size={14} />AI repository repair</button>
      </div>}
      <form onSubmit={event => {void submit(event)}}>
        {preview ? <SourceReview preview={preview} /> : mode === 'demo' ? <>
          <div className="field-label">CHOOSE A CHALLENGE</div>
          <div className="fixture-options">{fixtures.map(f => <button type="button" disabled={pending} className={fixture === f.id ? 'fixture-option selected' : 'fixture-option'} key={f.id} onClick={() => setFixture(f.id)}><span className="radio-dot">{fixture === f.id && <span />}</span><span><b>{f.title}</b><small>{f.repo} · #{f.number}</small></span></button>)}</div>
          <div className="mode-note"><FlaskConical size={16} /><span>Deterministic patch recipes with real Python test execution. No AI calls, credentials, or Docker required.</span></div>
        </> : <fieldset className="repair-fields" disabled={pending}>
          {!config?.repositories.length && <p className="form-warning">Register a repository in .env, then restart FixForge.</p>}
          <label className="field-label" htmlFor="repository">REGISTERED REPOSITORY</label>
          <select id="repository" value={repository} onChange={event => setRepository(event.target.value)} required>
            <option value="">Select a repository</option>
            {config?.repositories.map(repo => <option key={repo} value={repo}>{repo}</option>)}
          </select>
          <label className="field-label" htmlFor="issue-url">GITHUB ISSUE URL <span>optional</span></label>
          <input id="issue-url" type="url" maxLength={1000} placeholder="https://github.com/owner/repo/issues/123" value={url} onChange={event => setUrl(event.target.value)} />
          <div className="or-divider"><span />or describe the issue<span /></div>
          <label className="field-label" htmlFor="issue-title">ISSUE TITLE</label>
          <input id="issue-title" maxLength={250} required={!url.trim()} placeholder="What is broken?" value={title} onChange={event => setTitle(event.target.value)} />
          <label className="field-label" htmlFor="issue-body">EXPECTED BEHAVIOR & REPRODUCTION</label>
          <textarea id="issue-body" required={!url.trim()} maxLength={20000} rows={4} placeholder="What happens now? What should happen? Include an example." value={body} onChange={event => setBody(event.target.value)} />
          <details className="regression-field" open={initialRun?.supplied_regression ? true : undefined}>
            <summary>Supply a regression test <span>optional</span></summary>
            <label className="field-label" htmlFor="supplied-regression">PYTHON UNITTEST MODULE</label>
            <textarea id="supplied-regression" rows={6} maxLength={8000} spellCheck={false}
              placeholder="Paste a complete unittest module, including imports."
              value={regression} onChange={event => setRegression(event.target.value)} />
          </details>
          <div className="mode-note"><LockKeyhole size={16} /><span>Review the issue and source before inference with {inferenceProvider ? providerNames[inferenceProvider] : 'the configured model'}. Repair tests require Linux Docker.</span></div>
        </fieldset>}
        {preview && !config?.ai_configured && <p className="form-warning">
          Set {preview.provider === 'ollama' ? 'FIXFORGE_OLLAMA_MODEL' : 'OPENAI_API_KEY'} in .env and restart FixForge to continue.
        </p>}
        {error && <p className="form-warning" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="button secondary" disabled={pending} onClick={preview ? () => setPreview(null) : onClose}>{preview ? 'Back to issue' : 'Cancel'}</button>
          <button className="button primary" disabled={disabled}>
            {pending ? <LoaderCircle size={15} className="spin" /> : <ArrowRight size={15} />}{action}
          </button>
        </div>
      </form>
    </div>
  </div>
}

function SourceReview({preview}: {preview: SourcePreview}) {
  const {issue, supplied_regression: regression, untrusted_repository: files} = preview.input
  return <section className="source-review" aria-label="Data selected for inference">
    <p>{preview.provider === 'ollama' ? 'Local Ollama model' : 'OpenAI model'} <code>{preview.model}</code> will receive this issue and {files.length} Python {files.length === 1 ? 'file' : 'files'}{regression && ', along with the supplied regression test'}.</p>
    <details open>
      <summary>Issue text</summary>
      <div className="source-issue">
        <h3>{issue.title}</h3>
        {preview.issue_url && <a className="source-issue-link" href={preview.issue_url} target="_blank" rel="noreferrer">
          View issue on GitHub<ArrowUpRight size={13} />
        </a>}
        <p>{issue.body}</p>
      </div>
    </details>
    {regression && <details>
      <summary>Supplied regression test</summary>
      <pre tabIndex={0}><code>{regression}</code></pre>
    </details>}
    {files.map(file => <details key={file.path}>
      <summary><code>{file.path}</code></summary>
      <pre tabIndex={0}><code>{file.source}</code></pre>
    </details>)}
  </section>
}

const stages = [['index', 'Understand'], ['baseline', 'Baseline'], ['plan', 'Plan'], ['reproduce', 'Reproduce'], ['patch', 'Patch'], ['verify', 'Verify'], ['review', 'Review']]
function RunDetail({run, busy, onBack, onReview, notify, onRetry}: {run: Run; busy: boolean; onBack: () => void; onReview: (d: 'approve' | 'reject', note: string) => Promise<void>; notify: (s: string) => void; onRetry: () => void}) {
  const [tab, setTab] = useState('overview')
  const [file, setFile] = useState(0)
  const [log, setLog] = useState(0)
  const [note, setNote] = useState('')
  useEffect(() => {setTab('overview'); setFile(0); setLog(0); setNote('')}, [run.id])
  const currentStage = stages.findIndex(s => s[0] === run.stage)
  const complete = !!run.evidence
  const reproduced = run.events.some(event => event.stage === 'patch')
  const copy = async (value: string) => {
    try {await navigator.clipboard.writeText(value); notify('Copied to clipboard.')}
    catch {notify('Clipboard unavailable. Use the evidence export to copy the complete record.')}
  }
  return <div className="run-detail"><button className="back-link" onClick={onBack}><ArrowLeft size={15} />All repairs</button><div className="detail-heading"><div><div className="detail-meta"><span>{run.repo}</span><span>/</span><span>{run.number ? `ISSUE #${run.number}` : run.id}</span><span className="tiny-tag">{run.provider === 'demo' ? 'CURATED DEMO' : 'AI REPAIR'}</span></div><h1>{run.title}</h1><div className="detail-status"><Status run={run} /><span><Clock3 size={13} />{shortTime(run.created_at)}</span><span>{duration(run.duration_ms)}</span></div></div>{complete && <a className="button secondary" href={`/api/runs/${run.id}/export/review`}><ArrowDownToLine size={15} />Review package</a>}</div>
    {run.error && <div className="error-callout" role="alert"><XCircle size={19} /><div><b>Verification stopped</b><p>{run.error}</p></div><button className="button secondary" disabled={busy} onClick={onRetry}>Retry<ArrowRight size={14} /></button></div>}
    <div className="stage-bar">{stages.map(([key, label], i) => {const done = complete || run.events.some(e => stages.findIndex(s => s[0] === e.stage) > i); const ongoing = active(run) && currentStage === i; return <div key={key} className={done ? 'stage done' : ongoing ? 'stage ongoing' : 'stage'}><span>{done ? <Check size={13} /> : ongoing ? <LoaderCircle size={13} className="spin" /> : String(i + 1).padStart(2, '0')}</span>{label}{i < stages.length - 1 && <ChevronRight size={12} />}</div>})}</div>
    <div className="detail-tabs" role="tablist" aria-label="Repair evidence">{[['overview', 'Investigation', Workflow], ['diff', 'Code changes', GitCompareArrows], ['tests', 'Test evidence', Terminal], ['evidence', 'Evidence record', Fingerprint]].map(([value, label, Icon]) => {const TabIcon = Icon as typeof Workflow; return <button key={value as string} role="tab" aria-selected={tab === value} className={tab === value ? 'selected' : ''} onClick={() => setTab(value as string)}><TabIcon size={16} />{label as string}{value === 'diff' && run.files.length > 0 && <span className="count-chip">{run.files.length}</span>}</button>})}</div>
    {tab === 'overview' && <div className="investigation-grid"><div><section className="panel issue-panel"><div className="panel-heading"><h2><CircleDot size={16} />The issue</h2></div><p className="issue-body">{run.body}</p>{run.rationale && <><div className="inner-divider" /><div className="panel-heading"><h2><Braces size={16} />Root cause & repair</h2></div><p className="issue-body">{run.rationale}</p></>}</section><section className="panel timeline-panel"><div className="panel-heading"><h2>Investigation timeline</h2><span className="quiet-label">{run.events.length} events</span></div>{!run.events.length && <div className="loading-row"><LoaderCircle size={16} className="spin" />Waiting for the worker…</div>}<div className="timeline">{run.events.map((event, i) => <article className="timeline-event" key={event.seq}><span className={event.stage === 'failed' ? 'timeline-dot failed' : 'timeline-dot'}>{i === run.events.length - 1 && active(run) ? <LoaderCircle size={12} className="spin" /> : event.stage === 'failed' ? <X size={12} /> : <Check size={12} />}</span><div><h3>{event.title}<time>{shortTime(event.at)}</time></h3><p>{event.detail}</p><span className="event-hash">{event.hash.slice(0, 12)}</span></div></article>)}</div></section></div><aside className="investigation-aside"><section className="panel"><div className="panel-heading"><h2>Verification contract</h2><ShieldCheck size={17} /></div>{['Existing suite passes', 'Regression fails before fix', 'Full suite passes after fix', 'Existing tests preserved', 'Same named tests preserved', 'Original failures replayed', 'Human review required'].map((label, i) => <div className="contract-row" key={label}>{complete || (i === 0 && run.checks[0]?.passed) || (i === 1 && reproduced) ? <CheckCircle2 size={16} /> : <Circle size={16} />}<span>{label}</span></div>)}</section><section className="panel"><div className="panel-heading"><h2>Repository map</h2><Code2 size={17} /></div>{run.index.length === 0 ? <p className="aside-note">Source indexing starts when the worker picks up this run.</p> : run.index.map(entry => <div className="index-entry" key={entry.path}><div><FileCode2 size={14} /><b>{entry.path}</b><small>{entry.lines} lines</small></div>{entry.symbols.map(s => <span key={`${s.name}-${s.line}`}><span className="symbol-type">{s.kind === 'class' ? 'C' : 'ƒ'}</span>{s.name}<small>L{s.line}</small></span>)}</div>)}</section></aside></div>}
    {tab === 'diff' && <section className="diff-view panel"><div className="panel-heading"><h2>{run.files.length} changed files</h2><span className="diff-count"><b>+{run.files.reduce((a, f) => a + f.additions, 0)}</b><span>−{run.files.reduce((a, f) => a + f.deletions, 0)}</span></span></div>{!run.files.length ? <Empty icon={<GitCompareArrows size={24} />} title="The patch is still taking shape">Code changes appear after the planner proposes a valid repair.</Empty> : <div className="diff-layout"><aside>{run.files.map((f, i) => <button key={f.path} className={file === i ? 'selected' : ''} onClick={() => setFile(i)}><FileCode2 size={15} /><span>{f.path}</span><small className={f.kind === 'added' ? 'new-file' : ''}>{f.kind === 'added' ? 'A' : 'M'}</small></button>)}</aside><div className="diff-code"><div className="diff-file-heading"><span><FileCode2 size={14} />{run.files[file]?.path}</span><button className="icon-button" aria-label="Copy file diff" onClick={() => {void copy(run.files[file]?.diff ?? '')}}><Copy size={14} /></button></div>{run.files[file] && <Diff change={run.files[file]} />}</div></div>}</section>}
    {tab === 'tests' && <TestEvidence run={run} selected={log} onSelect={setLog} />}
    {tab === 'evidence' && <section className="panel evidence-panel"><div className="panel-heading"><h2><Fingerprint size={18} />Evidence record</h2>{run.evidence && <span className={`status ${run.integrity_valid === false ? 'failed' : 'approved'}`}><ShieldCheck size={13} />{run.integrity_valid === true ? 'Integrity verified' : run.integrity_valid === false ? 'Integrity failed' : 'Checking integrity…'}</span>}</div>{!run.evidence ? <Empty icon={<Fingerprint size={25} />} title="Evidence has not been sealed">A record is created only after all verification contracts pass.</Empty> : <><p className="evidence-intro">This record binds the code snapshot, proposed changes and test results. Approval applies to this exact patch. Evidence v{run.evidence.version ?? 1}.</p><EvidenceReceipt run={run} />{[['Source snapshot', run.evidence.source_sha256], ['Patch SHA-256', run.evidence.patch_sha256], ['Manifest SHA-256', run.evidence.manifest_sha256]].map(([label, value]) => <div className="digest-row" key={label}><span>{label}</span><code>{value}</code><button className="icon-button" aria-label={`Copy ${label}`} onClick={() => {void copy(value)}}><Copy size={14} /></button></div>)}<div className="evidence-downloads"><a className="button secondary" href={`/api/runs/${run.id}/export/evidence`}><ArrowDownToLine size={14} />Evidence JSON</a><a className="button secondary" href={`/api/runs/${run.id}/export/patch`}><ArrowDownToLine size={14} />Unified patch</a><a className="button secondary" href={`/api/runs/${run.id}/export/review`}><ArrowDownToLine size={14} />Review description</a></div><div className="limitations"><b>What this record proves — and its limits</b>{run.evidence.limitations.map(l => <p key={l}>{l}</p>)}</div></>}</section>}
    {complete && <section className="review-gate"><div className="review-gate-icon"><GitPullRequest size={23} /></div><div className="review-gate-copy"><h2>{run.status === 'review' ? 'The evidence is in. The decision is yours.' : run.status === 'approved' ? 'You approved this exact patch.' : 'This patch was rejected.'}</h2><p>{run.status === 'review' ? 'Inspect the changes and test output, then record your review. Approval stays local.' : 'Your decision is saved with the patch digest.'}</p>{run.decision?.note && <p className="decision-note">“{run.decision.note}”</p>}{run.status === 'review' && <textarea aria-label="Review note" placeholder="Add a review note (optional)…" rows={2} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} />}</div>{run.status === 'review' && <div className="review-buttons"><button className="button secondary" disabled={busy} onClick={() => {void onReview('reject', note)}}><X size={14} />Reject</button><button className="button primary" disabled={busy || run.integrity_valid === false} onClick={() => {void onReview('approve', note)}}>{busy ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}Approve patch</button></div>}</section>}
    {run.status === 'approved' && run.provider !== 'demo' && run.source_revision?.kind === 'git' &&
      run.source_revision.dirty === false && run.integrity_valid === true && <GitHubPublication key={run.id} runId={run.id} />}
  </div>
}

function GitHubPublication({runId}: {runId: string}) {
  const [preview, setPreview] = useState<PublicationPreview | null>(null)
  const [result, setResult] = useState<Publication | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const reviewButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (preview || result) heading.current?.focus()
  }, [preview, result])

  const review = async () => {
    setBusy(true)
    setError('')
    try {
      setPreview(await api<PublicationPreview>(`/runs/${runId}/publication-preview`))
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const publish = async () => {
    if (!preview) return
    setBusy(true)
    setError('')
    try {
      setResult(await api<Publication>(`/runs/${runId}/publication`, {sha256: preview.sha256}))
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const cancel = () => {
    setError('')
    setPreview(null)
    requestAnimationFrame(() => reviewButton.current?.focus())
  }

  return <section className="panel publication-panel" aria-labelledby="publication-heading">
    <div className="panel-heading">
      <h2 id="publication-heading" ref={heading} tabIndex={-1}>
        <GitPullRequest size={18} />{preview && !result ? 'Confirm GitHub publication' : 'GitHub publication'}
      </h2>
    </div>
    <div className="publication-content">
      {result ? <div className="publication-actions">
        <p>{result.state === 'closed' ? 'The matching pull request is closed.' :
          result.draft ? 'The draft pull request is open.' : 'The matching pull request is open for review.'}</p>
        <a className="button secondary" href={result.url} target="_blank" rel="noreferrer">
          View pull request #{result.number}<ArrowUpRight size={14} />
        </a>
      </div> : <>
        {preview ? <>
          <p>FixForge will push the approved patch on a repair branch and open a draft pull request in this repository.</p>
          <dl className="publication-details">
            <dt>Repository</dt><dd><code>{preview.repo}</code></dd>
            <dt>Base branch</dt><dd><code>{preview.base}</code></dd>
            <dt>Verified commit</dt><dd><code>{preview.base_commit}</code></dd>
            <dt>Repair branch</dt><dd><code>{preview.branch}</code></dd>
            <dt>Patch SHA-256</dt><dd><code>{preview.patch_sha256}</code></dd>
            <dt>Evidence SHA-256</dt><dd><code>{preview.evidence_sha256}</code></dd>
          </dl>
        </> : <p>Review where this approved patch will be published.</p>}
        {error && <p className="publication-error" role="alert">{error}</p>}
        <div className="publication-actions">
          {preview ? <>
            <button className="button secondary" disabled={busy} onClick={cancel}>Cancel</button>
            <button className="button primary" disabled={busy} onClick={() => {void publish()}}>
              {busy ? <><LoaderCircle size={14} className="spin" />Publishing…</> : <><GitPullRequest size={14} />Publish draft PR</>}
            </button>
          </> : <button className="button secondary" ref={reviewButton} disabled={busy} onClick={() => {void review()}}>
            {busy ? <><LoaderCircle size={14} className="spin" />Loading destination…</> : 'Review GitHub destination'}
          </button>}
        </div>
      </>}
    </div>
  </section>
}

function Diff({change}: {change: Change}) {
  let before = 0, after = 0
  return <div className="diff-lines">{change.diff.split('\n').filter((line, i, all) => i < all.length - 1 || line).map((line, i) => {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line)
    if (hunk) {before = Number(hunk[1]) - 1; after = Number(hunk[2]) - 1}
    const meta = line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')
    const addition = line.startsWith('+') && !meta, deletion = line.startsWith('-') && !meta
    if (!meta && !addition) before++
    if (!meta && !deletion) after++
    return <div key={i} className={`diff-line ${meta ? 'meta' : addition ? 'addition' : deletion ? 'deletion' : ''}`}><span className="line-no">{meta || addition ? '' : before}</span><span className="line-no">{meta || deletion ? '' : after}</span><code>{line || ' '}</code></div>
  })}</div>
}
function TestLog({check}: {check: TestCheck}) {
  const outcomes = check.report?.outcomes
  return <>
    {check.assessment && <div className={`assessment-note ${check.assessment.accepted ? 'accepted' : 'declined'}`}>
      {check.assessment.accepted ? <ShieldCheck size={18} /> : <XCircle size={18} />}
      <div><b>{check.assessment.reason}</b><small>Test identity digest <code>{check.assessment.test_identity_sha256.slice(0, 20)}…</code></small></div>
    </div>}
    {outcomes && <div className="named-tests"><h3>Named test outcomes <span>{Object.keys(outcomes).length}</span></h3>
      <div className="named-test-list">{Object.entries(outcomes).map(([id, result]) => <div className={`named-test ${result.outcome}`} key={id}>
        {result.outcome === 'passed' ? <CheckCircle2 size={14} /> : <CircleDot size={14} />}
        <div><code>{id}</code>{result.exception && <small>{result.exception} · {result.category?.replaceAll('_', ' ')}{result.production_frames.length > 0 && ` · ${result.production_frames.join(', ')}`}</small>}</div>
        <span>{result.outcome}</span>
      </div>)}</div>
    </div>}
    <div className="test-log"><div><span><Terminal size={14} />{check.label}</span><small>exit {check.exit_code}{check.timed_out ? ' · timed out' : ''}</small></div><pre>{check.log || 'No output captured.'}</pre></div>
  </>
}

function TestEvidence({run, selected, onSelect}: {run: Run; selected: number; onSelect: (index: number) => void}) {
  const reproduced = run.events.some(event => event.stage === 'patch')
  return <section className="panel test-panel"><div className="panel-heading"><h2>Execution evidence</h2><span className="quiet-label">{run.provider === 'demo' ? 'Trusted fixture · local Python' : 'Docker · no network'}</span></div>
    {!run.checks.length ? <Empty icon={<Terminal size={24} />} title="Waiting for the first test run">Named outcomes and raw test output are collected at each gate.</Empty> : <>
      <div className="check-cards">{run.checks.map((check, index) => {
        const expected = check.assessment ? check.assessment.accepted && check.assessment.expected_failure : index === 1 && reproduced
        const rejected = check.assessment?.accepted === false
        const label = rejected ? 'Gate rejected' : expected ? 'Failed as required' : check.passed ? 'Passed' : 'Failed'
        return <button key={check.label} className={selected === index ? 'check-card selected' : 'check-card'} onClick={() => onSelect(index)}>
          {rejected ? <XCircle size={19} className="failed-icon" /> : expected ? <CircleDot size={19} className="expected-failure" /> : check.passed ? <CheckCircle2 size={19} /> : <XCircle size={19} className="failed-icon" />}
          <span className="check-label">{check.label}</span><strong>{label}</strong><small>{check.report?.tests ?? 0} tests<span>·</span>{duration(check.duration_ms)}</small>
        </button>
      })}</div>
      {run.checks[selected] && <TestLog check={run.checks[selected]} />}
    </>}
  </section>
}

function EvidenceReceipt({run}: {run: Run}) {
  const source = run.source_revision, provider = run.provider_record
  if (!source && !provider) return <p className="legacy-evidence-note">Legacy record: source revision and per-test identity receipts were introduced in v0.2. Start a new repair to collect them.</p>
  return <div className="receipt-grid">
    <section className="receipt-card"><div className="receipt-title"><GitBranch size={16} /><h3>Source identity</h3></div>
      <dl><div><dt>Snapshot</dt><dd>{source?.kind === 'git' ? 'Git checkout' : source?.kind === 'trusted_fixture' ? 'Curated fixture' : 'Directory snapshot'}</dd></div>
        <div><dt>Revision</dt><dd><code>{source?.commit ? source.commit : 'No Git commit'}</code></dd></div>
        <div><dt>Working tree</dt><dd>{source?.kind === 'trusted_fixture' ? 'Fixed demo source' : source?.dirty === true ? 'Uncommitted changes captured' : source?.dirty === false ? 'Clean at capture' : 'Content fingerprint captured'}</dd></div>
        <div><dt>Python files</dt><dd>{source?.file_count ?? '—'}</dd></div></dl>
      <p>{run.provider === 'demo' ? 'This source is a deterministic fixture.' : 'The checkout is revalidated when you approve. Changes block approval and require a new run.'}</p>
    </section>
    <section className="receipt-card"><div className="receipt-title"><Sparkles size={16} /><h3>Inference receipt</h3></div>
      <dl><div><dt>Planner</dt><dd>{provider?.model ?? 'Not recorded'}</dd></div>
        {provider?.provider && <div><dt>Provider</dt><dd>{providerNames[provider.provider]}</dd></div>}
        <div><dt>Model requests</dt><dd>{provider?.attempts ?? '—'}</dd></div>
        {run.supplied_regression && <div><dt>Regression test</dt><dd>Operator-supplied</dd></div>}
        <div><dt>Reported usage</dt><dd>{provider?.usage ? `${provider.usage.total_tokens.toLocaleString()} tokens` : 'Not reported'}</dd></div>
        <div><dt>Output ceiling</dt><dd>{run.provider === 'demo' ? 'No model call' : provider?.limits.output_tokens ? `${provider.limits.output_tokens.toLocaleString()} tokens` : 'Not recorded'}</dd></div>
        {provider?.disclosure && <>
          <div><dt>Files sent</dt><dd>{provider.disclosure.paths.join(', ')}</dd></div>
          <div><dt>Source review SHA-256</dt><dd><code>{provider.disclosure.sha256}</code></dd></div>
        </>}</dl>
      <p>{run.provider === 'demo' ? 'No model request was made.' : run.provider === 'ollama'
        ? 'Inference ran on the local Ollama server with a token limit and timeout.'
        : 'One request to OpenAI with a token limit and timeout.'}</p>
    </section>
    {run.execution_record && <ExecutionReceipt execution={run.execution_record} />}
  </div>
}

function ExecutionReceipt({execution}: {execution: NonNullable<Run['execution_record']>}) {
  return <section className="receipt-card runtime-receipt">
    <div className="receipt-title"><Terminal size={16} /><h3>Execution environment</h3></div>
    <dl>
      <div><dt>Runner</dt><dd>{execution.runner}{execution.architecture && ` · ${execution.architecture}`}</dd></div>
      {execution.image_id && <div><dt>Image ID</dt><dd><code>{execution.image_id}</code></dd></div>}
      {execution.python_version && <div><dt>Python</dt><dd>{execution.python_version}</dd></div>}
      <div><dt>Harness SHA-256</dt><dd><code>{execution.harness_sha256}</code></dd></div>
    </dl>
  </section>
}
