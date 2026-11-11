import { useState } from "react";
import { FileAudio, FileText, Upload, Video } from "lucide-react";
import { apiFetch } from "../lib/api";
import type { ProjectPayload } from "../types";

export function ImportPanel({ onImported }: { onImported: (project: ProjectPayload) => void }) {
  const [lyrics, setLyrics] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [video, setVideo] = useState<File | null>(null);
  const [legacy, setLegacy] = useState(false);
  const [preserve, setPreserve] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (!lyrics) return;
    const form = new FormData();
    form.append("lyrics", lyrics);
    if (audio) form.append("audio", audio);
    if (video) form.append("video", video);
    form.append("legacy_parentheses", String(legacy));
    form.append("preserve_ass_timing", String(preserve));
    setBusy(true);
    setError("");
    try {
      let project = await apiFetch<ProjectPayload>("/api/import", { method: "POST", body: form });
      if (audio || video) project = await apiFetch<ProjectPayload>("/api/prepare", { method: "POST" });
      onImported(project);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="import-workspace">
      <div className="import-card">
        <span className="eyebrow">Karaoke Studio</span>
        <h1>新建项目</h1>
        <div className="drop-grid">
          <label className={lyrics ? "file-drop selected" : "file-drop"}><FileText /><strong>{lyrics?.name ?? "歌词"}</strong><span>TXT · LRC · ASS</span><input aria-label="歌词文件" type="file" accept=".txt,.lrc,.ass" onChange={(event) => setLyrics(event.target.files?.[0] ?? null)} /></label>
          <label className={video ? "file-drop selected" : "file-drop"}><Video /><strong>{video?.name ?? "视频"}</strong><input aria-label="视频文件" type="file" accept="video/*" onChange={(event) => setVideo(event.target.files?.[0] ?? null)} /></label>
          <label className={audio ? "file-drop selected" : "file-drop"}><FileAudio /><strong>{audio?.name ?? "独立音轨（可选）"}</strong><input aria-label="音轨文件" type="file" accept="audio/*,video/*" onChange={(event) => setAudio(event.target.files?.[0] ?? null)} /></label>
        </div>
        <details><summary>导入选项</summary><label className="check-row"><input type="checkbox" checked={legacy} onChange={(event) => setLegacy(event.target.checked)} /> 识别 漢字(かんじ) 注音</label>
        <label className="check-row"><input type="checkbox" checked={preserve} onChange={(event) => setPreserve(event.target.checked)} /> 保留 ASS 时间</label></details>
        {error && <div className="error-banner">{error}</div>}
        <button className="primary import-button" disabled={!lyrics || busy} onClick={submit}><Upload size={16} />{busy ? "正在本地导入……" : "导入项目"}</button>
      </div>
    </main>
  );
}
