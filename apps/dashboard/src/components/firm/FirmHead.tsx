import { ADMIN_MARKER } from "../home/viewAs";
import { SYNTHETIC_NOTE } from "./Badges";

/** The one printed line under every Admin title: a use limit, so it is never behind a Hint. */
export const FIRM_LIMIT = "For coaching and onboarding, not for evaluating individuals.";

/**
 * The head of every Admin screen: the title (a name, six words at most), the Admin view marker, the one origin pill and the use limit.
 * The wording of the origin pill lives in Badges.tsx, so there is one place to change it.
 */
export function FirmHead({ title }: { title: string }) {
  return (
    <header className="screenhead">
      <div className="screenhead__row">
        <h1 className="screenhead__title">{title}</h1>
        <div className="page__aside">
          <span className="screenhead__marker">{ADMIN_MARKER}</span>
          <span className="pill pill--origin firm-synthetic" data-origin="synthetic">{SYNTHETIC_NOTE}</span>
        </div>
      </div>
      <p className="screenhead__limit">{FIRM_LIMIT}</p>
    </header>
  );
}
