import { useEffect } from "react";
import { PageHead } from "../../components/common";
import { ScorecardView, useScorecard } from "../../components/firm/ScorecardPanel";

/**
 * Predictions: how well we forecast the moments when someone gets stuck. One hero (the reliability diagram), then the comparison with
 * two simple baselines, false alarms against the budget, and, when the report has it, time to progress. A detail screen, so intervals
 * and n stay in view. Everything is read from evals/report.json through GET /eval/report.
 */
export default function Predictions() {
  const { load, read } = useScorecard();
  useEffect(() => { document.title = "Predictions · Understudy"; }, []);
  return (
    <div className="page page--wide">
      <PageHead eyebrow="Details" title="Predictions" lede="How well we forecast the moments when someone gets stuck." />
      <ScorecardView load={load} read={read} />
    </div>
  );
}
