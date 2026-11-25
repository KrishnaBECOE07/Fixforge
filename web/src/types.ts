export type Check = {
  label: string; passed: boolean; exit_code: number; timed_out: boolean;
  duration_ms: number; log: string; runner: string;
  assessment?: {accepted: boolean; reason: string; expected_failure?: boolean; test_identity_sha256: string};
  report: {tests: number; failures: number; errors: number; skipped: number;
    test_ids?: string[]; outcomes?: Record<string, {outcome: string; exception: string | null;
      category: string | null; production_frames: string[]}>} | null;
}
export type Change = {path: string; before: string; after: string; diff: string; kind: string; additions: number; deletions: number}
export type InferenceProvider = 'openai' | 'ollama'
export type Run = {
  id: string; title: string; body: string; repo: string; number: number | null; provider: 'demo' | InferenceProvider;
  created_at: string; updated_at: string; status: string; stage: string; error: string | null;
  tags: string[]; fixture_id?: string; repository_id?: string; issue_url?: string; duration_ms?: number;
  supplied_regression?: string;
  events: {seq: number; at: string; stage: string; title: string; detail: string; hash: string}[];
  checks: Check[]; files: Change[]; rationale?: string; plan?: string[]; integrity_valid?: boolean;
  index: {path: string; symbols: {name: string; line: number; kind: string}[]; imports: string[]; lines: number; relevance: number}[];
  source_revision?: {kind: string; commit: string | null; dirty: boolean | null; file_count: number;
    identity_sha256: string; captured_at: string};
  provider_record?: {model: string; attempts: number; usage: {input_tokens: number; output_tokens: number; total_tokens: number} | null;
    provider?: InferenceProvider;
    limits: {context_chars?: number; output_tokens?: number; timeout_seconds?: number};
    disclosure?: {sha256: string; paths: string[]}};
  execution_record?: {runner: 'Docker' | 'local Python'; harness_sha256: string;
    image_id?: string; image_reference?: string; architecture?: string; python_version?: string};
  evidence: null | {version?: number; patch_sha256: string; manifest_sha256: string; source_sha256: string;
    execution_mode: string; provider: string; contracts: Record<string, boolean>; limitations: string[]};
  decision: {action: string; note: string; at: string} | null;
}
export type SourcePreview = {
  provider: InferenceProvider; model: string; sha256: string;
  input: {issue: {title: string; body: string}; supplied_regression?: string;
    untrusted_repository: {path: string; source: string}[]};
}
export type PublicationPreview = {
  repo: string; base: string; base_commit: string; branch: string;
  patch_sha256: string; evidence_sha256: string; sha256: string;
}
export type Publication = {url: string; number: number; state: 'open' | 'closed'; draft: boolean; reused: boolean}
export type Fixture = {id: string; repo: string; number: number; title: string; body: string; tags: string[]}
export type Config = {version?: string; model: string; ai_provider: InferenceProvider; ai_configured: boolean; repositories: string[]; scope: string; github_configured: boolean;
  limits?: {context_chars: number; output_tokens: number; provider_timeout_seconds: number; attempts: number}}
export type Metrics = {total: number; completed: number; verified: number; approved: number; failed: number;
  success_rate: number | null; mean_duration_ms: number | null; demo_runs: number; ai_runs: number}
