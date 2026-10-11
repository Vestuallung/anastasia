import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  CircleStop,
  CloudOff,
  Download,
  FileCheck2,
  Pause,
  Play,
  Redo2,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { AssPreview } from "./components/AssPreview";
import { ImportPanel } from "./components/ImportPanel";
import { Inspector } from "./components/Inspector";
import { Timeline } from "./components/Timeline";
import { apiFetch, apiUrl, getProject, getWaveform, saveReading, saveTiming } from "./lib/api";
import type { ProjectPayload, RubyGroup, WaveformPayload } from "./types";

interface TimingHistory {
  lineId: string;
  before: number[];
  after: number[];
}

type SaveState = "saved" | "saving" | "error";

function App() {
  const [project, setProject] = useState<ProjectPayload | null>(null);
  const [waveform, setWaveform] = useState<WaveformPayload>({ peaks: [], duration_ms: 0 });
  const [selectedId, setSelectedId] = useState("");
  const [currentMs, setCurrentMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(true);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const [jobMessage, setJobMessage] = useState("");
  const [jobId, setJobId] = useState("");
  const [licenseOpen, setLicenseOpen] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [undoStack, setUndoStack] = useState<TimingHistory[]>([]);
  const [redoStack, setRedoStack] = useState<TimingHistory[]>([]);
  const [timingPreview, setTimingPreview] = useState<number[] | null>(null);
  const mediaRef = useRef<HTMLAudioElement>(null);
  const [runtime, setRuntime] = useState<{ device?: string; model_url?: string }>({});

  const load = useCallback(async () => {
    try {
      const [nextProject, nextWaveform] = await Promise.all([getProject(), getWaveform()]);
      setProject(nextProject);
      setWaveform(nextWaveform);
      setSelectedId((value) => value || nextProject.lines[0]?.id || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, []);

  useEffect(() => { void load(); void apiFetch<{ device: string; model_url: string }>("/api/appearance").then(setRuntime).catch(() => {}); }, [load]);

  const selectedIndex = project?.lines.findIndex((line) => line.id === selectedId) ?? -1;
  const selectedLine = selectedIndex >= 0 ? project?.lines[selectedIndex] : undefined;
  const boundaries = project?.effective_boundaries[selectedId] ?? [];
  const editorBoundaries = timingPreview ?? boundaries;
  const durationMs = waveform.duration_ms || project?.audio.duration_ms || 1;
  const lineStart = editorBoundaries[0] ?? 0;
  const lineEnd = editorBoundaries[editorBoundaries.length - 1] ?? durationMs;

  useEffect(() => {
    const media = mediaRef.current;
    if (!media) return;
    const update = () => {
      const milliseconds = Math.round(media.currentTime * 1000);
      setCurrentMs(milliseconds);
      if (loop && boundaries.length && milliseconds >= lineEnd) {
        media.currentTime = lineStart / 1000;
        void media.play();
      }
    };
    const stopped = () => setPlaying(false);
    media.addEventListener("timeupdate", update);
    media.addEventListener("ended", stopped);
    return () => {
      media.removeEventListener("timeupdate", update);
      media.removeEventListener("ended", stopped);
    };
  }, [boundaries.length, lineEnd, lineStart, loop]);

  useEffect(() => {
    if (mediaRef.current) mediaRef.current.playbackRate = playbackRate;
  }, [playbackRate]);

  function selectLine(id: string) {
    setTimingPreview(null);
    setSelectedId(id);
    const start = project?.effective_boundaries[id]?.[0];
    if (start !== undefined && mediaRef.current) {
      mediaRef.current.currentTime = start / 1000;
      setCurrentMs(start);
    }
  }

  function stepLine(direction: number) {
    if (!project?.lines.length) return;
    const index = Math.min(Math.max(0, selectedIndex + direction), project.lines.length - 1);
    selectLine(project.lines[index].id);
  }

  function togglePlayback() {
    const media = mediaRef.current;
    if (!media) return;
    if (media.paused) {
      if (boundaries.length && (media.currentTime * 1000 < lineStart || media.currentTime * 1000 >= lineEnd)) {
        media.currentTime = lineStart / 1000;
      }
      void media.play();
      setPlaying(true);
    } else {
      media.pause();
      setPlaying(false);
    }
  }

  const applyLocalTiming = useCallback((lineId: string, next: number[]) => {
    setProject((value) => value ? {
      ...value,
      updated_at: new Date().toISOString(),
      effective_boundaries: { ...value.effective_boundaries, [lineId]: next },
    } : value);
  }, []);

  async function commitTiming(
    before: number[],
    after: number[],
    kind: "line_shift" | "boundary" | "line_start" | "line_end",
    boundaryIndex?: number,
  ) {
    if (!selectedLine) return;
    applyLocalTiming(selectedLine.id, after);
    setUndoStack((items) => [...items, { lineId: selectedLine.id, before, after }]);
    setRedoStack([]);
    setSaveState("saving");
    try {
      setProject(await saveTiming(selectedLine.id, after, kind, boundaryIndex));
      setSaveState("saved");
    } catch (reason) {
      applyLocalTiming(selectedLine.id, before);
      setSaveState("error");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function replayHistory(history: TimingHistory, direction: "undo" | "redo") {
    const next = direction === "undo" ? history.before : history.after;
    applyLocalTiming(history.lineId, next);
    setSaveState("saving");
    try {
      setProject(await saveTiming(history.lineId, next, "line_shift"));
      setSaveState("saved");
    } catch (reason) {
      setSaveState("error");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function undo() {
    const item = undoStack[undoStack.length - 1];
    if (!item) return;
    setUndoStack((items) => items.slice(0, -1));
    setRedoStack((items) => [...items, item]);
    void replayHistory(item, "undo");
  }

  function redo() {
    const item = redoStack[redoStack.length - 1];
    if (!item) return;
    setRedoStack((items) => items.slice(0, -1));
    setUndoStack((items) => [...items, item]);
    void replayHistory(item, "redo");
  }

  async function updateReading(group: RubyGroup, reading: string, romaji: string) {
    if (!selectedLine) return;
    setSaveState("saving");
    try {
      setProject(await saveReading(selectedLine.id, selectedLine.original, group.span, reading, romaji));
      setSaveState("saved");
    } catch (reason) {
      setSaveState("error");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function restoreRaw() {
    if (!selectedLine) return;
    setSaveState("saving");
    try {
      setProject(await apiFetch(`/api/lines/${selectedLine.id}/restore-timing`, { method: "POST" }));
      setSaveState("saved");
    } catch (reason) {
      setSaveState("error");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function acceptLicense() {
    const form = new FormData();
    form.append("accepted", "true");
    try {
      await apiFetch("/api/model/accept-license", { method: "POST", body: form });
      setLicenseOpen(false);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function startAlignment(allowDownload = false) {
    setJobMessage("正在启动整曲对齐……");
    setError("");
    try {
      const result = await apiFetch<{ job_id: string }>(`/api/jobs/align?allow_download=${allowDownload}`, { method: "POST" });
      setJobId(result.job_id);
      const events = new EventSource(apiUrl(`/api/jobs/${result.job_id}/events`));
      events.onmessage = (event) => {
        const update = JSON.parse(event.data) as { message: string; status: string };
        setJobMessage(update.message);
        if (["completed", "failed", "cancelled"].includes(update.status)) {
          events.close();
          setJobId("");
          if (update.status === "completed") void load();
          if (update.status === "failed") setError(update.message);
        }
      };
      events.onerror = () => events.close();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function cancelAlignment() {
    if (!jobId) {
      setJobMessage("");
      return;
    }
    try {
      await apiFetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
      setJobMessage("已请求取消……");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function downloadAss() {
    try {
      const content = await apiFetch<string>("/api/export.ass");
      const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${project?.title || "karaoke"}.ass`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  if (!project) {
    return <div className="boot-screen"><RefreshCw className="spin" /> <span>{error || "正在打开本地项目……"}</span></div>;
  }
  if (!project.lines.length) return <ImportPanel onImported={(value) => { setProject(value); setSelectedId(value.lines[0]?.id ?? ""); void getWaveform().then(setWaveform); }} />;

  const issueCount = project.issues.length;
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><div><strong>Karaoke Studio</strong><span>本地卡拉 OK 对齐工作台</span></div></div>
        <div className="project-title"><span>{project.title}</span><small>{project.alignment_source === "preserved_ass" ? "使用导入的 ASS 时间" : project.alignment_stale ? "读音已修改 · 需要重新对齐" : "正在使用 Yohane 原始时间"}</small></div>
        <div className="header-actions">
          <span className={`save-state ${saveState}`}>{saveState === "saved" ? <BadgeCheck size={14} /> : saveState === "saving" ? <RefreshCw className="spin" size={14} /> : <TriangleAlert size={14} />}{saveState === "saved" ? "已保存" : saveState === "saving" ? "保存中" : "保存失败"}</span>
          <button onClick={undo} disabled={!undoStack.length} title="撤销时间修改" aria-label="撤销时间修改"><Undo2 size={16} /></button>
          <button onClick={redo} disabled={!redoStack.length} title="重做时间修改" aria-label="重做时间修改"><Redo2 size={16} /></button>
          <button onClick={() => setIssuesOpen((value) => !value)} className={issueCount ? "warning-button" : ""}><FileCheck2 size={16} /> {issueCount} 个问题</button>
          <button onClick={() => void startAlignment(false)} disabled={!project.audio.prepared_path}><RefreshCw size={16} /> 开始对齐</button>
          <button className="primary" onClick={downloadAss} disabled={project.alignment_stale}><Download size={16} /> 导出 ASS</button>
        </div>
      </header>

      {error && <div className="error-banner floating"><TriangleAlert size={16} /><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}
      {jobMessage && <div className="job-banner"><RefreshCw className={jobId ? "spin" : ""} size={14} />{jobMessage}<button onClick={() => void cancelAlignment()} aria-label={jobId ? "取消对齐" : "关闭任务状态"}><CircleStop size={14} /></button></div>}

      <div className="workspace">
        <aside className="lyrics-panel">
          <div className="lyrics-heading"><div><span className="eyebrow">歌词</span><strong>{project.lines.length} 行</strong></div><span>来源 / 读音 / 时间</span></div>
          <div className="lyrics-list">
            {project.lines.map((line, index) => {
              const text = line.display_tokens.map((token) => token.text).join("");
              const hasIssue = project.issues.some((issue) => issue.line_id === line.id);
              return <button key={line.id} className={`lyric-row ${selectedId === line.id ? "active" : ""}`} onClick={() => selectLine(line.id)}>
                {line.paragraph_before > 0 && <span className="paragraph-gap" />}
                <span className="line-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="line-copy"><strong>{text}</strong><small>{line.yohane_input}</small></span>
                <span className={`line-state ${hasIssue ? "warning" : line.state}`} />
              </button>;
            })}
          </div>
          <div className="local-note"><CloudOff size={15} /><span>本地制作流程<br /><small>{runtime.device?.toUpperCase()} · 整曲对齐 · 本地文件</small></span></div>
        </aside>

        <main className="editor-main">
          <AssPreview mediaRef={mediaRef} line={selectedLine} boundaries={editorBoundaries} currentMs={currentMs} hasProjectVideo={Boolean(project.source.video_path)} refreshKey={project.updated_at} />
          <div className="transport">
            <button onClick={() => stepLine(-1)} aria-label="上一句"><ChevronLeft size={18} /></button>
            <button className="play-button" onClick={togglePlayback} aria-label={playing ? "暂停" : "播放当前句"}>{playing ? <Pause size={19} /> : <Play size={19} fill="currentColor" />}</button>
            <button onClick={() => stepLine(1)} aria-label="下一句"><ChevronRight size={18} /></button>
            <span className="time-readout">{(currentMs / 1000).toFixed(2)} <i>/</i> {(durationMs / 1000).toFixed(2)} s</span>
            <label className="loop-toggle"><input type="checkbox" checked={loop} onChange={(event) => setLoop(event.target.checked)} /> 循环播放当前句</label>
            <label className="speed-control">播放速度
              <select aria-label="播放速度" value={playbackRate} onChange={(event) => setPlaybackRate(Number(event.target.value))}>
                {[0.5, 0.75, 1, 1.25, 1.5, 2].map((rate) => <option value={rate} key={rate}>{rate}×</option>)}
              </select>
            </label>
            <div className="transport-spacer" />
            {!project.model.license_accepted_at ? <button className="license-button" onClick={() => setLicenseOpen(true)}>查看并接受模型许可</button> : <button className="text-button" onClick={() => void startAlignment(true)}>下载模型并对齐</button>}
          </div>
          <Timeline line={selectedLine} boundaries={boundaries} peaks={waveform.peaks} durationMs={durationMs} currentMs={currentMs} onSeek={(value) => { if (mediaRef.current) mediaRef.current.currentTime = value / 1000; setCurrentMs(value); }} onPreview={setTimingPreview} onCommit={commitTiming} onRestore={restoreRaw} />
        </main>

        <Inspector project={project} line={selectedLine} boundaries={editorBoundaries} saving={saveState === "saving"} onSaveReading={updateReading} />
      </div>

      <footer className="status-bar"><span><i className="status-dot" />本地会话 127.0.0.1</span><span>16 kHz · 单声道</span><span>{project.model.model_id.split("/").pop()}</span><span className="footer-spacer" /><span>项目格式 v1</span><span>{project.alignment_stale ? "需要重新对齐" : "原始时间已保留"}</span></footer>

      {issuesOpen && <div className="issues-drawer"><div className="drawer-heading"><strong>结构检查报告</strong><button onClick={() => setIssuesOpen(false)}>关闭</button></div>{project.issues.length ? project.issues.map((issue) => <button key={`${issue.line_id}-${issue.code}`} onClick={() => issue.line_id && selectLine(issue.line_id)}><TriangleAlert size={15} /><span><strong>{issue.code}</strong>{issue.message}</span></button>) : <div className="all-clear"><BadgeCheck />歌词结构检查完成。</div>}</div>}

      {licenseOpen && <div className="modal-backdrop" role="presentation" onMouseDown={() => setLicenseOpen(false)}>
        <section className="license-dialog" role="dialog" aria-modal="true" aria-labelledby="model-license-title" onMouseDown={(event) => event.stopPropagation()}>
          <span className="eyebrow">模型下载许可</span>
          <h2 id="model-license-title">请确认强制对齐模型的许可</h2>
          <p>模型 <code>{project.model.model_id}</code> 通过模型下载流程安装。</p>
          <div className="license-notice"><TriangleAlert size={18} /><span>其许可为 <strong>{project.model.license}</strong>。具体使用条款见模型说明与许可页面。</span></div>
          <p>下载前，Karaoke Studio 会记录你的确认、固定模型 ID、revision 和本地快照校验值。</p>
          <a href={runtime.model_url} target="_blank" rel="noreferrer">打开模型说明与许可页面</a>
          <div className="modal-actions"><button onClick={() => setLicenseOpen(false)}>取消</button><button className="primary" onClick={() => void acceptLicense()}>接受 {project.model.license}</button></div>
        </section>
      </div>}
    </div>
  );
}

export default App;
