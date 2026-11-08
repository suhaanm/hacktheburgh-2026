// "Change profile": edit the name (kept on this Mac only) and choose the role. Saving posts only what changed to /profile, which keeps the person, the name,
// the quiet hours and the capture choice, switches the role and starts the new role's skills clean; then the screen reloads so Home, Growth and the coach
// follow the role. Nothing here is a consent or an approval, and a role is only ever one the engine lists.
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api";
import { NAME_MAX, NAME_PLACEHOLDER, ROLE_NOTE, SAVED_EXAMPLE, SAVED_LIVE, SAVE_FAILED, checkName, profileChange, setDisplayName, type ProfileRole } from "../../lib/profile";
import { setState } from "../../store";

export function ProfileForm({ name, role, roles, onDone }: { name: string | null; role: string | null; roles: ProfileRole[] | null; onDone: () => void }) {
  const [draft, setDraft] = useState(name ?? "");
  const [pick, setPick] = useState<string | null>(role);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  const roleChanges = pick !== null && pick !== role;

  const save = async () => {
    const c = checkName(draft);
    if (!c.ok) { setMsg({ tone: "error", text: c.message }); input.current?.focus(); return; }
    const body = profileChange({ role, name }, { role: pick, name: c.name });
    if (!body) { onDone(); return; }
    setBusy(true); setMsg(null);
    try {
      const out = await api.setProfile(body);
      const done = out.data;
      setDisplayName(done.name ?? c.name);
      if (done.role) setState({ role: done.role, person: done.person });
      // The engine is the truth about who the worker is: ask again and reload the screen so it shows the new role's pointers and progress.
      if (out.source === "live" && done.role_changed) window.dispatchEvent(new Event("understudy:retry"));
      setMsg({ tone: "ok", text: out.source === "live" ? SAVED_LIVE : SAVED_EXAMPLE });
    } catch (e) {
      setMsg({ tone: "error", text: e instanceof ApiError && e.message ? e.message : SAVE_FAILED });
    } finally { setBusy(false); }
  };

  return (
    <form className="profile" onSubmit={(e) => { e.preventDefault(); void save(); }} aria-label="Change profile">
      <label className="profile__field">
        <span className="popover__label">Name</span>
        <input ref={input} className="input" type="text" value={draft} maxLength={NAME_MAX} placeholder={NAME_PLACEHOLDER} autoComplete="off" spellCheck={false} dir="auto" aria-describedby="profile-name-note" aria-invalid={msg?.tone === "error" && checkName(draft).ok === false ? true : undefined} onChange={(e) => { setDraft(e.target.value); if (msg?.tone === "error") setMsg(null); }} />
      </label>
      <p className="popover__note profile__note" id="profile-name-note">Kept on this Mac only.</p>

      <fieldset className="profile__roles" disabled={busy}>
        <legend className="popover__label">Role</legend>
        {roles === null && <p className="popover__note">Loading roles</p>}
        {roles !== null && roles.length === 0 && <p className="popover__note">Roles could not be loaded. Your name can still be saved.</p>}
        {(roles ?? []).map((r) => (
          <label key={r.id} className="profile__role">
            <input type="radio" name="profile-role" value={r.id} checked={pick === r.id} onChange={() => setPick(r.id)} />
            <span>{r.name}</span>
          </label>
        ))}
      </fieldset>
      {roleChanges && <p className="popover__note profile__note">{ROLE_NOTE}</p>}

      {msg && <p className={`popover__note profile__note${msg.tone === "error" ? " popover__note--error" : ""}`} role={msg.tone === "error" ? "alert" : "status"}>{msg.text}</p>}
      <div className="profile__actions">
        {msg?.tone !== "ok" && <button type="submit" className="btn btn--primary btn--sm" disabled={busy}>{busy ? "Saving" : roleChanges ? "Switch role" : "Save"}</button>}
        <button type="button" className="btn btn--secondary btn--sm" onClick={onDone}>{msg?.tone === "ok" ? "Close" : "Cancel"}</button>
      </div>
    </form>
  );
}
