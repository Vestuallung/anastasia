import { expect, test } from "@playwright/test";

const project = {
  project_id: "e2e",
  title: "Karaoke Studio E2E",
  updated_at: "2026-08-20T00:00:00Z",
  alignment_stale: false,
  alignment_source: "yohane",
  lines: [{
    id: "line-e2e", source_index: 0, paragraph_before: 0, original: "他人《ひと》を待つ",
    display_tokens: [{ id: "t", text: "他人を待つ", span: { start: 0, end: 9 }, alignable: true }],
    ruby_groups: [{ id: "g", span: { start: 0, end: 6 }, display_token_ids: ["t"], display: "他人", reading: "ひと", mora_ids: ["m1", "m2"], source: "explicit_ruby", synthetic_breaks: [] }],
    moras: [{ id: "m1", kana: "ひ", romaji: "hi", group_id: "g", display_token_id: "t" }, { id: "m2", kana: "と", romaji: "to", group_id: "g", display_token_id: "t" }],
    yohane_input: "hi to", state: "aligned", warning_codes: [],
  }],
  issues: [], effective_boundaries: { "line-e2e": [1000, 1250, 1500] },
  source: { audio_path: "source/audio.wav", video_path: null },
  audio: { prepared_path: "prepared.wav", duration_ms: 5000 },
  model: { model_id: "NextFire/model", revision: "fixed", license: "CC-BY-NC-SA-4.0", license_accepted_at: "2026-08-20" },
  override_history: [],
};

test("editor exposes local project, reading and mora timeline", async ({ page }) => {
  await page.route("**/api/project", (route) => route.fulfill({ json: project }));
  await page.route("**/api/appearance", (route) => route.fulfill({ json: { device: "cpu", model_url: "https://example.org/model", japanese_family: "Noto Sans CJK JP", chinese_family: "Noto Sans CJK JP" } }));
  await page.route("**/api/waveform**", (route) => route.fulfill({ json: { peaks: [0.2, 0.8, 0.4, 0.7], duration_ms: 5000 } }));
  await page.route("**/api/preview.ass**", (route) => route.fulfill({ body: "[Script Info]\n", contentType: "text/plain" }));
  await page.route("**/api/audio**", (route) => route.fulfill({ status: 204 }));
  await page.goto("/?token=e2e-token");

  await expect(page.getByText("Karaoke Studio E2E", { exact: true })).toBeVisible();
  await expect(page.getByText("歌词内假名标注")).toBeVisible();
  await expect(page.getByLabel(/边界 2，1250 毫秒/)).toBeVisible();
  await expect(page.getByText("本地制作流程")).toBeVisible();
  await expect(page.locator(".ruby-subtitle rt")).toHaveText("ひと");

  await page.getByLabel("播放速度").selectOption("1.5");
  await expect(page.getByLabel("播放速度")).toHaveValue("1.5");

  await page.route("**/api/lines/line-e2e/timing", async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({ json: { ...project, effective_boundaries: { "line-e2e": body.boundaries_ms } } });
  });
  const boundary = page.getByLabel(/边界 2，1250 毫秒/);
  const box = await boundary.boundingBox();
  if (!box) throw new Error("timing boundary is not visible");
  const timingRequest = page.waitForRequest("**/api/lines/line-e2e/timing");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 50, box.y + box.height / 2, { steps: 5 });
  await page.mouse.up();
  const body = (await timingRequest).postDataJSON();
  expect(body.kind).toBe("boundary");
  expect(body.boundary_index).toBe(1);
  expect(body.boundaries_ms[0]).toBe(1000);
  expect(body.boundaries_ms[1]).toBeGreaterThan(1250);
  expect(body.boundaries_ms[2]).toBe(1500);
});
