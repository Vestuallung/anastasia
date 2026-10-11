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
      if (audio) project = await apiFetch<ProjectPayload>("/api/prepare", { method: "POST" });
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
        <span className="eyebrow">新建本地项目</span>
        <h1>导入歌词和音频，在同一处完成对齐与调整。</h1>
        <p>标准假名语法为 <code>他人《ひと》</code>；普通圆括号会保留显示并参与演唱。</p>
        <div className="drop-grid">
          <label className={lyrics ? "file-drop selected" : "file-drop"}><FileText /><strong>{lyrics?.name ?? "选择 TXT、LRC 或 ASS"}</strong><span>歌词与行内假名标注</span><input type="file" accept=".txt,.lrc,.ass" onChange={(event) => setLyrics(event.target.files?.[0] ?? null)} /></label>
          <label className={video ? "file-drop selected" : "file-drop"}><Video /><strong>{video?.name ?? "选择预览视频"}</strong><span>作为字幕实时预览画面</span><input type="file" accept="video/*" onChange={(event) => setVideo(event.target.files?.[0] ?? null)} /></label>
          <label className={audio ? "file-drop selected" : "file-drop"}><FileAudio /><strong>{audio?.name ?? "选择对齐音频"}</strong><span>播放并转换为 16 kHz 单声道</span><input type="file" accept="audio/*,video/*" onChange={(event) => setAudio(event.target.files?.[0] ?? null)} /></label>
        </div>
        <label className="check-row"><input type="checkbox" checked={legacy} onChange={(event) => setLegacy(event.target.checked)} /> 将旧式 漢字(かんじ) 解析为假名标注</label>
        <label className="check-row"><input type="checkbox" checked={preserve} onChange={(event) => setPreserve(event.target.checked)} /> 保留结构有效的 ASS 卡拉 OK 时间</label>
        {error && <div className="error-banner">{error}</div>}
        <button className="primary import-button" disabled={!lyrics || busy} onClick={submit}><Upload size={16} />{busy ? "正在本地导入……" : "导入项目"}</button>
      </div>
    </main>
  );
}
