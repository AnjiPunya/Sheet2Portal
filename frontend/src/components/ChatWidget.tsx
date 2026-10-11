import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelAction, confirmAction } from '../api/actions'
import { sendChatMessage, fetchChatSuggestions, type ActionContext } from '../api/chat'
import { ApiRequestError } from '../api/client'
import { changedData, nextActionState, pendingFrom } from '../lib/actionState'
import { invalidateWorkbookData } from '../lib/invalidate'
import type { ActionResult, ActionState } from '../types/actions'
import type { ChatMessage, ChatReference } from '../types/chat'
import { ActionDraftCard } from './ActionDraftCard'
import { ChatMarkdown } from './ChatMarkdown'
import { ChatReferences } from './ChatReferences'
import { VoiceAssistant } from './VoiceAssistant'

interface DisplayMessage extends ChatMessage {
  references?: ChatReference[]
}

function newConversationId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
  }
}

export function ChatWidget({
  workbookId,
  portalTitle,
}: {
  workbookId: string
  portalTitle: string
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  // Business actions: one conversation id per chat thread (drafts are scoped
  // to it server-side) and the draft currently on screen.
  const [conversationId, setConversationId] = useState(newConversationId)
  const [action, setAction] = useState<ActionState | null>(null)
  const actionContext: ActionContext = { conversationId, pendingAction: pendingFrom(action) }

  function applyAction(incoming: ActionState | null | undefined) {
    setAction((prev) => nextActionState(prev, incoming))
    if (changedData(incoming)) invalidateWorkbookData(queryClient, workbookId)
  }

  const suggestionsQuery = useQuery({
    queryKey: ['chat-suggestions', workbookId],
    queryFn: () => fetchChatSuggestions(workbookId),
    enabled: isOpen,
    staleTime: Infinity,
  })

  const sendMutation = useMutation({
    mutationFn: ({ history, context }: { history: ChatMessage[]; context: ActionContext }) => sendChatMessage(workbookId, history, context),
    onSuccess: (response) => {
      setMessages((prev) => [...prev, { role: 'assistant', content: response.message, references: response.references }])
      applyAction(response.action)
    },
  })

  const decideMutation = useMutation({
    mutationFn: ({ decision, draft }: { decision: 'confirm' | 'cancel'; draft: ActionState }): Promise<ActionResult> =>
      decision === 'confirm'
        ? confirmAction(workbookId, draft.draft_id!, draft.token!, conversationId)
        : cancelAction(workbookId, draft.draft_id!, conversationId),
    onSuccess: (result) => {
      setMessages((prev) => [...prev, { role: 'assistant', content: result.message }])
      applyAction(result.action)
    },
  })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sendMutation.isPending, action])

  function ask(question: string) {
    const trimmed = question.trim()
    if (!trimmed || sendMutation.isPending) return
    const next: DisplayMessage[] = [...messages, { role: 'user', content: trimmed }]
    setMessages(next)
    setInput('')
    sendMutation.mutate({ history: next.map(({ role, content }) => ({ role, content })), context: actionContext })
  }

  function newConversation() {
    setMessages([])
    sendMutation.reset()
    decideMutation.reset()
    setAction(null)
    setConversationId(newConversationId())
  }

  const failure = sendMutation.error ?? decideMutation.error
  const error = failure instanceof ApiRequestError ? failure : null

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-label={isOpen ? 'Close chat' : 'Open chat'}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-indigo-700"
      >
        {isOpen ? (
          <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M18 10c0 3.866-3.582 7-8 7a9.06 9.06 0 01-2.347-.306c-.584.296-1.925.864-4.181 1.234-.2.032-.352-.176-.273-.362.354-.836.674-1.95.77-2.966C2.249 13.187 1 11.712 1 10c0-3.866 3.582-7 8-7s9 3.134 9 7z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </button>

      {isOpen && (
        <div className="fixed bottom-24 right-5 z-40 flex h-[32rem] w-[22rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl sm:w-96">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Ask about this data</p>
              <p className="truncate text-xs text-slate-400" title={portalTitle}>
                {portalTitle}
              </p>
            </div>
            <button onClick={newConversation} className="text-xs text-indigo-600 hover:underline">
              New conversation
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.length === 0 && (
              <div className="space-y-3">
                <p className="text-sm text-slate-400">
                  Ask a question about the uploaded data -- totals, overdue items, pending approvals, and more.
                </p>
                {suggestionsQuery.data && suggestionsQuery.data.suggestions.length > 0 && (
                  <div className="flex flex-col gap-1.5">
                    {suggestionsQuery.data.suggestions.map((q) => (
                      <button
                        key={q}
                        onClick={() => ask(q)}
                        className="rounded-lg border border-slate-200 px-3 py-1.5 text-left text-sm text-slate-600 hover:border-indigo-300 hover:bg-indigo-50"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                    m.role === 'user' ? 'whitespace-pre-wrap bg-indigo-600 text-white' : 'bg-slate-100 text-slate-800'
                  }`}
                >
                  {m.role === 'assistant' ? <ChatMarkdown text={m.content} /> : m.content}
                  {m.references && m.references.length > 0 && <ChatReferences references={m.references} />}
                </div>
              </div>
            ))}

            {action && (
              <ActionDraftCard
                action={action}
                busy={sendMutation.isPending || decideMutation.isPending}
                onConfirm={() => decideMutation.mutate({ decision: 'confirm', draft: action })}
                onCancel={() => decideMutation.mutate({ decision: 'cancel', draft: action })}
                onChoose={(candidate) => ask(candidate.label)}
              />
            )}

            {sendMutation.isPending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-400">Thinking…</div>
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                {error.message}
              </div>
            )}
          </div>

          <VoiceAssistant
            workbookId={workbookId}
            history={messages}
            disabled={sendMutation.isPending || decideMutation.isPending}
            actionContext={actionContext}
            onAction={applyAction}
            onTranscript={(text) => setMessages((prev) => [...prev, { role: 'user', content: text }])}
            onReply={(reply) =>
              setMessages((prev) => [...prev, { role: 'assistant', content: reply.message, references: reply.references }])
            }
          />

          <form
            onSubmit={(e) => {
              e.preventDefault()
              ask(input)
            }}
            className="flex items-center gap-2 border-t border-slate-100 p-3"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question…"
              disabled={sendMutation.isPending}
              className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={sendMutation.isPending || !input.trim()}
              className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </>
  )
}
