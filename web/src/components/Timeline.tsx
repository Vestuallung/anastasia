import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { LyricLine } from "../types";

interface TimelineProps {
  line?: LyricLine;
  boundaries: number[];
  peaks: number[];
  durationMs: number;
  currentMs: number;
  onSeek: (milliseconds: number) => void;
  onPreview: (boundaries: number[] | null) => void;
  onCommit: (
    before: number[],
    after: number[],
    kind: "line_shift" | "boundary" | "line_start" | "line_end",
    boundaryIndex?: number,
  ) => void;
  onRestore: () => void;
}

interface DragState {
  type: "line" | "boundary";
  index?: number;
  startX: number;
  before: number[];
}

const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), high);
const formatTime = (value: number) => `${Math.floor(value / 60000)}:${((value % 60000) / 1000).toFixed(2).padStart(5, "0")}`;

export function Timeline({ line, boundaries, peaks, durationMs, currentMs, onSeek, onPreview, onCommit, onRestore }: TimelineProps) {
  const root = useRef<HTMLDivElement>(null);
  const drag = useRef<DragState | null>(null);
  const draftRef = useRef<number[]>(boundaries);
  const [draft, setDraft] = useState<number[]>(boundaries);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    drag.current = null;
    draftRef.current = boundaries;
    setDraft(boundaries);
    setZoom(1);
    onPreview(null);
  }, [line?.id]);

  const source = drag.current ? draft : boundaries;
  const lineStart = source[0] ?? 0;
  const lineEnd = source[source.length - 1] ?? Math.min(durationMs, 1000);
  const lineDuration = Math.max(200, lineEnd - lineStart);
  const context = Math.max(140, (lineDuration * 0.18) / zoom);
  const viewStart = Math.max(0, lineStart - context);
  const viewEnd = Math.min(durationMs || lineEnd + context, lineEnd + context);
  const viewDuration = Math.max(1, viewEnd - viewStart);
  const canvasWidth = Math.max(920, Math.max(1, line?.moras.length ?? 0) * 72);
  const toPercent = (value: number) => ((value - viewStart) / viewDuration) * 100;
  const currentMora = source.findIndex((value, index) => index < source.length - 1 && currentMs >= value && currentMs < source[index + 1]);

  const visiblePeaks = useMemo(() => {
    if (!peaks.length || !durationMs) return [];
    const start = Math.floor((viewStart / durationMs) * peaks.length);
    const end = Math.ceil((viewEnd / durationMs) * peaks.length);
    return peaks.slice(start, Math.max(start + 1, end));
  }, [durationMs, peaks, viewEnd, viewStart]);

  function timeAt(clientX: number) {
    const rect = root.current!.getBoundingClientRect();
    return Math.round(viewStart + clamp((clientX - rect.left) / rect.width, 0, 1) * viewDuration);
  }

  function updateDraft(next: number[]) {
    draftRef.current = next;
    setDraft(next);
    onPreview(next);
  }

  function move(clientX: number) {
    const state = drag.current;
    if (!state || !root.current) return;
    if (state.type === "line") {
      const delta = timeAt(clientX) - timeAt(state.startX);
      const minDelta = -state.before[0];
      const maxDelta = durationMs - state.before[state.before.length - 1];
      const bounded = clamp(delta, minDelta, maxDelta);
      updateDraft(state.before.map((value) => value + bounded));
      return;
    }
    const index = state.index!;
    const next = [...state.before];
    const low = index === 0 ? 0 : next[index - 1];
    const high = index === next.length - 1 ? durationMs : next[index + 1];
    next[index] = clamp(timeAt(clientX), low, high);
    updateDraft(next);
  }

  function finish() {
    const state = drag.current;
    if (!state) return;
    const after = draftRef.current;
    drag.current = null;
    onPreview(null);
    if (after.some((value, index) => value !== state.before[index])) {
      const kind = state.type === "line" ? "line_shift" : state.index === 0 ? "line_start" : state.index === after.length - 1 ? "line_end" : "boundary";
      onCommit(state.before, after, kind, state.index);
    }
  }

  function beginLine(event: React.PointerEvent) {
    if (!source.length) return;
    const before = [...source];
    drag.current = { type: "line", startX: event.clientX, before };
    draftRef.current = before;
    setDraft(before);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function beginBoundary(event: React.PointerEvent, index: number) {
    event.stopPropagation();
    const before = [...source];
    drag.current = { type: "boundary", index, startX: event.clientX, before };
    draftRef.current = before;
    setDraft(before);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  return (
    <section className="timeline-panel" aria-label="单句时间轴编辑器">
      <div className="timeline-toolbar">
        <div>
          <span className="eyebrow">当前句 MORA 时间轴</span>
          <strong>{line ? `${line.source_index + 1}. ${line.display_tokens.map((token) => token.text).join("")}` : "尚未选择歌词"}</strong>
        </div>
        <div className="timeline-actions">
          <span className="timeline-help">拖动边界会同时调整左右两个音</span>
          <button title="缩小" aria-label="缩小时间轴" onClick={() => setZoom((value) => Math.max(1, value / 1.4))}><Minus size={15} /></button>
          <span>{zoom.toFixed(1)}×</span>
          <button title="放大" aria-label="放大时间轴" onClick={() => setZoom((value) => Math.min(8, value * 1.4))}><Plus size={15} /></button>
          <button className="text-button" onClick={onRestore}><RotateCcw size={14} /> 恢复原始</button>
        </div>
      </div>
      <div className="timeline-scroll">
        <div
          className="timeline-track"
          ref={root}
          style={{ width: `${canvasWidth}px` }}
          onPointerMove={(event) => move(event.clientX)}
          onPointerUp={finish}
          onPointerCancel={finish}
          onDoubleClick={(event) => onSeek(timeAt(event.clientX))}
        >
          <svg className="waveform" viewBox={`0 0 ${Math.max(1, visiblePeaks.length)} 100`} preserveAspectRatio="none" aria-hidden="true">
            {visiblePeaks.map((peak, index) => <line key={index} x1={index} x2={index} y1={50 - peak * 42} y2={50 + peak * 42} />)}
          </svg>
          <div className="ruler">
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => <span key={ratio} style={{ left: `${ratio * 100}%` }}>{formatTime(viewStart + ratio * viewDuration)}</span>)}
          </div>
          {source.length > 1 && <div className="line-region" style={{ left: `${toPercent(source[0])}%`, width: `${toPercent(source[source.length - 1]) - toPercent(source[0])}%` }} onPointerDown={beginLine} title="拖动整句" />}
          {source.slice(0, -1).map((start, index) => {
            const end = source[index + 1];
            return <div className={`mora-segment ${index === currentMora ? "active" : currentMs >= end ? "passed" : ""}`} key={`${line?.id}-mora-${index}`} style={{ left: `${toPercent(start)}%`, width: `${toPercent(end) - toPercent(start)}%` }}>
              <strong>{line?.moras[index]?.kana || `#${index + 1}`}</strong><span>{Math.max(0, end - start)} ms</span>
            </div>;
          })}
          {source.map((value, index) => {
            const leftMora = index > 0 ? line?.moras[index - 1]?.kana : "句首";
            const rightMora = index < source.length - 1 ? line?.moras[index]?.kana : "句尾";
            return <button key={`${line?.id}-boundary-${index}`} className={`boundary ${index === 0 || index === source.length - 1 ? "edge" : ""}`} style={{ left: `${toPercent(value)}%` }} onPointerDown={(event) => beginBoundary(event, index)} aria-label={`边界 ${index + 1}，${value} 毫秒，左侧 ${leftMora}，右侧 ${rightMora}`} title={`${leftMora}｜${rightMora} · ${value} ms`}><span>{index === 0 ? "入" : index === source.length - 1 ? "出" : value}</span></button>;
          })}
          <div className="playhead" style={{ left: `${toPercent(currentMs)}%` }} />
        </div>
      </div>
      <div className="timeline-legend"><span><i className="legend-edge" />绿色：整句首尾</span><span><i />蓝色：相邻 mora 共享边界</span><span>双击波形可定位播放</span></div>
    </section>
  );
}
