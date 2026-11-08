// The background tasks list as static markup: one line each, the state carried by an icon shape and a spoken word, running first, finished ones under a
// closed "Done today", no ids and no counts the worker cannot act on, and nothing at all when there are no tasks.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { groupTasks, type Task, type TaskState } from "../../lib/tasks";
import type { TasksView } from "../../lib/useTasks";
import { TaskSection } from "./BackgroundTasks";

const NOW = Date.parse("2026-11-08T10:00:00Z");
const t = (id: string, state: TaskState, note = "", title = `Task ${id}`, steps: Task["steps"] = []): Task => ({ id, title, state, note, steps, started: new Date(NOW - 5 * 60_000).toISOString(), finished: null, isTask: false, open: null, answer: null });
function view(tasks: Task[], over: Partial<TasksView> = {}, finished: [string, number][] = []): TasksView {
  return { tasks, grouped: groupTasks(tasks, new Map(finished), NOW), ready: true, failed: false, active: tasks.some((x) => x.state === "running"), announce: "", sources: [], reload: () => undefined, want: () => undefined, fromTasks: false, stop: async () => undefined, openResult: async () => undefined, ...over };
}
const html = (v: TasksView, limit?: number) => renderToStaticMarkup(createElement(TaskSection, { v, limit }));
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("the background tasks list", () => {
  it("shows nothing but a quiet live region when there are no tasks", () => {
    const h = html(view([]));
    expect(h).not.toMatch(/Background tasks/);
    expect(h).toMatch(/role="status"/);
  });
  it("is one line per task: an icon, the task in plain words and one short note", () => {
    const h = html(view([t("a", "running", "Working on habit counter."), t("b", "waiting", "Needs you.")]));
    expect((h.match(/class="bt-line"/g) ?? []).length).toBe(2);
    expect(text(h)).toContain("Working on habit counter.");
    expect(text(h)).toContain("Needs you.");
  });
  it("puts running first and carries each state in an icon shape plus a spoken word", () => {
    const h = html(view([t("d", "done"), t("r", "running"), t("w", "waiting")], {}, [["d", NOW - 5000]]));
    expect(h.indexOf("Task r")).toBeLessThan(h.indexOf("Task w"));
    expect(h.indexOf("Task w")).toBeLessThan(h.indexOf("Task d"));
    expect(h).toMatch(/bt-icon--running[^>]*><i class="bt-spin"/);
    expect(h).toMatch(/bt-icon--done[^>]*><svg/);
    for (const w of ["Running.", "Needs you.", "Done."]) expect(text(h)).toContain(w);
  });
  it("shows a dash for a stopped task and a cross for one that did not finish", () => {
    const h = html(view([t("s", "stopped"), t("f", "failed")], {}, [["s", NOW - 1000], ["f", NOW - 1000]]));
    expect(h).toMatch(/bt-icon--stopped[^>]*>[^]*?M4 8h8/);
    expect(h).toMatch(/bt-icon--failed[^>]*>[^]*?M5 5l6 6/);
  });
  it("keeps the steps closed until the line is pressed, and prints no id and no count the worker cannot use", () => {
    const h = html(view([t("r_abc123", "running", "Working.", "Chart builder", [{ label: "reading the file", state: "done" }])]));
    expect(h).toMatch(/aria-expanded="false"/);
    expect(h).not.toMatch(/class="bt-steps"/);
    expect(text(h)).not.toMatch(/r_abc123/);
    expect(text(h)).not.toMatch(/\b\d+ of \d+\b|step 0|budget|lease/i);
  });
  it("folds the rest of today's finished tasks into a closed 'Done today'", () => {
    const h = html(view([t("a", "done"), t("b", "done"), t("c", "stopped")]));
    expect(text(h)).toContain("Done today (3)");
    expect(h).not.toMatch(/<details[^>]*open/);
  });
  it("counts what does not fit instead of drawing it", () => {
    const many = ["a", "b", "c", "d", "e", "f"].map((id) => t(id, "running"));
    const h = html(view(many), 3);
    expect((h.match(/class="bt-line"/g) ?? []).length).toBe(3);
    expect(text(h)).toContain("3 more running or just finished.");
  });
  it("announces a finish in one quiet sentence for a screen reader, never as a toast", () => {
    const h = html(view([t("a", "done")], { announce: "Chart builder finished." }));
    expect(h).toMatch(/aria-live="polite"[^>]*data-testid="tasks-live">Chart builder finished\./);
    expect(h).not.toMatch(/toast/i);
  });
  it("says so, with a way to retry, when the list cannot be read at all", () => {
    const h = html(view([], { failed: true }));
    expect(text(h)).toContain("Background tasks could not be read.");
    expect(text(h)).toContain("Try again");
  });
  it("a very long title or note wraps instead of widening the line, and a missing note leaves the line short", () => {
    const h = html(view([t("a", "running", "", "Y".repeat(300))]));
    expect(h).toMatch(/class="bt-title"/);
    expect((h.match(/class="bt-note"><\/span>/g) ?? []).length).toBe(1);
  });
});
