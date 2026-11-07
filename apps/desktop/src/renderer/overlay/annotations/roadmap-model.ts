// Pure view-model for the Showtime roadmap strip and the "Scripted walkthrough" badge.
import type { ShowtimeChapterStatus, ShowtimeState } from '../../../shared/showtime'

export const BADGE_TEXT = 'Scripted walkthrough on a practice desktop'

export interface RoadmapItem {
  id: string
  n: number
  title: string
  status: ShowtimeChapterStatus
}

export interface RoadmapModel {
  visible: boolean
  // The badge text, or null when it is switched off, the tour is live-mode, or the tour is not running.
  badge: string | null
  items: RoadmapItem[]
  current: { n: number; title: string; caption: string } | null
  // 0..1 inside the current chapter.
  progress: number
  paused: boolean
  // The tour finished: nothing is drawn, the app is back to normal.
  handover: boolean
}

export const EMPTY_ROADMAP: RoadmapModel = { visible: false, badge: null, items: [], current: null, progress: 0, paused: false, handover: false }

export function roadmapModel(s: ShowtimeState, now: number): RoadmapModel {
  if (!s.running) return { ...EMPTY_ROADMAP, handover: s.handover }
  const chapter = s.chapters[s.chapterIndex]
  const live = s.since !== null && !s.paused ? Math.max(0, now - s.since) : 0
  const progress = s.chapterDurationMs > 0 ? Math.min(1, (s.chapterElapsedMs + live) / s.chapterDurationMs) : 0
  return {
    visible: true,
    badge: s.badge && s.mode === 'scripted' ? BADGE_TEXT : null,
    items: s.chapters.map((c) => ({ id: c.id, n: c.n, title: c.title, status: c.status })),
    current: chapter ? { n: chapter.n, title: chapter.title, caption: chapter.caption } : null,
    progress,
    paused: s.paused,
    handover: false,
  }
}
