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

describe("Karaoke Studio structured editor", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url=String(input);
      if(url.startsWith("/api/waveform"))return new Response(JSON.stringify({peaks:[.2,.8,.4],duration_ms:5000,start_ms:0,end_ms:5000}),{headers:{"content-type":"application/json"}});
      if(url.startsWith("/api/jobs/render"))return Response.json({job_id:"render-test"});
      return new Response(JSON.stringify(project),{headers:{"content-type":"application/json"}});
    }));
  });
  it("opens existing model data without requesting ASS playback",async()=>{
    render(<App/>);
    expect(await screen.findByText("君は０から１になれ",{selector:".project-title"})).toBeVisible();
    expect(screen.getAllByLabelText(/边界 1，1000 毫秒/,{selector:"button"})[0]).toBeVisible();
    expect(screen.getByRole("button",{name:"导出成片"})).toBeEnabled();
    expect(screen.getByLabelText("结构化字幕画布")).toBeVisible();
    expect(screen.queryByText("正在使用 Yohane 原始时间")).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url])=>String(url).includes("preview.ass"))).toBe(false);
    await userEvent.selectOptions(screen.getByLabelText("播放速度"),"1.5");
    expect(document.querySelector("audio")?.playbackRate).toBe(1.5);
  });
  it("keeps help out of the editing surface",async()=>{
    render(<App/>);await screen.findByRole("button",{name:"帮助"});
    expect(screen.queryByText(/拖动色块移动字音/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button",{name:"帮助"}));
    expect(screen.getByRole("dialog",{name:"帮助"})).toBeVisible();
  });
  it("allows selecting rendering settings",async()=>{
    render(<App/>);await screen.findByText("字幕样式");
    await userEvent.click(screen.getByRole("button",{name:"字幕样式"}));
    expect(screen.getByLabelText("右上标题")).toBeVisible();
    expect(screen.getByLabelText("遮黑比例")).toBeVisible();
  });
  it("requests an upload copy when the editor option is selected",async()=>{
    vi.stubGlobal("EventSource", class {close() {}});
    render(<App/>);
    const option=await screen.findByLabelText("同时生成上传版（500 MB 以内）");
    expect(option).not.toBeChecked();
    await userEvent.click(option);
    await userEvent.click(screen.getByRole("button",{name:"导出成片"}));
    await waitFor(()=>expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/jobs/render?fresh=true&upload=true"),
      expect.objectContaining({method:"POST"}),
    ));
  });
  it("passes the selected Mbps value to the main render request",async()=>{
    vi.stubGlobal("EventSource", class {close() {}});
    render(<App/>);
    const bitrate=await screen.findByLabelText("视频码率");
    await userEvent.selectOptions(bitrate,"custom");
    expect(screen.getByRole("button",{name:"导出成片"})).toBeDisabled();
    await userEvent.type(screen.getByLabelText("自定义码率（Mbps）"),"10.5");
    await userEvent.click(screen.getByRole("button",{name:"导出成片"}));
    await waitFor(()=>expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/jobs/render?fresh=true&video_bitrate_mbps=10.5"),
      expect.objectContaining({method:"POST"}),
    ));
  });
});
