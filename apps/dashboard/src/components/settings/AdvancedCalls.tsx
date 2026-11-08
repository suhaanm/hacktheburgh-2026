import { api } from "../../api";
import { ErrorState, Loading } from "../common";
import { Sent } from "../yourdata/Sent";
import { useLoad } from "../../hooks";

/**
 * Every call Knack makes: the list of what went to a model, exactly as sent, under Settings, Advanced (closed). This is the only place the call list
 * appears for a worker: Your data says one sentence and links here. It is read when Advanced is opened, not before.
 */
export default function AdvancedCalls() {
  const ledger = useLoad(() => api.privacyLedger(), []);
  const summary = useLoad(() => api.privacySummary(), []);
  if (ledger.status === "error" && !ledger.data) return <ErrorState error={ledger.error} retry={ledger.reload} what="the list of calls" />;
  if (!ledger.data) return <Loading label="Loading every call Knack makes" />;
  return (
    <div style={{ display: "grid", gap: "var(--space-2)" }} data-testid="advanced-calls">
      <p className="kc-label">Every call Knack makes</p>
      <Sent entries={ledger.data} summary={summary.data} onChanged={() => { ledger.reload(); summary.reload(); }} />
    </div>
  );
}
