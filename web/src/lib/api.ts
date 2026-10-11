import type { ProjectPayload, WaveformPayload } from "../types";

const params = new URLSearchParams(window.location.search);
const urlToken = params.get("token");
if (urlToken) {
  sessionStorage.setItem("karaoke-session-token", urlToken);
  params.delete("token");
  const clean = `${window.location.pathname}${params.size ? `?${params}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", clean);
}

export const sessionToken = sessionStorage.getItem("karaoke-session-token") ?? "";

export function apiUrl(path: string): string {
  if (!sessionToken) return path;
  return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(sessionToken)}`;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (sessionToken) headers.set("X-Karaoke-Token", sessionToken);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  return (contentType.includes("application/json") ? response.json() : response.text()) as Promise<T>;
}

export const getProject = () => apiFetch<ProjectPayload>("/api/project");
export const getWaveform = () => apiFetch<WaveformPayload>("/api/waveform?points=1800");

export async function saveTiming(
  lineId: string,
  boundaries: number[],
  kind: "line_shift" | "boundary" | "line_start" | "line_end",
  boundaryIndex?: number,
): Promise<ProjectPayload> {
  return apiFetch(`/api/lines/${lineId}/timing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boundaries_ms: boundaries,
      kind,
      boundary_index: boundaryIndex,
      reason: "timeline editor",
    }),
  });
}

export async function saveReading(
  lineId: string,
  expectedText: string,
  span: { start: number; end: number },
  reading: string,
  romaji: string,
): Promise<ProjectPayload> {
  return apiFetch(`/api/lines/${lineId}/reading`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_text: expectedText,
      span_start: span.start,
      span_end: span.end,
      reading,
      romaji,
      reason: "reading inspector",
    }),
  });
}
