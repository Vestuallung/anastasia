import { useEffect, useMemo, useState } from "react";
import { BookOpen, Clock3, History, Save, TriangleAlert } from "lucide-react";
import type { LyricLine, ProjectPayload, RubyGroup } from "../types";

interface InspectorProps {
  project: ProjectPayload;
  line?: LyricLine;
  boundaries: number[];
  saving: boolean;
  onSaveReading: (group: RubyGroup, reading: string, romaji: string) => void;
}

const sourceLabels: Record<string, string> = {
  user_override: "用户覆盖",
  agent_override: "Agent 覆盖",
  explicit_ruby: "歌词内假名标注",
  mecab_unidic: "MeCab / UniDic",
  local_fallback: "结构映射",
  display_only: "仅显示",
};

const stateLabels: Record<string, string> = {
  ready: "待对齐",
  stale: "需要重新对齐",
  aligned: "已对齐",
  structural_warning: "结构警告",
};

export function Inspector({ project, line, boundaries, saving, onSaveReading }: InspectorProps) {
  const [tab, setTab] = useState<"reading" | "timing" | "history">("reading");
  const [groupId, setGroupId] = useState("");
  const group = useMemo(
    () => line?.ruby_groups.find((item) => item.id === groupId) ?? line?.ruby_groups[0],
    [groupId, line],
  );
  const [reading, setReading] = useState("");
  const [romaji, setRomaji] = useState("");

  useEffect(() => {
    setGroupId(line?.ruby_groups[0]?.id ?? "");
  }, [line?.id, line?.ruby_groups]);

  useEffect(() => {
    setReading(group?.reading ?? "");
    const moraIds = new Set(group?.mora_ids ?? []);
    setRomaji(line?.moras.filter((mora) => moraIds.has(mora.id)).map((mora) => mora.romaji).join(" ") ?? "");
  }, [group, line]);

  const lineIssues = project.issues.filter((issue) => issue.line_id === line?.id);
  const history = project.override_history.filter((item) => item.line_id === line?.id).reverse();

  return (
    <aside className="inspector">
      <div className="inspector-tabs">
        <button className={tab === "reading" ? "active" : ""} onClick={() => setTab("reading")}><BookOpen size={15} /> 读音</button>
        <button className={tab === "timing" ? "active" : ""} onClick={() => setTab("timing")}><Clock3 size={15} /> 时间</button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")} aria-label="修改历史"><History size={15} /></button>
      </div>
      {!line ? (
        <div className="empty-inspector">请选择一句歌词，查看并修改读音与时间。</div>
      ) : tab === "reading" ? (
        <div className="inspector-body">
          <div className="section-heading"><span>显示文字与假名</span><span className={`state-badge ${line.state}`}>{stateLabels[line.state]}</span></div>
          <div className="display-card">
            <span className="ruby-reading">{group?.reading}</span>
            <strong>{line.display_tokens.map((token) => token.text).join("")}</strong>
          </div>
          <label>读音分组
            <select value={group?.id ?? ""} onChange={(event) => setGroupId(event.target.value)}>
              {line.ruby_groups.map((item) => <option key={item.id} value={item.id}>{item.display} · {item.reading}</option>)}
            </select>
          </label>
          <label>假名读音
            <input value={reading} onChange={(event) => setReading(event.target.value)} />
          </label>
          <label>罗马字 mora 单位
            <input value={romaji} onChange={(event) => setRomaji(event.target.value)} spellCheck={false} />
          </label>
          <div className="source-row"><span>来源</span><span className="source-badge">{sourceLabels[group?.source ?? ""] ?? group?.source}</span></div>
          <button className="primary full" disabled={!group || saving} onClick={() => group && onSaveReading(group, reading, romaji)}>
            <Save size={15} /> {saving ? "保存中……" : "保存读音"}
          </button>
          <p className="hint">修改读音后，点击整曲对齐即可更新时间。</p>
          {lineIssues.map((issue) => (
            <div className={`issue ${issue.severity}`} key={`${issue.code}-${issue.message}`}><TriangleAlert size={15} /><div><strong>{issue.code}</strong><span>{issue.message}</span></div></div>
          ))}
        </div>
      ) : tab === "timing" ? (
        <div className="inspector-body timing-list">
          <div className="section-heading"><span>整数毫秒</span><span>{Math.max(0, boundaries.length - 1)} 个 mora</span></div>
          {boundaries.slice(0, -1).map((start, index) => (
            <div className="timing-row" key={index}>
              <span className="mora-chip">{line.moras[index]?.kana || `#${index + 1}`}</span>
              <span>{start} ms</span><span>→</span><span>{boundaries[index + 1]} ms</span>
            </div>
          ))}
          <p className="hint">拖动内部边界只会改变左右相邻两个 mora；导出 ASS 时量化为 10 ms。</p>
        </div>
      ) : (
        <div className="inspector-body">
          <div className="section-heading"><span>覆盖修改历史</span><span>{history.length}</span></div>
          {history.length ? history.map((item) => (
            <div className="history-card" key={item.id}><strong>{item.author}</strong><span>{item.reason}</span><time>{new Date(item.created_at).toLocaleString()}</time></div>
          )) : <p className="hint">这一句没有读音覆盖记录。</p>}
        </div>
      )}
    </aside>
  );
}
