import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Timeline } from "./Timeline";
import type { LyricLine } from "../types";

const line: LyricLine = {
  id: "line-1",
  source_index: 0,
  paragraph_before: 0,
  original: "声《こえ》",
  display_tokens: [{ id: "t1", text: "声", span: { start: 0, end: 1 }, alignable: true }],
  ruby_groups: [{ id: "g1", span: { start: 0, end: 1 }, display_token_ids: ["t1"], display: "声", reading: "こえ", mora_ids: ["m1", "m2"], source: "explicit_ruby", synthetic_breaks: [] }],
  moras: [
    { id: "m1", kana: "こ", romaji: "ko", group_id: "g1", display_token_id: "t1" },
    { id: "m2", kana: "え", romaji: "e", group_id: "g1", display_token_id: "t1" },
  ],
  yohane_input: "ko e",
  state: "aligned",
  warning_codes: [],
};

describe("单句时间轴", () => {
  it("拖动内部共享边界时同步改变左右 mora，并提交同一边界", () => {
    const onPreview = vi.fn();
    const onCommit = vi.fn();
    const { container } = render(<Timeline line={line} boundaries={[1000, 1200, 1500]} peaks={[]} durationMs={5000} currentMs={1000} onSeek={vi.fn()} onPreview={onPreview} onCommit={onCommit} onRestore={vi.fn()} />);
    const track = container.querySelector(".timeline-track") as HTMLDivElement;
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 250, width: 1000, height: 250, toJSON: () => ({}) });

    const handle = screen.getByLabelText(/边界 2，1200 毫秒/);
    fireEvent.pointerDown(handle, { clientX: 450, pointerId: 1 });
    fireEvent.pointerMove(track, { clientX: 550, pointerId: 1 });

    const preview = onPreview.mock.calls.at(-1)?.[0] as number[];
    expect(preview[0]).toBe(1000);
    expect(preview[2]).toBe(1500);
    expect(preview[1]).toBeGreaterThan(1200);

    fireEvent.pointerUp(track, { pointerId: 1 });
    expect(onCommit).toHaveBeenCalledWith([1000, 1200, 1500], preview, "boundary", 1);
  });
});
