import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const project = {
  project_id: "demo",
  title: "君は０から１になれ",
  updated_at: "2026-08-20T00:00:00Z",
  alignment_stale: false,
  alignment_source: "yohane",
  lines: [
    {
      id: "line-1",
      source_index: 0,
      paragraph_before: 0,
      original: "君は０《ゼロ》から１《ワン》になれ",
      display_tokens: [{ id: "t1", text: "君は０から１になれ", span: { start: 0, end: 18 }, alignable: true }],
      ruby_groups: [{ id: "g1", span: { start: 0, end: 18 }, display_token_ids: ["t1"], display: "君は０から１になれ", reading: "きみはぜろからわんになれ", mora_ids: ["m1", "m2"], source: "explicit_ruby", synthetic_breaks: [] }],
      moras: [{ id: "m1", kana: "き", romaji: "ki", group_id: "g1", display_token_id: "t1" }, { id: "m2", kana: "み", romaji: "mi", group_id: "g1", display_token_id: "t1" }],
      yohane_input: "ki mi",
      state: "aligned",
      warning_codes: [],
    },
  ],
  issues: [],
  effective_boundaries: { "line-1": [1000, 1200, 1400] },
  source: { audio_path: "source/audio.mp4", video_path: "source/video.mp4" },
  audio: { prepared_path: ".karaoke-work/audio.wav", duration_ms: 5000 },
  model: { model_id: "NextFire/model", revision: "fixed", license: "CC-BY-NC-SA-4.0", license_accepted_at: "2026-08-20T00:00:00Z" },
  override_history: [],
};

describe("Karaoke Studio", () => {
  beforeEach(() => {
    sessionStorage.setItem("karaoke-session-token", "test");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/project")) return new Response(JSON.stringify(project), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/appearance")) return new Response(JSON.stringify({ device: "cpu", model_url: "https://example.org/model", japanese_family: "Noto Sans CJK JP", chinese_family: "Noto Sans CJK JP" }), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/waveform")) return new Response(JSON.stringify({ peaks: [0.2, 0.8, 0.4], duration_ms: 5000 }), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/preview.ass")) return new Response("[Script Info]", { headers: { "content-type": "text/plain" } });
      return new Response("{}", { headers: { "content-type": "application/json" } });
    }));
  });

  it("renders aligned project, inspector and timeline controls", async () => {
    render(<App />);

    expect(await screen.findByText("君は０から１になれ", { selector: ".project-title span" })).toBeVisible();
    expect(screen.getByText("正在使用 Yohane 原始时间")).toBeVisible();
    expect(screen.getByText("歌词内假名标注")).toBeVisible();
    expect(screen.getByLabelText(/边界 1，1000 毫秒/)).toBeVisible();
    expect(screen.getByRole("button", { name: /导出 ASS/i })).toBeEnabled();
    expect(document.querySelector(".ruby-subtitle rt")).toHaveTextContent("きみはぜろからわんになれ");
    expect(screen.getByRole("combobox", { name: "播放速度" })).toHaveValue("1");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "播放速度" }), "1.5");
    expect(document.querySelector("audio")?.playbackRate).toBe(1.5);
  });

  it("opens the structural report", async () => {
    render(<App />);
    await screen.findByText("正在使用 Yohane 原始时间");
    await userEvent.click(screen.getByRole("button", { name: /0 个问题/i }));

    await waitFor(() => expect(screen.getByText(/歌词结构检查完成/)).toBeVisible());
  });

  it("shows the configured model details before acceptance", async () => {
    const unaccepted = { ...project, model: { ...project.model, license_accepted_at: null } };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/project")) return new Response(JSON.stringify(unaccepted), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/appearance")) return new Response(JSON.stringify({ device: "cpu", model_url: "https://example.org/model", japanese_family: "Noto Sans CJK JP", chinese_family: "Noto Sans CJK JP" }), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/waveform")) return new Response(JSON.stringify({ peaks: [], duration_ms: 5000 }), { headers: { "content-type": "application/json" } });
      if (url.startsWith("/api/preview.ass")) return new Response("[Script Info]", { headers: { "content-type": "text/plain" } });
      return new Response("{}", { headers: { "content-type": "application/json" } });
    }));
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /查看并接受模型许可/i }));
    expect(screen.getByRole("dialog", { name: /强制对齐模型的许可/i })).toBeVisible();
    expect(screen.getByText("CC-BY-NC-SA-4.0")).toBeVisible();
    expect(screen.getByText("NextFire/model")).toBeVisible();
    expect(screen.getByRole("link", { name: /模型说明与许可页面/i })).toHaveAttribute("href", "https://example.org/model");
  });
});
