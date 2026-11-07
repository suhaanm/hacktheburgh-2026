import type { ReactElement } from 'react'
import type { CompanionState } from '../../shared/protocol'
import { AgentTray, ErrorBanner, LevelChip, SkillStepper } from '../design'
import { chatBus } from './chat/bus'
import { ChatView } from './chat/ChatView'
import { conversationFrom, useChatMessages, useChatMode } from './chat/useChat'

export interface ChatTabProps {
  state: CompanionState
  personaName: string
  onWake: () => void
  onCancelAgent: (id: string) => void
}

export function ChatTab({ state, personaName, onWake, onCancelAgent }: ChatTabProps): ReactElement {
  const bus = useChatMessages()
  const mode = useChatMode()
  const { messages, asides } = conversationFrom(bus, state.captions)
  const resting = state.phase === 'asleep' || state.phase === 'listening_for_name'

  const above = (
    <>
      {state.phase === 'error' ? <ErrorBanner message={state.lastError ?? 'Something went wrong.'} actionLabel="Try again" onAction={onWake} /> : null}
      <AgentTray agents={state.agents} onCancel={onCancelAgent} />
    </>
  )

  const empty =
    mode === 'text' ? (
      <p>Type a message to begin.</p>
    ) : resting ? (
      <>
        <p>
          Say <strong>{`“Hey ${personaName}”`}</strong>
        </p>
        <button type="button" className="al-btn al-btn--lg al-btn--primary" onClick={onWake}>
          {`Talk to ${personaName}`}
        </button>
      </>
    ) : (
      <p>I am listening.</p>
    )

  return (
    <ChatView
      messages={messages}
      asides={asides}
      mode={mode}
      onMode={(m) => chatBus.setMode(m)}
      onSend={(text) => chatBus.send(text)}
      topRight={<LevelChip level={state.level} locked={state.levelLocked} variant="compact" />}
      pinned={state.skill ? <SkillStepper name={state.skill.name} step={state.skill.step} stepCount={state.skill.stepCount} /> : undefined}
      above={above}
      empty={empty}
    />
  )
}
