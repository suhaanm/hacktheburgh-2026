// Hand-authored fallback LessonPlans for the three skills. They make the demo robust when the Argon architect
// is slow or fails (the runner switches to these after 8 s). Written against STAGE's Practice Desktop:
// descriptions, expected outcomes and step order follow apps/demo-stage/flows.js (window.STAGE_FLOWS) and
// each step's `groundId` is the stage's data-ground-id for it (handy for QA and the grounding benchmark).
import { truncateWords } from '../../../shared/protocol'
import type { BuiltinSkillId, LessonPlan, LessonStep } from '../../../shared/protocol'
import { SKILLS } from './definitions'

interface StaticStep extends Omit<LessonStep, 'index'> {
  // data-ground-id of the target on the Practice Desktop (not used at runtime by the runner).
  groundId: string
}

const VIDEO_CALL: StaticStep[] = [
  {
    id: 'video_call.open_app',
    groundId: 'desk.icon.video',
    instruction: 'Open the VideoChat app on your desktop.',
    targetDescription:
      'Teal rounded-square icon with a white video-camera symbol and the label VideoChat, first icon in the left-hand column of the desktop',
    expectedOutcome:
      'The VideoChat window is open: a contacts list on the left (Dave Morgan, Lily, Priya Shah, Riverside Surgery, Rosa Bell, Tom) and "Select a contact" text on the right.',
    hints: {
      l1: 'See the little camera picture at the top of the left edge? That is the VideoChat program. I will point to it, and then you click it.',
      l2: 'Click the teal VideoChat icon at the top of the left-hand column.',
      l3: 'Look along the left edge of the screen, at the very top: a little camera.',
    },
    safetyCritical: false,
    analogy: SKILLS.video_call.analogy,
  },
  {
    id: 'video_call.pick_lily',
    groundId: 'video.contact.lily',
    instruction: 'Click Lily in your contacts list.',
    targetDescription:
      'Row labelled Lily with the subtitle Granddaughter and a green dot, second row in the contacts list on the left of the VideoChat window',
    expectedOutcome:
      "Lily's row is highlighted and the right-hand pane shows a large avatar, the name Lily, \"Granddaughter\", and a large green Start call button.",
    hints: {
      l1: 'This list works like a phone book. Lily is the second name, with a green dot that means she is online. Now you click her name.',
      l2: 'Click Lily in the list on the left.',
      l3: 'Second name down the list: it says Granddaughter underneath.',
    },
    safetyCritical: false,
  },
  {
    id: 'video_call.start_call',
    groundId: 'video.start_call',
    instruction: 'Press the green Start call button.',
    targetDescription: "Large green button reading Start call with a camera icon, in the right-hand pane below Lily's name",
    expectedOutcome:
      'A screen titled "Ready to join?" appears with a camera preview, Camera and Microphone switches, a large blue Join button and a Cancel button.',
    hints: {
      l1: 'The big green button says Start call. Pressing it is like picking up the phone to ring Lily, only with a picture too.',
      l2: 'Press the large green Start call button.',
      l3: "On the right-hand side, under Lily's name: a big green button with a camera.",
    },
    safetyCritical: false,
  },
  {
    id: 'video_call.join',
    groundId: 'video.precall.join',
    instruction: 'Press the blue Join button to begin the call.',
    targetDescription:
      'Large blue button reading Join, below the camera preview and the switches on the Ready to join screen (not the small Join button in the contacts toolbar)',
    expectedOutcome:
      'The call screen fills the window: Lily\'s picture, her name top-left, "Connected" under it, a timer top-right counting up, and a bottom row of controls ending with a red Leave button. (It says "Calling..." for about two seconds first.)',
    hints: {
      l1: 'This is the ready screen, like checking your hair before a photo. The big blue Join button starts the call for real.',
      l2: 'Press the big blue Join button.',
      l3: 'Under the picture of you: a large blue button. Not the small Join up in the top bar.',
    },
    safetyCritical: false,
  },
  {
    id: 'video_call.leave',
    groundId: 'video.call.hangup',
    instruction: 'When you have finished talking, press the red Leave button.',
    targetDescription:
      'Red button with a white phone-handset icon and the word Leave, right-most button in the bottom control bar of the call screen',
    expectedOutcome: 'A "Call ended" screen says how long the call lasted and offers Call Lily again and Back to contacts.',
    hints: {
      l1: 'When you are finished, the red Leave button hangs up, like putting the phone back down.',
      l2: 'Press the red Leave button at the bottom right.',
      l3: 'Bottom row of the call screen, far right: a red button with a phone on it.',
    },
    safetyCritical: false,
  },
]

const SPOT_SCAM: StaticStep[] = [
  {
    id: 'spot_scam.open_messages',
    groundId: 'desk.icon.messages',
    instruction: 'Open the Messages app on your desktop.',
    targetDescription:
      'Blue rounded-square icon with a white speech bubble and a small red 1 badge, label Messages, second icon in the left-hand column of the desktop',
    expectedOutcome:
      'The Messages window is open; the conversation list shows Aldermoor Bank at the top in bold with a blue dot; the right pane says "Select a conversation to read it."',
    hints: {
      l1: 'This speech bubble is your text messages. The little red 1 means there is one you have not read yet.',
      l2: 'Click the blue Messages icon in the left-hand column.',
      l3: 'Left edge of the screen, second icon down: blue with a speech bubble and a red 1.',
    },
    safetyCritical: false,
    analogy: SKILLS.spot_scam.analogy,
  },
  {
    id: 'spot_scam.open_text',
    groundId: 'messages.conv.scam',
    instruction: 'Click the Aldermoor Bank message to read it.',
    targetDescription: 'Top row of the conversation list, name Aldermoor Bank in bold with a blue unread dot and a preview starting URGENT',
    expectedOutcome:
      'The message opens on the right: sender Aldermoor Bank, number +44 7700 900482, and a grey bubble saying the account is LOCKED with a blue underlined web address.',
    hints: {
      l1: 'The name in bold at the top is the unread one. Reading a message is safe. It is tapping the links inside that needs care.',
      l2: 'Click the Aldermoor Bank message at the top of the list.',
      l3: 'Top of the list, in bold, with a blue dot and a preview that begins URGENT.',
    },
    safetyCritical: false,
  },
  {
    id: 'spot_scam.inspect',
    groundId: 'messages.msg.scam.0',
    instruction: 'Read it carefully, but do not tap the blue link.',
    targetDescription:
      'The grey message bubble from Aldermoor Bank (the blue underlined web address inside it is messages.link.scam: point at it, never click it)',
    expectedOutcome:
      'Nothing changes on screen and no pop-up appears (the link was not clicked). The learner can name warning signs: urgency, threat of frozen money, odd web address.',
    hints: {
      l1: 'Read it slowly. It is in a big hurry, it threatens your money, and the web address looks odd. That is how a stranger at the door behaves. We do not tap the blue link.',
      l2: 'Read the message, but do not tap the blue link. What is it rushing you to do?',
      l3: 'Look at the words: urgent, locked, a deadline. A real bank would not rush you like this.',
    },
    safetyCritical: true,
  },
  {
    id: 'spot_scam.open_menu',
    groundId: 'messages.thread.menu',
    instruction: 'Open the three-dots menu at the top right of the message.',
    targetDescription: 'Small round button with three dots in the top-right corner of the open conversation, next to the sender name',
    expectedOutcome: 'A small menu drops down with Report junk, Block this number and Delete conversation.',
    hints: {
      l1: 'The three dots hide the choices for this message.',
      l2: 'Click the three dots at the top right of the message.',
      l3: 'Top right corner of the message: a small round button with three dots.',
    },
    safetyCritical: false,
  },
  {
    id: 'spot_scam.report',
    groundId: 'messages.thread.report',
    instruction: 'Choose Report junk.',
    targetDescription: 'First item, Report junk with a warning-triangle icon, in the dropdown under the three-dots button',
    expectedOutcome: 'The menu closes and an amber banner reads "Reported as junk. This number is now blocked."',
    hints: {
      l1: 'Report junk tells your phone this is a trick, and blocks that number so it cannot message you again.',
      l2: 'Choose Report junk, the first item in the little menu.',
      l3: 'First choice in the menu, with a small warning triangle.',
    },
    safetyCritical: false,
  },
]

const BIGGER_TEXT: StaticStep[] = [
  {
    id: 'bigger_text.open_settings',
    groundId: 'desk.icon.settings',
    instruction: 'Open the Settings app on your desktop.',
    targetDescription:
      'Grey rounded-square icon with a white gear symbol and the label Settings, third icon in the left-hand column of the desktop',
    expectedOutcome:
      'The Settings window is open on General: a list on the left (General, Display, Sound, Notifications, Privacy, Advanced) and language/time rows on the right.',
    hints: {
      l1: 'The grey gear is Settings, the place where you change how the computer looks and behaves. I will point to it, and then you click it.',
      l2: 'Click the grey gear icon, third down on the left.',
      l3: 'Left edge of the screen, third icon: grey with a little gear.',
    },
    safetyCritical: false,
    analogy: SKILLS.bigger_text.analogy,
  },
  {
    id: 'bigger_text.open_display',
    groundId: 'settings.nav.display',
    instruction: 'Click Display in the list on the left.',
    targetDescription: 'Second item, Display with a monitor icon, in the vertical list on the left of the Settings window',
    expectedOutcome: 'The Display panel shows a Text size card with a Smaller button, a slider, a Larger button and the readout "100% · Default".',
    hints: {
      l1: 'Display means how the screen looks. The Text size control lives in there.',
      l2: 'Click Display, second in the list on the left.',
      l3: 'In the list inside the Settings window, second item down: it has a little monitor.',
    },
    safetyCritical: false,
  },
  {
    id: 'bigger_text.make_bigger',
    groundId: 'settings.text_larger',
    instruction: 'Press the Larger button once to make the text bigger.',
    targetDescription: 'Button with a big letter A and the word Larger, to the right of the slider inside the Text size card',
    expectedOutcome:
      'Every piece of text on screen, including the top bar and the window, is visibly bigger (125%). The readout says "125% · Large".',
    hints: {
      l1: 'Larger works like turning a volume knob up, but for the writing. One press and everything gets bigger. You can always press Smaller to go back.',
      l2: 'Press the Larger button once, to the right of the slider.',
      l3: 'In the Text size card: a button with a big letter A, right of the slider.',
    },
    safetyCritical: false,
  },
]

const STEPS: Record<BuiltinSkillId, StaticStep[]> = { video_call: VIDEO_CALL, spot_scam: SPOT_SCAM, bigger_text: BIGGER_TEXT }

let seq = 0

export function fallbackPlan(skillId: BuiltinSkillId, goal?: string): LessonPlan {
  const steps: LessonStep[] = STEPS[skillId].map(({ groundId: _groundId, ...step }, index) => ({
    ...step,
    index,
    instruction: truncateWords(step.instruction),
  }))
  return {
    lessonId: `fallback-${skillId}-${++seq}`,
    skillId,
    goal: goal?.trim() || SKILLS[skillId].name,
    steps,
  }
}

// Step id -> the Practice Desktop's data-ground-id. For QA, the grounding benchmark and the stage fallback.
export const FALLBACK_GROUND_IDS: Record<string, string> = Object.fromEntries(
  Object.values(STEPS).flatMap((steps) => steps.map((s) => [s.id, s.groundId] as const)),
)

// When Argon cannot plan a novel goal in time: one honest step that just points at what was asked about.
// Never a built-in lesson that does not match the goal.
export function pointerPlan(goal: string): LessonPlan {
  const what = goal.trim().replace(/\s+/g, ' ').slice(0, 120) || 'what you asked about'
  return {
    lessonId: `pointer-${++seq}`,
    skillId: 'custom',
    goal: what,
    steps: [
      {
        id: 'custom.point',
        index: 0,
        instruction: truncateWords(`Here is where to look for: ${what}`),
        targetDescription: what,
        expectedOutcome: `The learner has done what they asked: ${what}`,
        hints: {
          l1: 'I will point to the part of the screen to look at. You do the clicking.',
          l2: 'Look where the arrow points.',
          l3: 'Look at the highlighted part of the screen.',
        },
        safetyCritical: false,
      },
    ],
  }
}
