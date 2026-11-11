export interface EditorPreferences {
  schema_version: 1;
  playback_speed: number;
  preserve_pitch: boolean;
  loop: 'line' | 'off';
  lead_ms: number;
  snap: boolean;
  snap_ms: number;
  key_step_ms: number;
  seek_large_ms: number;
  show_waveform: boolean;
  show_characters: boolean;
  show_readings: boolean;
}

export const defaultPreferences: EditorPreferences = {
  schema_version: 1,
  playback_speed: .75,
  preserve_pitch: true,
  loop: 'line',
  lead_ms: 250,
  snap: true,
  snap_ms: 10,
  key_step_ms: 10,
  seek_large_ms: 1000,
  show_waveform: true,
  show_characters: true,
  show_readings: true,
};

export interface StyleSettings {
  title_text?: string;
  theme?: string;
  colors?: Record<string, string>;
  layout?: {margin_x?: number; top_y?: number; bottom_y?: number};
  countdown?: boolean;
  katakana_ruby?: boolean;
  media?: {blackout: Array<{x:number;y:number;width:number;height:number;start:number;end?:number}>};
}
