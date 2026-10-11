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

export interface WaveformPayload {
  peaks: number[];
  duration_ms: number;
}
