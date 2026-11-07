// Adapted from farzaa/clicky (MIT) — leanring-buddy/CompanionScreenCaptureUtility.swift (screenshot sizing and JPEG compression)
// Capture sizing per TEAM_BRIEF section 4: 'live' <= 1280 px wide at q~0.6; 'ground' | 'verify' up to 1920 wide.
// Never upscales past the display's physical resolution (a 1440p retina panel is 3456 px wide, so both caps bite).
import type { ShotPurpose } from '../../shared/protocol'

export interface CaptureProfile {
  maxWidth: number
  // JPEG quality 0-100 (Electron's toJPEG scale).
  quality: number
}

export const PROFILES: Record<ShotPurpose, CaptureProfile> = {
  live: { maxWidth: 1280, quality: 60 },
  ground: { maxWidth: 1920, quality: 80 },
  verify: { maxWidth: 1920, quality: 80 },
}

export function targetSize(displayDip: { width: number; height: number }, scaleFactor: number, purpose: ShotPurpose): { width: number; height: number } {
  const physicalW = Math.max(1, Math.round(displayDip.width * scaleFactor))
  const physicalH = Math.max(1, Math.round(displayDip.height * scaleFactor))
  const width = Math.min(PROFILES[purpose].maxWidth, physicalW)
  return { width, height: Math.max(1, Math.round((width * physicalH) / physicalW)) }
}
