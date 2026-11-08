import { ADMIN_MARKER } from "../home/viewAs";

/** The one printed line under every Admin title: a use limit, so it is never behind a Hint. */
export const FIRM_LIMIT = "For coaching and onboarding, not for evaluating individuals.";

/**
 * The head of every Admin screen: the title (a name, six words at most), the Admin view marker and the use limit. Generated data draws no origin tag (owner decision D57): where the numbers come from is said inside "About this data".
 */
export function FirmHead({ title }: { title: string }) {
  return (
    <header className="screenhead">
      <div className="screenhead__row">
        <h1 className="screenhead__title">{title}</h1>
        <div className="page__aside">
          <span className="screenhead__marker">{ADMIN_MARKER}</span>
        </div>
      </div>
      <p className="screenhead__limit">{FIRM_LIMIT}</p>
    </header>
  );
}
