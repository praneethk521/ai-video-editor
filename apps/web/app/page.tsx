"use client";

import {
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Circle,
  Clapperboard,
  Download,
  FileVideo,
  FolderSync,
  Gauge,
  GitBranch,
  Loader2,
  Play,
  Pin,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  UploadCloud,
  UserPlus,
  Users,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
  selection?: {
    method?: string;
    target_seconds: number;
    duration_seconds: number;
    decisions: Array<{
      asset_id: string;
      status: string;
      reasons: string[];
      score: number;
      alternative_to?: string;
      start?: number;
      duration?: number;
      pinned?: boolean;
      story_beat?: string;
    }>;
  };
  soundtrack?: {
    mode: "latest" | "manual" | "none";
    asset_id?: string | null;
    filename?: string | null;
  };
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

type MediaAsset = {
  id: string;
  filename: string;
  mime_type: string;
  duration_seconds: number;
  orientation: string;
};

type DecisionEdit = {
  asset_id: string;
  selected: boolean;
  pinned: boolean;
  start: number;
  duration: number;
};

type PhotosStatus = {
  configured: boolean;
  status: string;
  missing?: string[];
  picker_url?: string;
  selected_count?: number;
  processed_count?: number;
  imported_count?: number;
  skipped_count?: number;
  error?: string;
  poll_after_seconds?: number;
};

type TimelinePlan = {
  id: string;
  variant: string;
  status: string;
  confidence_score: number;
  plan: TimelinePlanBody;
  review_notes?: string | null;
};

type PipelineStep = {
  id: string;
  label: string;
  state: "pending" | "current" | "complete" | "failed";
  detail: string;
};

type ProjectPipeline = {
  current_step: string;
  next_action: string;
  steps: PipelineStep[];
};

const pipelineIcons = {
  import: FolderSync,
  analyze: Gauge,
  curate: GitBranch,
  review: ShieldCheck,
  render: Clapperboard,
  ready: FileVideo
};

const emptyPipeline: ProjectPipeline = {
  current_step: "import",
  next_action: "Select or create a project",
  steps: [
    { id: "import", label: "Import", state: "pending", detail: "Waiting for a project" },
    { id: "analyze", label: "Analyze", state: "pending", detail: "Pending" },
    { id: "curate", label: "Curate", state: "pending", detail: "Pending" },
    { id: "review", label: "Review", state: "pending", detail: "Pending" },
    { id: "render", label: "Render", state: "pending", detail: "Pending" },
    { id: "ready", label: "Ready", state: "pending", detail: "Pending" }
  ]
};

type ProjectStatus = {
  project_id: string;
  status: string;
  role: ProjectRole;
  media_count: number;
  render_jobs: Array<{ id: string; variant: string; status: string }>;
  pipeline: ProjectPipeline;
};

type OutputVideo = {
  id: string;
  variant: string;
  width: number;
  height: number;
  duration_seconds: number;
  file_size_bytes: number;
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
      asset_count?: number;
      review_count?: number;
      scene_count?: number;
      primary_orientation?: string;
      average_highlight_score?: number;
      audio_quality?: string;
    };
    asset_features?: Array<{ asset_id: string }>;
  };
};

type UsageMetric = {
  metric: string;
  label: string;
  unit: "bytes" | "cents" | "requests" | "jobs" | "attempts";
  used: number;
  limit: number;
  remaining: number;
};

type ProjectUsage = {
  project_id: string;
  window_start: string;
  window_end: string;
  metrics: UsageMetric[];
  active_delivered_storage_bytes: number;
  active_delivered_output_count: number;
};

type LogEntry = {
  tone: "ok" | "warn" | "error";
  message: string;
};

type ProjectRole = "viewer" | "reviewer" | "operator" | "owner" | "admin";
type MembershipRole = Exclude<ProjectRole, "admin">;

type ProjectMembership = {
  id: string;
  principal_type: "user" | "team";
  principal_id: string;
  principal_name: string;
  role: MembershipRole;
};

type Team = {
  id: string;
  name: string;
  role: ProjectRole;
};

type TeamMember = {
  id: string;
  user_id: string;
  email: string;
  role: MembershipRole;
};

const defaultApiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const roleRanks: Record<ProjectRole, number> = {
  viewer: 10,
  reviewer: 20,
  operator: 30,
  owner: 40,
  admin: 50
};
const membershipRoleOptions: MembershipRole[] = ["owner", "operator", "reviewer", "viewer"];

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

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
}

function formatUsageValue(value: number, unit: UsageMetric["unit"]) {
  if (unit === "bytes") return formatBytes(value);
  if (unit === "cents") return `$${(value / 100).toFixed(2)}`;
  return value.toLocaleString();
}

export default function Page() {
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [apiToken, setApiToken] = useState("");
  const [projectRole, setProjectRole] = useState<ProjectRole>("owner");
  const [projectName, setProjectName] = useState("Launch video");
  const [folderUrl, setFolderUrl] = useState("https://drive.google.com/drive/folders/private-folder-id");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [plans, setPlans] = useState<TimelinePlan[]>([]);
  const [media, setMedia] = useState<MediaAsset[]>([]);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [planEdits, setPlanEdits] = useState<Record<string, DecisionEdit[]>>({});
  const thumbnailUrls = useRef<Record<string, string>>({});
  const [landscapeTarget, setLandscapeTarget] = useState(90);
  const [portraitTarget, setPortraitTarget] = useState(30);
  const [outputs, setOutputs] = useState<OutputVideo[]>([]);
  const [retentionRows, setRetentionRows] = useState<OutputRetentionRow[]>([]);
  const [cleanupRows, setCleanupRows] = useState<OutputCleanupRow[]>([]);
  const [analysisResults, setAnalysisResults] = useState<AnalysisResult[]>([]);
  const [usage, setUsage] = useState<ProjectUsage | null>(null);
  const [projectMembers, setProjectMembers] = useState<ProjectMembership[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [principalType, setPrincipalType] = useState<"user" | "team">("user");
  const [principalId, setPrincipalId] = useState("");
  const [membershipRole, setMembershipRole] = useState<MembershipRole>("viewer");
  const [newTeamName, setNewTeamName] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [teamUserId, setTeamUserId] = useState("");
  const [teamMemberRole, setTeamMemberRole] = useState<MembershipRole>("viewer");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState("");
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const previewUrls = useRef<Record<string, string>>({});
  const [photos, setPhotos] = useState<PhotosStatus | null>(null);
  const [photosConsent, setPhotosConsent] = useState(false);
  const [photosAuthUrl, setPhotosAuthUrl] = useState("");
  const photosPaused = useRef(true);
  const photosContext = useRef(0);

  useEffect(() => {
    photosContext.current += 1;
    photosPaused.current = true;
    setPhotos(null);
    setPhotosAuthUrl("");
    setPhotosConsent(false);
    return () => { photosContext.current += 1; photosPaused.current = true; };
  }, [projectId, apiToken, apiBase]);

  useEffect(() => {
    if (photos?.status !== "selecting" || photos.error || busy) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const result = await api<PhotosStatus>(`/projects/${projectId}/photos/poll`, { method: "POST" });
        if (!cancelled) setPhotos(result);
      } catch {
        if (!cancelled) setPhotos((value) => value ? { ...value, error: "Photos polling stopped; refresh or retry." } : value);
      }
    }, Math.max(1, photos.poll_after_seconds ?? 5) * 1000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [photos, busy, projectId, apiToken, apiBase]);

  useEffect(() => {
    const existingProject = new URLSearchParams(window.location.search).get("project");
    if (existingProject) setProjectId(existingProject);
  }, []);

  useEffect(() => {
    return () => {
      Object.values(previewUrls.current).forEach((url) => URL.revokeObjectURL(url));
      previewUrls.current = {};
      Object.values(thumbnailUrls.current).forEach((url) => URL.revokeObjectURL(url));
      thumbnailUrls.current = {};
    };
  }, [projectId, apiToken, apiBase]);

  useEffect(() => {
    setPreviews({});
    setThumbnails({});
    setMedia([]);
    setPlanEdits({});
  }, [projectId, apiToken, apiBase]);

  useEffect(() => {
    if (!projectId || !apiToken || status?.status !== "rendering") return;
    let cancelled = false;
    let pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return;
      pending = true;
      try {
        const next = await api<ProjectStatus>(`/projects/${projectId}/status`);
        if (cancelled) return;
        setStatus(next);
        if (next.status !== "rendering") {
          const response = await api<{ outputs: OutputVideo[] }>(`/projects/${projectId}/outputs`);
          if (!cancelled) setOutputs(response.outputs);
        }
      } catch (error) {
        if (!cancelled) pushLog({ tone: "error", message: String(error) });
      } finally {
        pending = false;
      }
    }, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [projectId, apiToken, apiBase, status?.status]);

  const approvedCount = useMemo(() => plans.filter((plan) => plan.status === "approved").length, [plans]);
  const draftCount = useMemo(() => plans.filter((plan) => plan.status === "draft").length, [plans]);
  const mediaById = useMemo(() => Object.fromEntries(media.map((asset) => [asset.id, asset])), [media]);
  const latestAnalysis = analysisResults[0];
  const canView = allowsRole(projectRole, "viewer");
  const canReview = allowsRole(projectRole, "reviewer");
  const canOperate = allowsRole(projectRole, "operator");
  const canOwn = allowsRole(projectRole, "owner");

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
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
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
    setProjectRole(nextStatus.role);
  }

  async function refreshUsage(targetProjectId = projectId) {
    if (!targetProjectId || !canOperate) return;
    const response = await api<ProjectUsage>(`/projects/${targetProjectId}/usage`);
    setUsage(response);
  }

  async function loadPhotos(targetProjectId = projectId) {
    if (!targetProjectId || !canView) return;
    setPhotos(await api<PhotosStatus>(`/projects/${targetProjectId}/photos`));
  }

  async function refreshOverview() {
    await run("Project overview refreshed", async () => {
      await Promise.all([refreshStatus(), refreshUsage(), refreshPlans(), refreshMedia(), refreshOutputs(), loadPhotos()]);
    });
  }

  async function refreshPhotos() {
    await run("Google Photos status refreshed", async () => {
      await loadPhotos();
    });
  }

  async function connectPhotos() {
    if (!photosConsent) return;
    await run("Google Photos authorization ready", async () => {
      const result = await api<{ authorization_url: string }>(`/projects/${projectId}/photos/connect`, { method: "POST" });
      setPhotosAuthUrl(result.authorization_url);
      setPhotos(await api<PhotosStatus>(`/projects/${projectId}/photos`));
    });
  }

  async function photosAction(action: string) {
    await run(`Google Photos: ${action}`, async () => {
      const result = await api<PhotosStatus>(`/projects/${projectId}/photos/${action}`, { method: "POST" });
      setPhotos(result);
      setPhotosAuthUrl("");
      if (result.error) throw new Error(result.error);
    });
  }

  async function importPhotos() {
    const context = photosContext.current;
    photosPaused.current = false;
    await run("Google Photos import stopped", async () => {
      while (!photosPaused.current && photosContext.current === context) {
        const result = await api<PhotosStatus>(`/projects/${projectId}/photos/import-next`, { method: "POST" });
        if (photosContext.current !== context) return;
        setPhotos(result);
        if (result.error) throw new Error(result.error);
        if (result.status === "complete") break;
      }
      if (photosContext.current === context) await Promise.all([refreshStatus(), refreshPlans()]);
    });
  }

  async function refreshPlans(targetProjectId = projectId) {
    if (!targetProjectId) return;
    const response = await api<{ plans: TimelinePlan[] }>(`/projects/${targetProjectId}/plans`);
    setPlans(response.plans);
    setReviewNotes(Object.fromEntries(response.plans.map((plan) => [plan.id, plan.review_notes ?? ""])));
    setPlanEdits(Object.fromEntries(response.plans.map((plan) => [plan.id, (plan.plan.selection?.decisions ?? []).map((decision) => {
      const clip = plan.plan.tracks?.find((track) => track.type === "video")?.clips.find(
        (candidate) => candidate.asset_id === decision.asset_id
      );
      return {
        asset_id: decision.asset_id,
        selected: decision.status === "selected",
        pinned: decision.pinned ?? false,
        start: decision.start ?? clip?.start ?? 0,
        duration: decision.duration ?? (clip ? clip.end - clip.start : 3)
      };
    })])));
  }

  async function refreshMedia(targetProjectId = projectId) {
    if (!targetProjectId) return;
    const response = await api<{ media: MediaAsset[] }>(`/projects/${targetProjectId}/media`);
    setMedia(response.media);
    const missing = response.media.filter((asset) => !asset.mime_type.startsWith("audio/") && !thumbnailUrls.current[asset.id]);
    for (let offset = 0; offset < missing.length; offset += 4) {
      await Promise.all(missing.slice(offset, offset + 4).map(async (asset) => {
        const response = await fetch(
          `${apiBase.replace(/\/$/, "")}/projects/${targetProjectId}/media/${asset.id}/thumbnail`,
          { headers: { Authorization: `Bearer ${apiToken}` } }
        );
        if (!response.ok) return;
        thumbnailUrls.current[asset.id] = URL.createObjectURL(await response.blob());
      }));
      setThumbnails({ ...thumbnailUrls.current });
    }
  }

  function updateDecision(planId: string, assetId: string, patch: Partial<DecisionEdit>) {
    setPlanEdits((current) => ({
      ...current,
      [planId]: (current[planId] ?? []).map((decision) =>
        decision.asset_id === assetId ? { ...decision, ...patch } : decision
      )
    }));
  }

  function moveDecision(planId: string, assetId: string, offset: -1 | 1) {
    setPlanEdits((current) => {
      const decisions = [...(current[planId] ?? [])];
      const index = decisions.findIndex((decision) => decision.asset_id === assetId);
      const target = index + offset;
      if (index < 0 || target < 0 || target >= decisions.length) return current;
      [decisions[index], decisions[target]] = [decisions[target], decisions[index]];
      return { ...current, [planId]: decisions };
    });
  }

  async function savePlan(planId: string) {
    await run("Selection review saved", async () => {
      await api(`/projects/${projectId}/plans/${planId}`, {
        method: "PATCH",
        body: JSON.stringify({ decisions: planEdits[planId], notes: reviewNotes[planId] || null })
      });
      await Promise.all([refreshPlans(), refreshStatus()]);
    });
  }

  async function updateSoundtrack(planId: string, value: string) {
    await run("Soundtrack updated", async () => {
      const mode = value === "latest" || value === "none" ? value : "manual";
      await api(`/projects/${projectId}/plans/${planId}/soundtrack`, {
        method: "PUT",
        body: JSON.stringify({ mode, asset_id: mode === "manual" ? value : null })
      });
      await Promise.all([refreshPlans(), refreshStatus()]);
    });
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
      setStatus({
        project_id: project.id,
        status: project.status,
        role: "owner",
        media_count: 0,
        render_jobs: [],
        pipeline: { ...emptyPipeline, next_action: "Import photos and videos", steps: emptyPipeline.steps.map((step, index) => ({
          ...step,
          state: index === 0 ? "current" : "pending"
        })) }
      });
      setProjectRole("owner");
      setPlans([]);
      setOutputs([]);
      setRetentionRows([]);
      setCleanupRows([]);
      setAnalysisResults([]);
      setUsage(null);
      setProjectMembers([]);
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

  async function uploadFiles() {
    await run("Media uploaded and scanned", async () => {
      for (let index = 0; index < selectedFiles.length; index++) {
        setUploadProgress(`${index + 1} / ${selectedFiles.length}: ${selectedFiles[index].name}`);
        const body = new FormData();
        body.append("file", selectedFiles[index]);
        await api(`/projects/${projectId}/upload`, { method: "POST", body });
        setSelectedFiles((current) => current.filter((file) => file !== selectedFiles[index]));
        await refreshStatus();
      }
      setUploadProgress("");
    });
  }

  async function previewOutput(output: OutputVideo) {
    await run("Video ready", async () => {
      if (!apiToken.trim()) throw new Error("API token is required");
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/projects/${projectId}/outputs/${output.id}/download`, {
        headers: { Authorization: `Bearer ${apiToken}` }
      });
      if (!response.ok) throw new Error(await response.text());
      const url = URL.createObjectURL(await response.blob());
      if (previewUrls.current[output.id]) URL.revokeObjectURL(previewUrls.current[output.id]);
      previewUrls.current[output.id] = url;
      setPreviews({ ...previewUrls.current });
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
      await refreshUsage();
    });
  }

  async function regenerate() {
    await run("Plans regenerated", async () => {
      await api(`/projects/${projectId}/plans/regenerate`, {
        method: "POST",
        body: JSON.stringify({ variants: ["youtube_16x9", "shorts_9x16"], notes: "Regenerated from dashboard review.",
          landscape_target_seconds: landscapeTarget, portrait_target_seconds: portraitTarget })
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
      await refreshUsage();
    });
  }

  async function loadOutputs() {
    await run("Outputs loaded", async () => {
      await refreshOutputs();
      await refreshUsage();
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
      await api(`/projects/${projectId}/outputs/${output.id}/deliver`, {
        method: "POST",
        body: JSON.stringify({ target: output.delivery?.target ?? "drive" })
      });
      await refreshOutputs();
      await refreshUsage();
    });
  }

  async function loadAccess() {
    await run("Access loaded", async () => {
      const [projectResponse, teamsResponse] = await Promise.all([
        api<{ members: ProjectMembership[] }>(`/projects/${projectId}/members`),
        api<{ teams: Team[] }>("/teams")
      ]);
      setProjectMembers(projectResponse.members);
      setTeams(teamsResponse.teams);
    });
  }

  async function grantProjectAccess() {
    await run("Project access updated", async () => {
      const path = principalType === "user"
        ? `/projects/${projectId}/members/users`
        : `/projects/${projectId}/members/teams/${principalId}`;
      const body = principalType === "user"
        ? { email: principalId.trim().toLowerCase(), role: membershipRole }
        : { role: membershipRole };
      await api(path, {
        method: "PUT",
        body: JSON.stringify(body)
      });
      setPrincipalId("");
      const response = await api<{ members: ProjectMembership[] }>(`/projects/${projectId}/members`);
      setProjectMembers(response.members);
    });
  }

  async function revokeProjectAccess(member: ProjectMembership) {
    await run("Project access removed", async () => {
      const principalPath = member.principal_type === "user" ? "users" : "teams";
      await api(`/projects/${projectId}/members/${principalPath}/${member.principal_id}`, { method: "DELETE" });
      setProjectMembers((current) => current.filter((row) => row.id !== member.id));
    });
  }

  async function createTeam() {
    await run("Team created", async () => {
      const team = await api<Team>("/teams", { method: "POST", body: JSON.stringify({ name: newTeamName }) });
      setNewTeamName("");
      setSelectedTeamId(team.id);
      setTeamMembers([]);
      const response = await api<{ teams: Team[] }>("/teams");
      setTeams(response.teams);
    });
  }

  async function loadTeamMembers(targetTeamId = selectedTeamId) {
    if (!targetTeamId) return;
    await run("Team members loaded", async () => {
      const response = await api<{ members: TeamMember[] }>(`/teams/${targetTeamId}/members`);
      setTeamMembers(response.members);
    });
  }

  async function grantTeamAccess() {
    await run("Team member updated", async () => {
      await api(`/teams/${selectedTeamId}/members`, {
        method: "PUT",
        body: JSON.stringify({ email: teamUserId.trim().toLowerCase(), role: teamMemberRole })
      });
      setTeamUserId("");
      const response = await api<{ members: TeamMember[] }>(`/teams/${selectedTeamId}/members`);
      setTeamMembers(response.members);
    });
  }

  async function removeTeamMember(member: TeamMember) {
    await run("Team member removed", async () => {
      await api(`/teams/${selectedTeamId}/members/${member.user_id}`, { method: "DELETE" });
      setTeamMembers((current) => current.filter((row) => row.id !== member.id));
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
            <p>Local workspace</p>
          </div>
          <div className="topActions">
            <button className="ghost" onClick={() => void refreshOverview()} disabled={!projectId || busy !== null || !canView}>
              <RefreshCw size={16} />
              Refresh
            </button>
            <button
              onClick={() => void renderApproved()}
              disabled={!projectId || approvedCount < 2 || busy !== null || !canOperate}
            >
              <Play size={16} />
              Render
            </button>
          </div>
        </header>

        <section className="panel pipelinePanel" aria-label="Project pipeline">
          <div className="pipelineHeader">
            <div>
              <h2>Trip pipeline</h2>
              <p>Media in, finished story out</p>
            </div>
            <div className="pipelineNext">
              <span>Next step</span>
              <strong>{status?.pipeline.next_action ?? emptyPipeline.next_action}</strong>
            </div>
          </div>
          <ol className="pipelineFlow">
            {(status?.pipeline.steps ?? emptyPipeline.steps).map((step, index) => {
              const StageIcon = pipelineIcons[step.id as keyof typeof pipelineIcons] ?? Circle;
              return (
                <li
                  className={`pipelineStep ${step.state}`}
                  key={step.id}
                  aria-current={status?.pipeline.current_step === step.id ? "step" : undefined}
                >
                  <div className="pipelineStageTop">
                    <span className="pipelineStageIcon" aria-hidden="true"><StageIcon size={20} /></span>
                    <span className="pipelineStageNumber">{String(index + 1).padStart(2, "0")}</span>
                  </div>
                  <strong>{step.label}</strong>
                  <span className="pipelineDetail">{step.detail}</span>
                  <span className="pipelineState">
                    <span className="pipelineStateIcon" aria-hidden="true">
                      {step.state === "complete" ? <CheckCircle2 size={15} /> :
                        step.state === "failed" ? <XCircle size={15} /> :
                          step.state === "current" ? <Loader2 className="spin" size={15} /> : <Circle size={15} />}
                    </span>
                    {step.state === "current" ? "In progress" : step.state}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>

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

        <section className="panel usagePanel">
          <div className="panelHeader">
            <div className="usageHeading">
              <Gauge size={18} />
              <h2>Daily Usage</h2>
            </div>
            <button className="ghost" onClick={() => void refreshUsage()} disabled={!projectId || busy !== null || !canOperate}>
              <RefreshCw size={15} />
              Refresh
            </button>
          </div>
          <div className="usageGrid">
            {(usage?.metrics ?? []).map((metric) => {
              const percent = metric.limit > 0 ? Math.min((metric.used / metric.limit) * 100, 100) : 0;
              return (
                <div className="usageMetric" key={metric.metric}>
                  <div className="usageMetricTopline">
                    <span>{metric.label}</span>
                    <strong>
                      {formatUsageValue(metric.used, metric.unit)} / {formatUsageValue(metric.limit, metric.unit)}
                    </strong>
                  </div>
                  <div className="usageMeter" role="progressbar" aria-valuenow={metric.used} aria-valuemin={0} aria-valuemax={metric.limit}>
                    <span style={{ width: `${percent}%` }} />
                  </div>
                </div>
              );
            })}
            {usage ? (
              <div className="usageMetric activeStorageMetric">
                <div className="usageMetricTopline">
                  <span>Currently retained outputs</span>
                  <strong>{formatBytes(usage.active_delivered_storage_bytes)}</strong>
                </div>
                <span className="muted">{usage.active_delivered_output_count} private outputs</span>
              </div>
            ) : (
              <div className="emptyState">No usage loaded</div>
            )}
          </div>
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
            <label>
              Project access
              <input value={projectRole} readOnly />
            </label>
            <div className="splitFields">
              <label>
                Project name
                <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
              </label>
              <button onClick={() => void createProject()} disabled={busy !== null}>
                <Plus size={16} />
                New
              </button>
            </div>
            <label>
              Project ID
              <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
            </label>
            <label>
              Google Drive folder URL (optional)
              <input value={folderUrl} onChange={(event) => setFolderUrl(event.target.value)} />
            </label>
            <label>
              Photos, videos, and soundtrack
              <input type="file" multiple accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm,audio/mpeg,audio/wav"
                disabled={!projectId || busy !== null || !canOperate}
                onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))} />
            </label>
            <button onClick={() => void uploadFiles()} disabled={!projectId || !selectedFiles.length || busy !== null || !canOperate}>
              <UploadCloud size={16} /> Upload {selectedFiles.length || ""}
            </button>
            {uploadProgress ? <span role="status" className="muted">{uploadProgress}</span> : null}
            <div className="buttonRow">
              <button className="ghost" onClick={() => void connectDrive()} disabled={!projectId || busy !== null || !canOperate}>
                Connect
              </button>
              <button className="ghost" onClick={() => void syncDrive()} disabled={!projectId || busy !== null || !canOperate}>
                Sync
              </button>
              <button className="ghost" onClick={() => void analyze()} disabled={!projectId || busy !== null || !canOperate}>
                Analyze
              </button>
              <button className="ghost" onClick={() => void refreshAnalysis()} disabled={!projectId || busy !== null || !canView}>
                Analysis
              </button>
            </div>
          </div>

          <div className="panel photosPanel">
            <div className="panelHeader">
              <h2>Google Photos</h2>
              <button className="ghost" onClick={() => void refreshPhotos()} disabled={!projectId || busy !== null || !canOwn}>
                <RefreshCw size={15} /> Status
              </button>
            </div>
            <p className="muted">Choose photos and videos from an album in Google&apos;s Picker. Selected files download to this laptop for local editing.</p>
            {photos?.configured === false ? (
              <div className="emptyState">Local Google OAuth setup required: {(photos.missing ?? []).join(", ")}</div>
            ) : null}
            {photos?.configured !== false && (!photos || ["disconnected", "oauth_failed", "pending_oauth"].includes(photos.status)) ? (
              <>
                <label className="consentRow">
                  <input type="checkbox" checked={photosConsent} onChange={(event) => setPhotosConsent(event.target.checked)} />
                  <span>I consent to this local app downloading only the Google Photos media I select for video editing.</span>
                </label>
                <button onClick={() => void connectPhotos()} disabled={!projectId || !photosConsent || busy !== null || !canOwn}>
                  Connect Google Photos
                </button>
                {photosAuthUrl ? <a className="actionLink" href={photosAuthUrl} target="_blank" rel="noopener noreferrer">Open Google authorization</a> : null}
              </>
            ) : null}
            {photos?.status === "connected" || photos?.status === "complete" ? (
              <button onClick={() => void photosAction("select")} disabled={busy !== null || !canOwn}>Choose album media</button>
            ) : null}
            {photos?.picker_url ? <a className="actionLink" href={`${photos.picker_url}/autoclose`} target="_blank" rel="noopener noreferrer">Open Google Photos Picker</a> : null}
            {photos && ["selecting", "ready", "importing", "complete"].includes(photos.status) ? (
              <div className="photosProgress" role="status">
                <strong>{photos.status.replaceAll("_", " ")}</strong>
                <span>{photos.processed_count ?? 0} processed · {photos.imported_count ?? 0} imported · {photos.skipped_count ?? 0} skipped</span>
              </div>
            ) : null}
            {photos?.status === "ready" || photos?.status === "importing" ? (
              <div className="buttonRow">
                <button onClick={() => void importPhotos()} disabled={busy !== null || !canOwn}>Import locally</button>
                <button className="ghost" onClick={() => { photosPaused.current = true; }} disabled={busy === null}>Pause</button>
              </div>
            ) : null}
            {photos?.error ? <div className="errorNotice">{photos.error}
              <button className="ghost" onClick={() => void photosAction("skip")} disabled={busy !== null || !canOwn}>Skip failed item</button>
            </div> : null}
            {photos && !["disconnected", "not_configured"].includes(photos.status) ? (
              <div className="buttonRow">
                {photos.picker_url ? <button className="ghost" onClick={() => void photosAction("cancel")} disabled={busy !== null || !canOwn}>Cancel selection</button> : null}
                <button className="reject" onClick={() => void photosAction("disconnect")} disabled={busy !== null || !canOwn}>Disconnect</button>
              </div>
            ) : null}
          </div>

          <div className="panel reviewPanel">
            <div className="panelHeader">
              <h2>Plan Review</h2>
              <div className="buttonRow compact">
                <button className="ghost" onClick={() => void refreshPlans()} disabled={!projectId || busy !== null || !canView}>
                  Load
                </button>
                <button className="ghost" onClick={() => void regenerate()} disabled={!projectId || busy !== null || !canOperate}>
                  Regenerate
                </button>
              </div>
            </div>
            <div className="planList">
              <div className="splitFields">
                <label>Landscape target (seconds)<input type="number" min={15} max={300} value={landscapeTarget}
                  onChange={(event) => setLandscapeTarget(Number(event.target.value))} /></label>
                <label>Vertical target (seconds)<input type="number" min={15} max={60} value={portraitTarget}
                  onChange={(event) => setPortraitTarget(Number(event.target.value))} /></label>
              </div>
              {plans.map((plan) => {
                const edits = planEdits[plan.id] ?? [];
                const soundtrackValue = plan.plan.soundtrack?.mode === "manual"
                  ? plan.plan.soundtrack.asset_id ?? "none"
                  : plan.plan.soundtrack?.mode ?? "none";
                const soundtrackAssets = media.filter((asset) => asset.mime_type.startsWith("audio/"));
                const selectedDuration = edits.filter((item) => item.selected || item.pinned)
                  .reduce((total, item) => total + Number(item.duration || 0), 0);
                return <article className="planCard" key={plan.id}>
                  <div className="planTopline">
                    <div>
                      <strong>{variantLabel(plan.variant)}</strong>
                      <span>{clipCount(plan.plan)} clips</span>
                    </div>
                    <span className={`pill ${plan.status}`}>{plan.status}</span>
                  </div>
                  <div className="planMeta">
                    <span>{plan.plan.selection ? `${plan.plan.selection.duration_seconds}s / ${plan.plan.selection.target_seconds}s target` : `${Math.round(plan.confidence_score * 100)}% confidence`}</span>
                    <span>
                      {plan.plan.export?.width}x{plan.plan.export?.height}
                    </span>
                    <span>{plan.plan.export?.fps ?? 30} fps</span>
                  </div>
                  <p>{plan.plan.strategy?.hook ?? "Timeline strategy pending."}</p>
                  <label className="soundtrackField">
                    Soundtrack
                    <select
                      value={soundtrackValue}
                      onChange={(event) => void updateSoundtrack(plan.id, event.target.value)}
                      disabled={busy !== null || !canReview}
                    >
                      {soundtrackAssets.length > 0 ? <option value="latest">Newest uploaded audio</option> : null}
                      <option value="none">No soundtrack</option>
                      {soundtrackAssets.map((asset) => (
                        <option key={asset.id} value={asset.id}>{asset.filename}</option>
                      ))}
                    </select>
                  </label>
                  {plan.plan.selection && plan.status !== "rejected" ? <details className="selectionReview" open={plan.status === "draft"}>
                    <summary>Review media ({edits.filter((item) => item.selected || item.pinned).length} selected · {selectedDuration.toFixed(1)}s)</summary>
                    <div className="selectionGrid">{edits.map((edit, decisionIndex) => {
                      const decision = plan.plan.selection?.decisions.find((item) => item.asset_id === edit.asset_id);
                      if (!decision) return null;
                      const asset = mediaById[decision.asset_id];
                      const isImage = asset?.mime_type.startsWith("image/") ?? false;
                      return <article className={`selectionItem ${edit.selected || edit.pinned ? "included" : "excluded"}`} key={decision.asset_id}>
                        <div className="selectionThumb">
                          {thumbnails[decision.asset_id]
                            ? <img src={thumbnails[decision.asset_id]} alt="" />
                            : <div className="thumbnailPlaceholder"><FileVideo size={22} /></div>}
                          {asset?.mime_type.startsWith("video/") ? <span className="mediaType">Video</span> : null}
                        </div>
                        <div className="selectionBody">
                          <div className="selectionTitle">
                            <strong>{asset?.filename ?? decision.asset_id}</strong>
                            <span>{Math.round(decision.score * 100)}%</span>
                          </div>
                          <span className="decisionReasons">{decision.reasons.map((reason) => reason.replaceAll("_", " ")).join(" · ")}</span>
                          {decision.story_beat ? <span className="storyBeat">{decision.story_beat}</span> : null}
                          {decision.alternative_to ? <span className="duplicateNote">
                            Alternative to {mediaById[decision.alternative_to]?.filename ?? "another similar item"}
                          </span> : null}
                          <div className="decisionToggles">
                            <label><input type="checkbox" checked={edit.selected || edit.pinned}
                              onChange={(event) => updateDecision(plan.id, decision.asset_id, { selected: event.target.checked, pinned: event.target.checked ? edit.pinned : false })} /> Include</label>
                            <label><input type="checkbox" checked={edit.pinned}
                              onChange={(event) => updateDecision(plan.id, decision.asset_id, { pinned: event.target.checked, selected: event.target.checked || edit.selected })} />
                              <Pin size={13} /> Pin</label>
                            <div className="orderControls" aria-label="Clip order">
                              <button className="ghost iconButton" title="Move earlier" aria-label={`Move ${asset?.filename ?? "media"} earlier`}
                                disabled={decisionIndex === 0 || !(edit.selected || edit.pinned)}
                                onClick={() => moveDecision(plan.id, decision.asset_id, -1)}><ArrowUp size={14} /></button>
                              <button className="ghost iconButton" title="Move later" aria-label={`Move ${asset?.filename ?? "media"} later`}
                                disabled={decisionIndex === edits.length - 1 || !(edit.selected || edit.pinned)}
                                onClick={() => moveDecision(plan.id, decision.asset_id, 1)}><ArrowDown size={14} /></button>
                            </div>
                          </div>
                          {edit.selected || edit.pinned ? <div className="trimFields">
                            <label>Start<input type="number" min={0} max={Math.max(0, (asset?.duration_seconds ?? 3) - 0.1)} step={0.1}
                              disabled={isImage} value={edit.start}
                              onChange={(event) => updateDecision(plan.id, decision.asset_id, { start: Number(event.target.value) })} /></label>
                            <label>Seconds<input type="number" min={0.5} max={Math.min(8, asset?.duration_seconds ?? 8)} step={0.5}
                              value={edit.duration}
                              onChange={(event) => updateDecision(plan.id, decision.asset_id, { duration: Number(event.target.value) })} /></label>
                          </div> : null}
                        </div>
                      </article>;
                    })}</div>
                  </details> : plan.plan.selection ? <details>
                    <summary>Selection decisions ({plan.plan.selection.decisions.length})</summary>
                    <ul className="selectionDecisions">{plan.plan.selection.decisions.map((decision, index) => (
                      <li key={decision.asset_id}><strong>Media {index + 1}: {decision.status}</strong>
                        <span>{decision.reasons.map((reason) => reason.replaceAll("_", " ")).join(", ")}</span></li>
                    ))}</ul>
                  </details> : null}
                  <textarea
                    value={reviewNotes[plan.id] ?? ""}
                    onChange={(event) => setReviewNotes((current) => ({ ...current, [plan.id]: event.target.value }))}
                    placeholder="Review notes"
                  />
                  <div className="buttonRow">
                    {plan.plan.selection && plan.status !== "rejected" ? <button className="ghost" onClick={() => void savePlan(plan.id)} disabled={busy !== null || !canReview}>
                      <Save size={16} /> Save review
                    </button> : null}
                    <button className="approve" onClick={() => void approve(plan.id)} disabled={busy !== null || !canReview}>
                      <CheckCircle2 size={16} />
                      Approve
                    </button>
                    <button className="reject" onClick={() => void reject(plan.id)} disabled={busy !== null || !canReview}>
                      <XCircle size={16} />
                      Reject
                    </button>
                  </div>
                </article>
              })}
              {plans.length === 0 ? <div className="emptyState">No plans loaded</div> : null}
            </div>
          </div>
        </section>

        <section className="panel accessPanel">
          <div className="panelHeader">
            <div className="usageHeading">
              <Users size={18} />
              <h2>Access</h2>
            </div>
            <button className="ghost" onClick={() => void loadAccess()} disabled={!projectId || busy !== null || !canOwn}>
              <RefreshCw size={15} />
              Load
            </button>
          </div>
          <div className="accessGrid">
            <div className="accessColumn">
              <h3>Project members</h3>
              <div className="accessForm">
                <select value={principalType} onChange={(event) => setPrincipalType(event.target.value as "user" | "team")}>
                  <option value="user">User</option>
                  <option value="team">Team</option>
                </select>
                {principalType === "user" ? (
                  <input value={principalId} onChange={(event) => setPrincipalId(event.target.value)} placeholder="User email" />
                ) : (
                  <select value={principalId} onChange={(event) => setPrincipalId(event.target.value)}>
                    <option value="">Select team</option>
                    {teams.map((team) => (
                      <option key={team.id} value={team.id}>{team.name}</option>
                    ))}
                  </select>
                )}
                <select value={membershipRole} onChange={(event) => setMembershipRole(event.target.value as MembershipRole)}>
                  {membershipRoleOptions.map((role) => (
                    <option key={role} value={role}>{role}</option>
                  ))}
                </select>
                <button
                  title="Grant project access"
                  onClick={() => void grantProjectAccess()}
                  disabled={!projectId || !principalId.trim() || busy !== null || !canOwn}
                >
                  <UserPlus size={16} />
                  Grant
                </button>
              </div>
              <div className="memberList">
                {projectMembers.map((member) => (
                  <div className="memberRow" key={member.id}>
                    <div>
                      <strong>{member.principal_name}</strong>
                      <span>{member.principal_type}</span>
                    </div>
                    <span className="pill">{member.role}</span>
                    <button
                      className="iconButton reject"
                      title="Remove project access"
                      aria-label={`Remove ${member.principal_name}`}
                      onClick={() => void revokeProjectAccess(member)}
                      disabled={busy !== null || !canOwn}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
                {projectMembers.length === 0 ? <div className="emptyState">No memberships loaded</div> : null}
              </div>
            </div>

            <div className="accessColumn">
              <h3>Teams</h3>
              <div className="teamCreateRow">
                <input value={newTeamName} onChange={(event) => setNewTeamName(event.target.value)} placeholder="Team name" />
                <button title="Create team" onClick={() => void createTeam()} disabled={!newTeamName.trim() || busy !== null}>
                  <Plus size={16} />
                  Create
                </button>
              </div>
              <div className="teamSelectRow">
                <select
                  value={selectedTeamId}
                  onChange={(event) => {
                    setSelectedTeamId(event.target.value);
                    setTeamMembers([]);
                  }}
                >
                  <option value="">Select team</option>
                  {teams.map((team) => (
                    <option key={team.id} value={team.id}>{team.name} ({team.role})</option>
                  ))}
                </select>
                <button
                  className="ghost iconButton"
                  title="Load team members"
                  aria-label="Load team members"
                  onClick={() => void loadTeamMembers()}
                  disabled={!selectedTeamId || busy !== null}
                >
                  <RefreshCw size={15} />
                </button>
              </div>
              <div className="accessForm teamAccessForm">
                <input value={teamUserId} onChange={(event) => setTeamUserId(event.target.value)} placeholder="User email" />
                <select value={teamMemberRole} onChange={(event) => setTeamMemberRole(event.target.value as MembershipRole)}>
                  {membershipRoleOptions.map((role) => (
                    <option key={role} value={role}>{role}</option>
                  ))}
                </select>
                <button
                  title="Add team member"
                  onClick={() => void grantTeamAccess()}
                  disabled={!selectedTeamId || !teamUserId.trim() || busy !== null}
                >
                  <UserPlus size={16} />
                  Add
                </button>
              </div>
              <div className="memberList">
                {teamMembers.map((member) => (
                  <div className="memberRow" key={member.id}>
                    <div>
                      <strong>{member.email}</strong>
                      <span>{member.user_id}</span>
                    </div>
                    <span className="pill">{member.role}</span>
                    <button
                      className="iconButton reject"
                      title="Remove team member"
                      aria-label={`Remove ${member.email}`}
                      onClick={() => void removeTeamMember(member)}
                      disabled={busy !== null}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
                {teamMembers.length === 0 ? <div className="emptyState">No team members loaded</div> : null}
              </div>
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
                    <span>Assets</span>
                    <strong>{latestAnalysis.result.summary?.asset_count ?? latestAnalysis.result.asset_features?.length ?? 0}</strong>
                  </div>
                  <div className="analysisMetric">
                    <span>Scenes</span>
                    <strong>{latestAnalysis.result.summary?.scene_count ?? 0}</strong>
                  </div>
                  <div className="analysisMetric">
                    <span>Review</span>
                    <strong>{latestAnalysis.result.summary?.review_count ?? 0}</strong>
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

          <div className="panel outputPanel">
            <div className="panelHeader">
              <h2>Outputs</h2>
              <div className="buttonRow compact">
                <button className="ghost" onClick={() => void loadOutputs()} disabled={!projectId || busy !== null || !canView}>
                  Load
                </button>
                <button
                  className="ghost"
                  onClick={() => void loadRetentionReport()}
                  disabled={!projectId || busy !== null || !canView}
                >
                  Retention
                </button>
                <button
                  className="ghost"
                  onClick={() => void runRetentionCleanup(true)}
                  disabled={!projectId || busy !== null || !canOperate}
                >
                  Preview cleanup
                </button>
                <button
                  className="reject"
                  onClick={() => void runRetentionCleanup(false)}
                  disabled={!projectId || busy !== null || !canOwn}
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
                    <button className="ghost" onClick={() => void previewOutput(output)}
                      disabled={busy !== null || !canView || output.validation?.status !== "passed"}>
                      <Play size={16} /> Preview
                    </button>
                    {previews[output.id] ? <>
                      <video className="outputPreview" src={previews[output.id]} controls preload="metadata" />
                      <a href={previews[output.id]} download={`${output.variant}.mp4`}><Download size={16} /> Download MP4</a>
                    </> : null}
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
                      disabled={busy !== null || output.delivery?.status === "delivered" || !canOperate}
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

function allowsRole(actual: ProjectRole, required: ProjectRole) {
  return roleRanks[actual] >= roleRanks[required];
}
