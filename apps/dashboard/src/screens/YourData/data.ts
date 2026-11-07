// Delete everything: clears, one part at a time, what Knack holds about the worker, and says which parts were cleared and which were not.
// Each part goes through the same call the screen's own Forget uses. Read-only unless the worker confirmed; example data clears only the example.
import { ApiError, ENGINE_URL, api } from "../../api";
import { deleteNotices } from "../../components/home/noticesData";
import { requestBody, requestHeaders } from "../../lib/http";
import type { Memory } from "../../types";
import { deleteLedger } from "../Growth/data";
import { clearItemsMarkdown, type DeletePart } from "./model";

const why = (e: unknown): string => (e instanceof ApiError || e instanceof Error ? e.message : "it did not go through");

/** The counts of the cursor and the app kind (the awareness layer), cleared for this person only. Off or unknown: nothing to clear. */
async function clearAwareness(person: string): Promise<void> {
  const res = await fetch(`${ENGINE_URL}/awareness/clear`, { method: "POST", headers: requestHeaders("POST"), body: requestBody("POST", { person, origin: "real" }) });
  if (res.status === 404) return;                      // the layer is not switched on: there is nothing of it to clear
  if (res.status >= 400) throw new ApiError(res.status, `http_${res.status}`, `the engine answered with status ${res.status}`);
}

export async function deleteEverything(ctx: { memory: Memory; person: string | null; example: boolean }): Promise<DeletePart[]> {
  const out: DeletePart[] = [];
  const step = async (part: string, fn: () => Promise<unknown>) => {
    try { await fn(); out.push({ part, ok: true }); } catch (e) { out.push({ part, ok: false, note: why(e) }); }
  };
  await step("memory lines", () => api.putMemory(clearItemsMarkdown(ctx.memory.markdown), ctx.memory.revision));
  await step("step counts", () => deleteLedger("going", ctx.example));
  await step("model-call records", () => api.privacyClear());
  await step("what it learned about notices", () => deleteNotices(ctx.person));
  if (ctx.person) await step("cursor and app counts", () => clearAwareness(ctx.person!));
  return out;
}
