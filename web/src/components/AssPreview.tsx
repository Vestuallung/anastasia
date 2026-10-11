import { useEffect, useRef, useState } from "react";
import JASSUB from "jassub";
import modernWasmUrl from "jassub/dist/wasm/jassub-worker-modern.wasm?url";
import wasmUrl from "jassub/dist/wasm/jassub-worker.wasm?url";
import workerUrl from "jassub/dist/worker/worker.js?worker&url";
import { Captions, CircleAlert } from "lucide-react";
import backgroundUrl from "../preview-background.mp4?url";
import { apiFetch, apiUrl } from "../lib/api";
import type { LyricLine } from "../types";

interface AssPreviewProps {
  mediaRef: React.RefObject<HTMLAudioElement | null>;
  line?: LyricLine;
  boundaries: number[];
  currentMs: number;
  hasProjectVideo: boolean;
  refreshKey: string;
}

const kanaOnly = /^[ぁ-ゖァ-ヺー]+$/;

export function AssPreview({ mediaRef, line, boundaries, currentMs, hasProjectVideo, refreshKey }: AssPreviewProps) {
  const renderer = useRef<JASSUB | null>(null);
  const backgroundRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "fallback">("loading");

  useEffect(() => {
    let disposed = false;
    let animationFrame = 0;
    async function load() {
      const media = mediaRef.current;
      const background = backgroundRef.current;
      if (!media || !background) return;
      setStatus("loading");
      try {
        if (hasProjectVideo) {
          background.currentTime = media.currentTime;
        } else {
          await background.play();
        }
        const content = await apiFetch<string>(`/api/preview.ass?v=${encodeURIComponent(refreshKey)}`);
        const appearance = await apiFetch<{ japanese_family: string; chinese_family: string }>("/api/appearance");
        if (disposed) return;
        await renderer.current?.destroy();
        const nextRenderer = new JASSUB({
          video: background,
          subContent: content,
          timeOffset: media.currentTime - background.currentTime,
          workerUrl,
          wasmUrl,
          modernWasmUrl,
          fonts: [apiUrl("/font/japanese"), apiUrl("/font/chinese")],
          availableFonts: { [appearance.japanese_family]: apiUrl("/font/japanese"), [appearance.chinese_family]: apiUrl("/font/chinese") },
          defaultFont: appearance.japanese_family,
          queryFonts: false,
        });
        renderer.current = nextRenderer;
        await nextRenderer.ready;
        if (disposed) return;
        setStatus("ready");
        const synchronizeClock = () => {
          if (disposed) return;
          if (hasProjectVideo) {
            background.playbackRate = media.playbackRate;
            if (Math.abs(background.currentTime - media.currentTime) > 0.1) background.currentTime = media.currentTime;
            if (media.paused) {
              if (!background.paused) background.pause();
            } else if (background.paused) {
              void background.play();
            }
          }
          nextRenderer.timeOffset = media.currentTime - background.currentTime;
          animationFrame = requestAnimationFrame(synchronizeClock);
        };
        synchronizeClock();
      } catch {
        if (!disposed) setStatus("fallback");
      }
    }
    void load();
    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrame);
      void renderer.current?.destroy();
      renderer.current = null;
    };
  }, [hasProjectVideo, mediaRef, refreshKey]);

  const currentMora = boundaries.findIndex((value, index) => index < boundaries.length - 1 && currentMs >= value && currentMs < boundaries[index + 1]);
  const moraIndex = new Map(line?.moras.map((mora, index) => [mora.id, index]) ?? []);
  const renderedGroups = new Set<string>();

  return (
    <section className="preview-panel" aria-label="字幕与假名预览">
      <div className="preview-toolbar">
        <div className="panel-title"><Captions size={15} /> 字幕与假名预览</div>
        <span className={`preview-status ${status}`}>
          {status === "ready" ? "ASS 数据已同步" : status === "loading" ? "正在载入渲染器" : "使用内置假名预览"}
        </span>
      </div>
      <div className="preview-stage">
        <video ref={backgroundRef} src={hasProjectVideo ? apiUrl("/api/video") : backgroundUrl} muted loop={!hasProjectVideo} playsInline preload="metadata" aria-label={hasProjectVideo ? "项目预览视频" : "内置预览背景"} />
        <audio ref={mediaRef} src={apiUrl("/api/audio")} preload="metadata" />
        {status === "fallback" && <CircleAlert className="preview-warning" size={16} aria-label="ASS 渲染器不可用" />}
        <div className="ruby-subtitle" aria-label="当前句假名字幕">
          {line?.display_tokens.flatMap((token) => {
            const group = line.ruby_groups.find((item) => item.display_token_ids.includes(token.id));
            if (!group) return [<span key={token.id} className="display-only-token">{token.text}</span>];
            if (renderedGroups.has(group.id)) return [];
            renderedGroups.add(group.id);
            const indices = group.mora_ids.map((id) => moraIndex.get(id)).filter((index): index is number => index !== undefined);
            const first = indices.length ? Math.min(...indices) : -1;
            const last = indices.length ? Math.max(...indices) : -1;
            const state = currentMora >= 0 && currentMora > last ? "passed" : currentMora >= first && currentMora <= last ? "active" : "";
            const showRuby = group.reading && !kanaOnly.test(group.display);
            return [<ruby key={group.id} className={`ruby-group ${state}`}><span>{group.display}</span>{showRuby ? <rt>{group.reading}</rt> : null}</ruby>];
          })}
        </div>
        <div className="safe-area" aria-hidden="true" />
      </div>
    </section>
  );
}
