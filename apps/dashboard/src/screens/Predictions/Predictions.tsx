import { useEffect } from "react";
import { FirmHead } from "../../components/firm/FirmHead";
import { ForecastsView } from "../../components/firm/ForecastsView";
import "../../components/firm/firm.css";

/**
 * Forecasts (Admin): what to expect and what to do about it, up to three plain insights each with one chart, then the numbers behind a disclosure.
 * The same view is the Forecasts row of the Firm screen. A worker never reaches it: the shell shows the Admin gate for this address.
 */
export default function Predictions() {
  useEffect(() => { document.title = "Forecasts · Knack"; }, []);
  return (
    <div className="page page--wide firm" data-tab="forecasts">
      <FirmHead title="Forecasts" />
      <ForecastsView />
    </div>
  );
}
