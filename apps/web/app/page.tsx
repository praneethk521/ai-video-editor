"use client";

import {
  CheckCircle2,
  Clapperboard,
  FileVideo,
  FolderSync,
  GitBranch,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  XCircle
} from "lucide-react";
import { useMemo, useState } from "react";

type TimelineClip = {
  asset_id: string;
  start: number;
  end: number;
  timeline_start: number;
  caption?: string;
  crop_strategy?: string;
};

type TimelineTrack = {
  type: string;
  clips: TimelineClip[];
};

type TimelinePlanBody = {
  tracks?: TimelineTrack[];
  strategy?: {
    hook?: string;
    pacing?: string;
    title_ideas?: string[];
  };
  export?: {
    width?: number;
    height?: number;
    fps?: number;
  };
};

type TimelinePlan = {
  id: string;
  variant: string;
  status: string;
  confidence_score: number;
  plan: TimelinePlanBody;
  review_notes?: string | null;
};

type ProjectStatus = {
  project_id: string;
  status: string;
  media_count: number;
  render_jobs: Array<{ id: string; variant: string; status: string }>;
};

type OutputVideo = {
  id: string;
  variant: string;
  width: number;
  height: number;
  duration_seconds: number;
  private_locator: string;
  validation?: {
    status?: string;
  };
  delivery?: {
    target?: string;
    status?: string;
    details?: {
      details?: {
        error?: string;
        retention?: {
          privacy?: string;
          retention_policy?: string;
          retention_days?: string;
          delete_after?: string;
        };
      };
      staged_source_cleanup?: {
        status?: string;
      };
    };
  };
};

type OutputRetentionRow = {
  id: string;
  variant: string;
  target: string;
  status: string;
  has_retention_metadata: boolean;
  retention_due: boolean;
  days_until_delete?: number | null;
  cleanup_status?: string | null;
};

type OutputCleanupRow = {
  id: string;
  variant: string;
  target: string;
  retention_due: boolean;
  cleanup: {
    status: string;
    reason?: string;
  };
};

type AnalysisResult = {
  id: string;
  provider: string;
  result: {
    summary?: {
      scene_count?: number;
      primary_orientation?: string;
      average_highlight_score?: number;
      audio_quality?: string;
    };
    asset_features?: Array<{ asset_id: string }>;
  };
};

type LogEntry = {
  tone: "ok" | "warn" | "error";
  message: string;
};

const defaultApiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function variantLabel(variant: string) {
  return variant === "youtube_16x9" ? "YouTube 16:9" : "Shorts 9:16";
}

function clipCount(plan: TimelinePlanBody) {
  return plan.tracks?.reduce((sum, track) => sum + track.clips.length, 0) ?? 0;
}

function retentionSummary(output: OutputVideo) {
  const retention = output.delivery?.details?.details?.retention;
  if (!retention) return null;
  const policy = retention.retention_policy?.replaceAll("_", " ");
  const days = retention.retention_days ? `${retention.retention_days}d` : policy;
  const deleteAfter = retention.delete_after ? `delete after ${retention.delete_after}` : null;
  return [days ? `Retention ${days}` : "Retention policy", deleteAfter].filter(Boolean).join(" · ");
}

function cleanupSummary(output: OutputVideo) {
  const status = output.delivery?.details?.staged_source_cleanup?.status;
  return status ? `Staged cleanup ${status}` : null;
}

export default function Page() {
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [apiToken, setApiToken] = useState("");
  const [projectName, setProjectName] = useState("Launch video");
  const [folderUrl, setFolderUrl] = useState("https://drive.google.com/drive/folders/private-folder-id");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [plans, setPlans] = useState<TimelinePlan[]>([]);
  const [outputs, setOutputs] = useState<OutputVideo[]>([]);
  const [retentionRows, setRetentionRows] = useState<OutputRetentionRow[]>([]);
  const [cleanupRows, setCleanupRows] = useState<OutputCleanupRow[]>([]);
  const [analysisResults, setAnalysisResults] = useState<AnalysisResult[]>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);

  const approvedCount = useMemo(() => plans.filter((plan) => plan.status === "approved").length, [plans]);
  const draftCount = useMemo(() => plans.filter((plan) => plan.status === "draft").length, [plans]);
  const latestAnalysis = analysisResults[0];

  function pushLog(entry: LogEntry) {
    setLog((current) => [entry, ...current].slice(0, 6));
  }

  async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!apiToken.trim()) {
      throw new Error("API token is required");
    }
    const response = await fetch(`${apiBase.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
        ...(init.headers ?? {})
      }
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Request failed with ${response.status}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  async function run(label: string, task: () => Promise<void>) {
    setBusy(label);
    try {
      await task();
      pushLog({ tone: "ok", message: label });
    } catch (error) {
      pushLog({ tone: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  }

  async function refreshStatus(targetProjectId = projectId) {
    if (!targetProjectId) return;
    const nextStatus = await api<ProjectStatus>(`/projects/${targetProjectId}/status`);
    setStatus(nextStatus);
  }

  async function refreshPlans(targetProjectId = projectId) {
    if (!targetProjectId) return;
    const response = await api<{ plans: TimelinePlan[] }>(`/projects/${targetProjectId}/plans`);
    setPlans(response.plans);
  }

  async function refreshAnalysis(targetProjectId = projectId) {
    if (!targetProjectId) return;
    const response = await api<{ results: AnalysisResult[] }>(`/projects/${targetProjectId}/analysis`);
    setAnalysisResults(response.results);
  }

  async function createProject() {
    await run("Project created", async () => {
      const project = await api<{ id: string; status: string }>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectName })
      });
      setProjectId(project.id);
      setStatus({ project_id: project.id, status: project.status, media_count: 0, render_jobs: [] });
      setPlans([]);
      setOutputs([]);
      setRetentionRows([]);
      setCleanupRows([]);
      setAnalysisResults([]);
    });
  }

  async function connectDrive() {
    await run("Drive connection started", async () => {
      const response = await api<{ authorization_url?: string }>(`/projects/${projectId}/connect-drive`, {
        method: "POST",
        body: JSON.stringify({ folder_url: folderUrl })
      });
      if (response.authorization_url) {
        window.open(response.authorization_url, "_blank", "noopener,noreferrer");
      }
      await refreshStatus();
    });
  }

  async function syncDrive() {
    await run("Drive folder synced", async () => {
      await api(`/projects/${projectId}/sync-drive`, { method: "POST" });
      await refreshStatus();
    });
  }

  async function analyze() {
    await run("Analysis complete", async () => {
      await api(`/projects/${projectId}/analyze`, { method: "POST" });
      await refreshStatus();
      await refreshAnalysis();
      await refreshPlans();
    });
  }

  async function regenerate() {
    await run("Plans regenerated", async () => {
      await api(`/projects/${projectId}/plans/regenerate`, {
        method: "POST",
        body: JSON.stringify({ variants: ["youtube_16x9", "shorts_9x16"], notes: "Regenerated from dashboard review." })
      });
      await refreshPlans();
    });
  }

  async function approve(planId: string) {
    await run("Plan approved", async () => {
      await api(`/projects/${projectId}/plans/${planId}/approve`, {
        method: "POST",
        body: JSON.stringify({ notes: reviewNotes[planId] || null })
      });
      await refreshPlans();
    });
  }

  async function reject(planId: string) {
    await run("Plan rejected", async () => {
      await api(`/projects/${projectId}/plans/${planId}/reject`, {
        method: "POST",
        body: JSON.stringify({ notes: reviewNotes[planId] || null })
      });
      await refreshPlans();
    });
  }

  async function renderApproved() {
    await run("Render queued", async () => {
      await api(`/projects/${projectId}/render`, {
        method: "POST",
        body: JSON.stringify({ variants: ["youtube_16x9", "shorts_9x16"] })
      });
      await refreshStatus();
    });
  }

  async function loadOutputs() {
    await run("Outputs loaded", async () => {
      await refreshOutputs();
    });
  }

  async function refreshOutputs() {
    if (!projectId) return;
    const response = await api<{ outputs: OutputVideo[] }>(`/projects/${projectId}/outputs`);
    setOutputs(response.outputs);
  }

  async function loadRetentionReport() {
    await run("Retention report loaded", async () => {
      if (!projectId) return;
      const response = await api<{ outputs: OutputRetentionRow[] }>(`/projects/${projectId}/outputs/retention`);
      setRetentionRows(response.outputs);
    });
  }

  async function runRetentionCleanup(dryRun: boolean) {
    await run(dryRun ? "Retention cleanup preview loaded" : "Retention cleanup completed", async () => {
      if (!projectId) return;
      const response = await api<{ outputs: OutputCleanupRow[] }>(`/projects/${projectId}/outputs/retention/cleanup`, {
        method: "POST",
        body: JSON.stringify({ dry_run: dryRun })
      });
      setCleanupRows(response.outputs);
      const report = await api<{ outputs: OutputRetentionRow[] }>(`/projects/${projectId}/outputs/retention`);
      setRetentionRows(report.outputs);
    });
  }

  async function deliverOutput(output: OutputVideo) {
    await run("Output delivery triggered", async () => {
      await api(`/internal/output-videos/${output.id}/deliver`, {
        method: "POST",
        body: JSON.stringify({ target: output.delivery?.target ?? "drive" })
      });
      await refreshOutputs();
    });
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Clapperboard size={20} />
          <span>AI Video Editor</span>
        </div>
        <nav>
          <a className="active">Projects</a>
          <a>Media</a>
          <a>Plans</a>
          <a>Renders</a>
          <a>Audit</a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Project Console</h1>
            <p>Private Drive media, approved timelines, manual upload outputs.</p>
          </div>
          <div className="topActions">
            <button className="ghost" onClick={() => void refreshStatus()} disabled={!projectId || busy !== null}>
              <RefreshCw size={16} />
              Refresh
            </button>
            <button onClick={() => void renderApproved()} disabled={!projectId || approvedCount < 2 || busy !== null}>
              <Play size={16} />
              Render
            </button>
          </div>
        </header>

        <section className="statusGrid">
          <article className="statusCard">
            <GitBranch size={20} />
            <span>Project</span>
            <strong>{status?.status ?? "Not selected"}</strong>
          </article>
          <article className="statusCard">
            <FolderSync size={20} />
            <span>Media</span>
            <strong>{status?.media_count ?? 0} assets</strong>
          </article>
          <article className="statusCard">
            <ShieldCheck size={20} />
            <span>Plans</span>
            <strong>{approvedCount} approved</strong>
          </article>
          <article className="statusCard">
            <FileVideo size={20} />
            <span>Renders</span>
            <strong>{status?.render_jobs.length ?? 0} jobs</strong>
          </article>
        </section>

        <section className="controlGrid">
          <div className="panel setupPanel">
            <div className="panelHeader">
              <h2>Setup</h2>
              {busy ? <Loader2 className="spin" size={18} /> : null}
            </div>
            <label>
              API base URL
              <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
            </label>
            <label>
              Bearer token
              <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} type="password" />
            </label>
            <div className="splitFields">
              <label>
                Project name
                <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
              </label>
              <button onClick={() => void createProject()} disabled={busy !== null}>
                New
              </button>
            </div>
            <label>
              Project ID
              <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
            </label>
            <label>
              Drive folder URL
              <input value={folderUrl} onChange={(event) => setFolderUrl(event.target.value)} />
            </label>
            <div className="buttonRow">
              <button className="ghost" onClick={() => void connectDrive()} disabled={!projectId || busy !== null}>
                Connect
              </button>
              <button className="ghost" onClick={() => void syncDrive()} disabled={!projectId || busy !== null}>
                Sync
              </button>
              <button className="ghost" onClick={() => void analyze()} disabled={!projectId || busy !== null}>
                Analyze
              </button>
              <button className="ghost" onClick={() => void refreshAnalysis()} disabled={!projectId || busy !== null}>
                Analysis
              </button>
            </div>
          </div>

          <div className="panel reviewPanel">
            <div className="panelHeader">
              <h2>Plan Review</h2>
              <div className="buttonRow compact">
                <button className="ghost" onClick={() => void refreshPlans()} disabled={!projectId || busy !== null}>
                  Load
                </button>
                <button className="ghost" onClick={() => void regenerate()} disabled={!projectId || busy !== null}>
                  Regenerate
                </button>
              </div>
            </div>
            <div className="planList">
              {plans.map((plan) => (
                <article className="planCard" key={plan.id}>
                  <div className="planTopline">
                    <div>
                      <strong>{variantLabel(plan.variant)}</strong>
                      <span>{clipCount(plan.plan)} clips</span>
                    </div>
                    <span className={`pill ${plan.status}`}>{plan.status}</span>
                  </div>
                  <div className="planMeta">
                    <span>{Math.round(plan.confidence_score * 100)}% confidence</span>
                    <span>
                      {plan.plan.export?.width}x{plan.plan.export?.height}
                    </span>
                    <span>{plan.plan.export?.fps ?? 30} fps</span>
                  </div>
                  <p>{plan.plan.strategy?.hook ?? "Timeline strategy pending."}</p>
                  <textarea
                    value={reviewNotes[plan.id] ?? ""}
                    onChange={(event) => setReviewNotes((current) => ({ ...current, [plan.id]: event.target.value }))}
                    placeholder="Review notes"
                  />
                  <div className="buttonRow">
                    <button className="approve" onClick={() => void approve(plan.id)} disabled={busy !== null}>
                      <CheckCircle2 size={16} />
                      Approve
                    </button>
                    <button className="reject" onClick={() => void reject(plan.id)} disabled={busy !== null}>
                      <XCircle size={16} />
                      Reject
                    </button>
                  </div>
                </article>
              ))}
              {plans.length === 0 ? <div className="emptyState">No plans loaded</div> : null}
            </div>
          </div>
        </section>

        <section className="bottomGrid">
          <div className="panel">
            <div className="panelHeader">
              <h2>Analysis</h2>
              <span className="muted">{latestAnalysis?.provider ?? "No provider"}</span>
            </div>
            <div className="analysisList">
              {latestAnalysis ? (
                <>
                  <div className="analysisMetric">
                    <span>Scenes</span>
                    <strong>{latestAnalysis.result.summary?.scene_count ?? 0}</strong>
                  </div>
                  <div className="analysisMetric">
                    <span>Orientation</span>
                    <strong>{latestAnalysis.result.summary?.primary_orientation ?? "unknown"}</strong>
                  </div>
                  <div className="analysisMetric">
                    <span>Audio</span>
                    <strong>{latestAnalysis.result.summary?.audio_quality ?? "unknown"}</strong>
                  </div>
                  <div className="analysisMetric">
                    <span>Avg score</span>
                    <strong>{Math.round((latestAnalysis.result.summary?.average_highlight_score ?? 0) * 100)}%</strong>
                  </div>
                </>
              ) : (
                <div className="emptyState">No analysis</div>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panelHeader">
              <h2>Render Jobs</h2>
              <span className="muted">{draftCount} drafts</span>
            </div>
            <div className="jobTable">
              {(status?.render_jobs ?? []).map((job) => (
                <div className="jobRow" key={job.id}>
                  <span>{variantLabel(job.variant)}</span>
                  <span className={`pill ${job.status}`}>{job.status}</span>
                </div>
              ))}
              {status?.render_jobs.length === 0 || !status ? <div className="emptyState">No render jobs</div> : null}
            </div>
          </div>

          <div className="panel">
            <div className="panelHeader">
              <h2>Outputs</h2>
              <div className="buttonRow compact">
                <button className="ghost" onClick={() => void loadOutputs()} disabled={!projectId || busy !== null}>
                  Load
                </button>
                <button
                  className="ghost"
                  onClick={() => void loadRetentionReport()}
                  disabled={!projectId || busy !== null}
                >
                  Retention
                </button>
                <button
                  className="ghost"
                  onClick={() => void runRetentionCleanup(true)}
                  disabled={!projectId || busy !== null}
                >
                  Preview cleanup
                </button>
                <button
                  className="reject"
                  onClick={() => void runRetentionCleanup(false)}
                  disabled={!projectId || busy !== null}
                >
                  Run cleanup
                </button>
              </div>
            </div>
            <div className="outputList">
              {outputs.map((output) => {
                const retention = retentionSummary(output);
                const cleanup = cleanupSummary(output);
                return (
                  <div className="outputRow" key={output.id}>
                    <strong>{variantLabel(output.variant)}</strong>
                    <span>
                      {output.width}x{output.height} · {output.duration_seconds}s
                    </span>
                    <span className={`pill ${output.validation?.status ?? "pending"}`}>
                      {output.validation?.status ?? "pending validation"}
                    </span>
                    <span className={`pill ${output.delivery?.status ?? "private_staging"}`}>
                      {output.delivery?.target ?? "delivery"} · {output.delivery?.status ?? "private staging"}
                    </span>
                    {retention ? <span className="outputRetention">{retention}</span> : null}
                    {cleanup ? <span className="outputRetention">{cleanup}</span> : null}
                    {output.delivery?.status === "failed" && output.delivery.details?.details?.error ? (
                      <span className="outputError">{output.delivery.details.details.error}</span>
                    ) : null}
                    <button
                      className="ghost"
                      onClick={() => void deliverOutput(output)}
                      disabled={busy !== null || output.delivery?.status === "delivered"}
                    >
                      <UploadCloud size={16} />
                      Deliver
                    </button>
                  </div>
                );
              })}
              {outputs.length === 0 ? <div className="emptyState">No outputs</div> : null}
            </div>
            {retentionRows.length > 0 ? (
              <div className="retentionList">
                {retentionRows.map((row) => (
                  <div className="retentionRow" key={row.id}>
                    <span>{variantLabel(row.variant)}</span>
                    <span className={`pill ${row.retention_due ? "failed" : "succeeded"}`}>
                      {row.retention_due ? "due" : `${row.days_until_delete ?? "n/a"}d left`}
                    </span>
                    <span>{row.cleanup_status ? `cleanup ${row.cleanup_status}` : row.target}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {cleanupRows.length > 0 ? (
              <div className="retentionList">
                {cleanupRows.map((row) => (
                  <div className="retentionRow" key={`${row.id}-${row.cleanup.status}`}>
                    <span>{variantLabel(row.variant)}</span>
                    <span className={`pill ${row.cleanup.status === "deleted" ? "succeeded" : "queued"}`}>
                      {row.cleanup.status}
                    </span>
                    <span>{row.cleanup.reason ?? row.target}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="panel">
            <div className="panelHeader">
              <h2>Activity</h2>
              <span className="muted">{busy ?? "Idle"}</span>
            </div>
            <div className="logList">
              {log.map((entry, index) => (
                <div className={`logRow ${entry.tone}`} key={`${entry.message}-${index}`}>
                  {entry.message}
                </div>
              ))}
              {log.length === 0 ? <div className="emptyState">No activity</div> : null}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
