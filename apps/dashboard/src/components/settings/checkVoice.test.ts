// Check voice on the page: the one button on a row, the headline, and the bridge that exists only in the desktop app.
import { describe, expect, it } from "vitest";
import { actionLabel, checkHeadline } from "./CheckVoice";
import { voiceBridge, type VoiceCheck } from "../../screens/Settings/bridge";

const report = (over: Partial<VoiceCheck> = {}): VoiceCheck => ({ ok: true, heyKnack: true, stages: [], at: 1, ...over });

describe("Check voice", () => {
  it("one button per row: Allow asks macOS, Open System Settings opens the pane, none when there is nothing to do", () => {
    expect(actionLabel({ do: "ask", what: "microphone" })).toBe("Allow");
    expect(actionLabel({ do: "open", what: "speech" })).toBe("Open System Settings");
    expect(actionLabel({ do: "open", what: "sound" })).toBe("Open System Settings");
    expect(actionLabel({ do: "settings" })).toBe("Open Settings");
    expect(actionLabel({ do: "ask_again" })).toBe("Ask me again");
    expect(actionLabel({ do: "consent" })).toBe("Show the card");
    expect(actionLabel(null)).toBeNull();
  });
  it("the headline says what works now", () => {
    expect(checkHeadline(report())).toBe("Talking and Hey Knack are ready.");
    expect(checkHeadline(report({ heyKnack: false }))).toContain("Option-Space");
    expect(checkHeadline(report({ ok: false, heyKnack: false }))).toBe("Voice is not ready. Fix the first line marked Fix.");
  });
  it("exists only where the desktop app provides it", () => {
    expect(voiceBridge({})).toBeNull();
    expect(voiceBridge({ knackShell: {} })).toBeNull();
    const check = async () => report();
    const b = voiceBridge({ knackShell: { voice: { check } } });
    expect(b?.check).toBe(check);
  });
});
