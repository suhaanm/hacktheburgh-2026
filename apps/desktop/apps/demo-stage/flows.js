/* Lesson-flow ground truth for the Practice Desktop.
 * `after` is the fixture route (see README) that shows the screen AFTER that step is completed.
 * `start` is the fixture shown before step 1. window.__stage.setStep(flowId, n) jumps to the state after step n (0 = start). */
window.STAGE_FLOWS = {
  video_call: {
    skillId: 'video_call',
    goal: 'Start a video call with Lily',
    start: 'desktop',
    steps: [
      {
        index: 1, id: 'video_call.open_app', targetId: 'desk.icon.video', safetyCritical: false,
        instruction: 'Open the VideoChat app on your desktop.',
        targetDescription: 'Teal rounded-square icon with a white video-camera symbol and the label VideoChat, first icon in the left-hand column of the desktop',
        expectedOutcome: 'The VideoChat window is open: a contacts list on the left (Dave Morgan, Lily, Priya Shah, Riverside Surgery, Rosa Bell, Tom) and "Select a contact" text on the right.',
        after: 'video/contacts'
      },
      {
        index: 2, id: 'video_call.pick_lily', targetId: 'video.contact.lily', safetyCritical: false,
        instruction: 'Click Lily in your contacts list.',
        targetDescription: 'Row labelled Lily with the subtitle Granddaughter and a green dot, second row in the contacts list on the left of the VideoChat window',
        expectedOutcome: 'Lily\'s row is highlighted and the right-hand pane shows a large avatar, the name Lily, "Granddaughter", and a large green Start call button.',
        after: 'video/lily'
      },
      {
        index: 3, id: 'video_call.start_call', targetId: 'video.start_call', safetyCritical: false,
        instruction: 'Press the green Start call button.',
        targetDescription: 'Large green button reading Start call with a camera icon, in the right-hand pane below Lily\'s name',
        expectedOutcome: 'A screen titled "Ready to join?" appears with a camera preview, Camera and Microphone switches, a large blue Join button and a Cancel button.',
        after: 'video/precall'
      },
      {
        index: 4, id: 'video_call.join', targetId: 'video.precall.join', safetyCritical: false,
        instruction: 'Press the blue Join button to begin the call.',
        targetDescription: 'Large blue button reading Join, below the camera preview and the switches on the Ready to join screen (not the small Join button in the contacts toolbar)',
        expectedOutcome: 'The call screen fills the window: Lily\'s picture, her name top-left, "Connected" under it, a timer top-right counting up, and a bottom row of controls ending with a red Leave button. (It says "Calling..." for about two seconds first.)',
        after: 'video/call-screen'
      },
      {
        index: 5, id: 'video_call.leave', targetId: 'video.call.hangup', safetyCritical: false,
        instruction: 'When you have finished talking, press the red Leave button.',
        targetDescription: 'Red button with a white phone-handset icon and the word Leave, right-most button in the bottom control bar of the call screen',
        expectedOutcome: 'A "Call ended" screen says how long the call lasted and offers Call Lily again and Back to contacts.',
        after: 'video/ended'
      }
    ]
  },

  spot_scam: {
    skillId: 'spot_scam',
    goal: 'Check whether a text message is a scam',
    start: 'desktop/scam',
    steps: [
      {
        index: 1, id: 'spot_scam.open_messages', targetId: 'desk.icon.messages', safetyCritical: false,
        instruction: 'Open the Messages app on your desktop.',
        targetDescription: 'Blue rounded-square icon with a white speech bubble and a small red 1 badge, label Messages, second icon in the left-hand column of the desktop',
        expectedOutcome: 'The Messages window is open; the conversation list shows Aldermoor Bank at the top in bold with a blue dot; the right pane says "Select a conversation to read it."',
        after: 'messages/scam-list'
      },
      {
        index: 2, id: 'spot_scam.open_text', targetId: 'messages.conv.scam', safetyCritical: false,
        instruction: 'Click the Aldermoor Bank message to read it.',
        targetDescription: 'Top row of the conversation list, name Aldermoor Bank in bold with a blue unread dot and a preview starting URGENT',
        expectedOutcome: 'The message opens on the right: sender Aldermoor Bank, number +44 7700 900482, and a grey bubble saying the account is LOCKED with a blue underlined web address.',
        after: 'messages/scam'
      },
      {
        index: 3, id: 'spot_scam.inspect', targetId: 'messages.msg.scam.0', safetyCritical: true,
        instruction: 'Read it carefully, but do not tap the blue link.',
        targetDescription: 'The grey message bubble from Aldermoor Bank (the blue underlined web address inside it is messages.link.scam: point at it, never click it)',
        expectedOutcome: 'Nothing changes on screen and no pop-up appears (the link was not clicked). The learner can name warning signs: urgency, threat of frozen money, odd web address.',
        after: 'messages/scam'
      },
      {
        index: 4, id: 'spot_scam.open_menu', targetId: 'messages.thread.menu', safetyCritical: false,
        instruction: 'Open the three-dots menu at the top right of the message.',
        targetDescription: 'Small round button with three dots in the top-right corner of the open conversation, next to the sender name',
        expectedOutcome: 'A small menu drops down with Report junk, Block this number and Delete conversation.',
        after: 'messages/scam/menu'
      },
      {
        index: 5, id: 'spot_scam.report', targetId: 'messages.thread.report', safetyCritical: false,
        instruction: 'Choose Report junk.',
        targetDescription: 'First item, Report junk with a warning-triangle icon, in the dropdown under the three-dots button',
        expectedOutcome: 'The menu closes and an amber banner reads "Reported as junk. This number is now blocked."',
        after: 'messages/scam/reported'
      }
    ]
  },

  bigger_text: {
    skillId: 'bigger_text',
    goal: 'Make the text on the screen bigger',
    start: 'desktop',
    steps: [
      {
        index: 1, id: 'bigger_text.open_settings', targetId: 'desk.icon.settings', safetyCritical: false,
        instruction: 'Open the Settings app on your desktop.',
        targetDescription: 'Grey rounded-square icon with a white gear symbol and the label Settings, third icon in the left-hand column of the desktop',
        expectedOutcome: 'The Settings window is open on General: a list on the left (General, Display, Sound, Notifications, Privacy, Advanced) and language/time rows on the right.',
        after: 'settings'
      },
      {
        index: 2, id: 'bigger_text.open_display', targetId: 'settings.nav.display', safetyCritical: false,
        instruction: 'Click Display in the list on the left.',
        targetDescription: 'Second item, Display with a monitor icon, in the vertical list on the left of the Settings window',
        expectedOutcome: 'The Display panel shows a Text size card with a Smaller button, a slider, a Larger button and the readout "100% \u00b7 Default".',
        after: 'settings/display'
      },
      {
        index: 3, id: 'bigger_text.make_bigger', targetId: 'settings.text_larger', safetyCritical: false,
        instruction: 'Press the Larger button once to make the text bigger.',
        targetDescription: 'Button with a big letter A and the word Larger, to the right of the slider inside the Text size card',
        expectedOutcome: 'Every piece of text on screen, including the top bar and the window, is visibly bigger (125%). The readout says "125% \u00b7 Large".',
        after: 'settings/display/size/1'
      }
    ]
  }
};
