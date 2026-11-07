import type { api } from "../../api";
import type { Routine } from "../../types";

export type ConsentBody = Parameters<typeof api.setConsent>[1];
/** Save one consent choice for a routine. Resolves when it is saved, rejects with an ApiError the row prints. */
export type Decide = (routine: Routine, body: ConsentBody, done: string) => Promise<void>;
