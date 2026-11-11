import type { EditorPreferences } from "./lib/preferences-11月7日";
export type ReadingSource =
  | "user_override"
  | "agent_override"
  | "explicit_ruby"
  | "mecab_unidic"
  | "local_fallback"
  | "display_only";

export interface Span {
  start: number;
  end: number;
}

export interface DisplayToken {
  id: string;
  text: string;
  span: Span;
  alignable: boolean;
}

export interface MoraToken {
  id: string;
  kana: string;
  romaji: string;
  group_id: string;
  display_token_id: string;
}

export interface RubyGroup {
  id: string;
  span: Span;
  display_token_ids: string[];
  display: string;
  reading: string;
  mora_ids: string[];
  source: ReadingSource;
  synthetic_breaks: number[];
}

export interface LyricLine {
  id: string;
  source_index: number;
  paragraph_before: number;
  original: string;
  display_tokens: DisplayToken[];
  ruby_groups: RubyGroup[];
  moras: MoraToken[];
  yohane_input: string;
  state: "ready" | "stale" | "aligned" | "structural_warning";
  warning_codes: string[];
  reference_time_ms?: number;
}

export interface StructuralIssue {
  code: string;
  severity: "info" | "warning" | "error";
  line_id?: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ProjectPayload {
  editor_preferences?: EditorPreferences;
  editor?: EditorScene;
  project_id: string;
  title: string;
  updated_at: string;
  alignment_stale: boolean;
  alignment_source?: "yohane" | "preserved_ass";
  lines: LyricLine[];
  issues: StructuralIssue[];
  effective_boundaries: Record<string, number[]>;
  source: {
    audio_path?: string;
    video_path?: string;
  };
  audio: {
    prepared_path?: string;
    duration_ms?: number;
  };
  model: {
    model_id: string;
    revision: string;
    license: string;
    license_accepted_at?: string;
  };
  override_history: Array<{
    id: string;
    line_id: string;
    author: string;
    reason: string;
    created_at: string;
  }>;
}

export interface SceneKana {
  text: string; left: number; right: number; y: number; start_ms: number; end_ms: number;
  mora_index?: number; mora_indices?: number[];
}
export interface SceneGlyph {
  text: string; left: number; right: number; y: number; start_ms: number; end_ms: number;
  mora_indices: number[]; kana: SceneKana[];
}
export interface SceneLine {
  id: string; index: number; start_ms: number; end_ms: number;
  display_start_ms: number; display_end_ms: number; width: number;
  glyphs: SceneGlyph[]; paragraph_start: boolean; countdown: boolean;
  countdown_position?: {left: number; y: number; radius: number; spacing: number} | null;
}
export interface EditorScene {
  video_bitrate_mbps?: number | null;
  typography?: {width:number;height:number;main:number;reading:number;title:number;chinese:number;title_y:number;outline:number;title_outline:number;chinese_outline?:number;bold:boolean};
  lines: SceneLine[]; canvas: {width: number; height: number}; theme: string; title_text: string;
  colors: {sung: string; unsung_fill: string; unsung_outline: string; sung_outline: string; title_fill: string; title_outline?: string};
  layout: {margin_x?: number; top_y?: number; bottom_y?: number};
  blackout: Array<{x: number; y: number; width: number; height: number; start: number; end?: number}>;
  countdown: boolean; katakana_ruby: boolean; translations: Record<string,string>;
  translation_events?: Array<{line_id:string;text:string;start_ms:number;end_ms:number;alignment:number;x:number;y:number}>;
  subtitle_offset_ms: number; video_offset_ms: number; audio_offset_ms: number;
}

export interface WaveformPayload {
  start_ms?: number; end_ms?: number;
  peaks: number[];
  duration_ms: number;
}
