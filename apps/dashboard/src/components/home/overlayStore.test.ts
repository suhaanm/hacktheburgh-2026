import { beforeEach, describe, expect, it } from "vitest";
import { closePalette, endTour, getOverlay, openPalette, resetOverlay, setTourStep, startTour, takeTourReturn, togglePalette } from "./overlayStore";

beforeEach(() => resetOverlay());

describe("overlay store", () => {
  it("starts with nothing open: the tour never starts by itself", () => {
    expect(getOverlay()).toEqual({ palette: false, tour: null });
  });
  it("opens, closes and toggles the palette", () => {
    openPalette();
    expect(getOverlay().palette).toBe(true);
    closePalette();
    expect(getOverlay().palette).toBe(false);
    togglePalette();
    expect(getOverlay().palette).toBe(true);
    togglePalette();
    expect(getOverlay().palette).toBe(false);
  });
  it("starting the tour closes the palette, so one thing speaks at a time", () => {
    openPalette();
    startTour();
    expect(getOverlay()).toEqual({ palette: false, tour: { step: 0 } });
  });
  it("moves between steps, never below zero, and ignores a step when there is no tour", () => {
    setTourStep(3);
    expect(getOverlay().tour).toBeNull();
    startTour(2);
    expect(getOverlay().tour).toEqual({ step: 2 });
    setTourStep(-4);
    expect(getOverlay().tour).toEqual({ step: 0 });
    setTourStep(4.8);
    expect(getOverlay().tour).toEqual({ step: 4 });
  });
  it("ends the tour and hands back no stale focus target", () => {
    startTour();
    endTour();
    expect(getOverlay().tour).toBeNull();
    expect(takeTourReturn()).toBeNull();
  });
  it("keeps the same state object when nothing changes, so subscribers do not re-render for nothing", () => {
    const a = getOverlay();
    closePalette();
    endTour();
    setTourStep(1);
    expect(getOverlay()).toBe(a);
  });
});
