# Requirements Document

## Introduction

This feature redesigns the JimsAI chat frontend from a monolithic single-file page (`frontend/app/user/page.tsx`) into a modern, componentised chat UI modelled after Claude and Cursor. The redesign introduces an icon-only sidebar, Claude-style message bubbles with full GFM markdown, a per-message Response Insights bottom drawer, a floating composer, and full mobile-first responsive layout — all backed by a Zustand store.

**Three key improvements over the initial design:**
1. Thread storage is online-first via the backend API (`/v1/chat/threads`, `/v1/chat/threads/{id}/messages`) — no localStorage for chat data. Threads auto-name from the first message and support inline rename.
2. Learn/unlearn/feedback use the exact backend request models: `FeedbackRequest` with `source_signature_ids`, `TrainingIngestRequest` with `source_trust` and `domain_hint`, `MemoryDeleteRequest` with `signature_id`.
3. On mobile, the sidebar collapses to a single hamburger `☰` icon in the top bar. Tapping it opens a full-width drawer with icon+text labels, profile info, and sign-out — not a bottom tab bar.

## Glossary

- **ChatLayout**: Root layout component: Sidebar + main column (MessageList + Composer).
- **Composer**: Floating textarea at the bottom of the chat area.
- **InsightsDrawer**: Per-message bottom-sheet drawer showing Answer State, Sources, Reasoning, Simulation, Capability, Gaps, Memory Controls.
- **MessageBubble**: Single rendered message with action row.
- **MessageList**: Scrollable container for all MessageBubble items in the active thread.
- **MarkdownRenderer**: Component that renders GFM markdown with code blocks, tables, images.
- **Sidebar**: 52px icon-only left column with slide-out panels (desktop only).
- **MobileNav**: Hamburger button in top bar on mobile that opens a full-width drawer navigation.
- **MobileDrawerNav**: Full-width slide-in navigation drawer on mobile — icon+text, profile, sign-out.
- **ThreadsPanel**: Slide-out panel from Sidebar showing searchable thread history.
- **LearnPanel**: Slide-out panel for quick workspace content ingestion.
- **Store**: Zustand store at `store.ts` holding all shared UI and API state.
- **ApiResponse**: Full JSON from `POST /v1/query`.
- **Thread**: `{ id, title, updated_at, created_at }` from the backend.
- **Message**: `{ role, content, apiResponse? }` entry in a thread.
- **FeedbackRequest**: `{ user_id, trace_id, rating, notes, workspace_id, thread_id, source_signature_ids }`.
- **TrainingIngestRequest**: `{ user_id, content, modality, source_trust, domain_hint, workspace_id }`.
- **MemoryDeleteRequest**: `{ user_id, signature_id, workspace_id, reason }`.

---

## Requirements

### Requirement 1: Layout and Shell

**User Story:** As a user, I want a clean, modern chat layout that feels like Claude or Cursor, so that I can focus on the conversation without visual clutter.

#### Acceptance Criteria

1. THE ChatLayout SHALL render a `flex-row` root containing a Sidebar (52px) and a main content column; on viewports less than 768px the Sidebar SHALL be hidden.
2. THE main content column SHALL have a scrollable MessageList occupying all remaining height and a fixed Composer at the bottom.
3. THE ChatLayout SHALL replace the existing `chatWorkspace` / `insightRail` grid layout entirely.
4. WHEN the viewport width is less than 768px, THE ChatLayout SHALL render a top bar containing the JimsAI logo mark and a single hamburger icon button — no bottom tab bar.
5. THE ChatLayout SHALL render without horizontal scroll at any viewport width from 320px to 2560px.
6. THE InsightsDrawer SHALL be rendered at the ChatLayout root level so it overlays the entire viewport.

---

### Requirement 2: Sidebar (Desktop — ≥ 768px)

**User Story:** As a desktop user, I want an icon-only sidebar, so that I can navigate threads, teaching, and account without visual noise.

#### Acceptance Criteria

1. THE Sidebar SHALL be 52px wide and always visible on viewports 768px and wider.
2. THE Sidebar SHALL display the JimsAI "J" logo mark at the top.
3. WHEN a user clicks the `+` button, THE Store SHALL create a new thread locally with a temporary title "New chat", set it as active, and immediately POST `GET /v1/chat/threads` on next load to sync.
4. WHEN a user clicks the chat history icon, THE Sidebar SHALL toggle the ThreadsPanel.
5. WHEN a user clicks the Learn icon (`BookOpen`), THE Sidebar SHALL toggle the LearnPanel.
6. THE Sidebar SHALL display a user avatar circle at the bottom with the user's initials.
7. WHEN the avatar is clicked, THE Sidebar SHALL sign the user out and redirect to the sign-in screen.
8. THE Sidebar SHALL show no text labels — icon buttons with `title` tooltips only.
9. WHEN the ThreadsPanel is open, it SHALL render as a 280px panel to the right of the Sidebar with: "Chats" heading, "New chat" button, search input, and a scrollable thread list ordered by `updated_at` descending.
10. WHEN a user types in the search input, THE ThreadsPanel SHALL filter threads client-side by title (case-insensitive).
11. WHEN a user clicks a thread, THE Store SHALL set that thread as active and close the ThreadsPanel.
12. WHEN the user hovers a thread item, a rename icon SHALL appear; clicking it SHALL show an inline text input pre-filled with the thread title; pressing Enter or blurring SHALL save the new title via `PATCH /v1/chat/threads/{thread_id}/rename` if that endpoint exists, otherwise update the title in Store only.
13. WHEN the LearnPanel is open, it SHALL render a 280px panel with a textarea and "Teach workspace" button.
14. WHEN "Teach workspace" is submitted with non-empty content, THE LearnPanel SHALL POST to `/v1/training/ingest` with `{ user_id, workspace_id, content, modality: "text", source_trust: 0.80, domain_hint: "user_teach_workspace" }` and display the result status.

---

### Requirement 3: Mobile Navigation (< 768px)

**User Story:** As a mobile user, I want a single hamburger menu, so that I can access all navigation without a complex bottom tab bar.

#### Acceptance Criteria

1. WHEN the viewport width is less than 768px, THE ChatLayout SHALL show a top bar with: JimsAI logo mark (left), active thread title (center, truncated), and a hamburger `☰` icon button (right).
2. WHEN the hamburger button is clicked, THE ChatLayout SHALL render a full-width slide-in navigation drawer from the left with a backdrop overlay.
3. THE MobileDrawerNav SHALL display a header with the JimsAI "J" logo mark and a close `✕` button.
4. THE MobileDrawerNav SHALL display the following navigation items as rows with icon + text label:
   - `+` New Chat (creates new thread, closes drawer)
   - `MessageSquare` Thread History (shows thread list inline within drawer)
   - `BookOpen` Teach Workspace (shows inline learn form within drawer)
5. WHEN "Thread History" is tapped in MobileDrawerNav, the drawer SHALL show an inline searchable thread list replacing the navigation items, with a back arrow to return.
6. WHEN "Teach Workspace" is tapped in MobileDrawerNav, the drawer SHALL show an inline learn form with textarea and submit button, with a back arrow.
7. THE MobileDrawerNav SHALL display a section at the bottom with: user email, user initials avatar, and a "Sign out" button.
8. WHEN the backdrop overlay is clicked, THE MobileDrawerNav SHALL close.
9. THE MobileDrawerNav SHALL have width 80% of viewport (max 320px) and full height, with overflow-y auto.
10. WHEN a thread is selected from the inline thread list, THE MobileDrawerNav SHALL close and THE Store SHALL set the selected thread as active.

---

### Requirement 4: Thread Storage — Online First

**User Story:** As a user, I want my conversation history stored and synced with my account online, so that I can access it from any device and never lose it.

#### Acceptance Criteria

1. WHEN the app loads and the user is authenticated, THE Store SHALL fetch threads from `GET /v1/chat/threads?user_id={userId}&workspace_id={workspaceId}&limit=50` and populate the threads list.
2. WHEN a thread is selected and the thread's messages have not yet been loaded, THE Store SHALL fetch messages from `GET /v1/chat/threads/{thread_id}/messages?user_id={userId}&limit=200` and store them.
3. WHEN a new query is submitted, THE Store SHALL use the `thread_id` in the `POST /v1/query` request body; THE backend saves the exchange via `save_chat_exchange` — no separate save call is needed.
4. WHEN a query completes successfully and the active thread's title is still "New chat" or empty, THE Store SHALL set the thread title to the first 48 characters of the query (trimmed), display it in the ThreadsPanel, and persist it client-side; the backend sets the real title in Supabase from `save_chat_exchange`.
5. THE Store SHALL NOT use `localStorage` for thread list or message storage — all thread and message data SHALL be fetched from the backend; the only permissible localStorage use is `activeThreadId` so the last-used thread can be restored on reload.
6. WHEN a thread is deleted via the delete icon in the ThreadsPanel, THE Store SHALL call `DELETE /v1/chat/threads/{thread_id}` with `{ user_id }` body and remove the thread from Store.
7. WHEN a thread title is renamed inline (Requirement 2, criterion 12), the new title SHALL be stored in the Store immediately for optimistic display.
8. WHEN the user is not authenticated or the backend is unavailable, THE Store SHALL display an empty thread list and show a status message — it SHALL NOT crash or attempt localStorage fallback for messages.

---

### Requirement 5: Message Bubbles

**User Story:** As a user, I want messages rendered as styled chat bubbles with rich markdown, so that I can read formatted responses clearly.

#### Acceptance Criteria

1. WHEN a user message is rendered, THE MessageBubble SHALL be right-aligned with an accent-colored background.
2. WHEN an assistant message is rendered, THE MessageBubble SHALL be left-aligned with a surface-colored background.
3. THE MarkdownRenderer SHALL render fenced code blocks as a dark `<pre><code>` block with language label header and a copy-to-clipboard button.
4. THE MarkdownRenderer SHALL render GFM tables with bordered cells and alternating row background.
5. THE MarkdownRenderer SHALL render inline code with monospace font and distinct background.
6. THE MarkdownRenderer SHALL render `**bold**`, `*italic*`, `~~strikethrough~~` using correct HTML elements.
7. THE MarkdownRenderer SHALL render blockquotes with a left accent border and muted color.
8. THE MarkdownRenderer SHALL render unordered and ordered lists with correct indentation and markers.
9. THE MarkdownRenderer SHALL render `![alt](url)` as an `<img>` with `loading="lazy"` and max-width constrained.
10. THE MarkdownRenderer SHALL render `#`, `##`, `###` headings with appropriately scaled sizes.
11. WHEN the copy button on a code block is clicked, it SHALL write the code to clipboard and show a `Check` icon for 1400ms before reverting.
12. WHEN an assistant message is rendered, THE MessageBubble SHALL display an action row below the bubble: copy, thumbs up, thumbs down, Insights, regenerate.
13. WHEN copy is clicked in the action row, THE MessageBubble SHALL write the plain text of `message.content` to the clipboard.
14. WHEN thumbs up is clicked, THE Store SHALL call `POST /v1/feedback` with `FeedbackRequest`:
    ```json
    { "user_id": "...", "trace_id": "...", "rating": "positive", "notes": "", "workspace_id": "...", "thread_id": "...", "source_signature_ids": ["sig1", "sig2"] }
    ```
    where `source_signature_ids` is populated from `message.apiResponse.sources`.
15. WHEN thumbs down is clicked, THE Store SHALL call `POST /v1/feedback` with `rating: "negative"` and the same `source_signature_ids` from `message.apiResponse.sources`.
16. WHEN regenerate is clicked, THE Store SHALL re-submit the preceding user message to `POST /v1/query` and replace the current assistant message with the new response.
17. WHEN the Insights button is clicked, THE Store SHALL set `drawerOpen: true`, `drawerMessageIndex` to the message index, and `drawerTab` to `"answer"`.

---

### Requirement 6: Response Insights Drawer

**User Story:** As a user, I want to inspect the full reasoning trace and control what JimsAI learns from each response, so that I understand and shape its knowledge.

#### Acceptance Criteria

1. WHEN `drawerOpen` is `true`, THE InsightsDrawer SHALL render as a bottom sheet with a backdrop.
2. THE InsightsDrawer SHALL have a drag handle at top center and a close `✕` button at top right.
3. WHEN the close button or backdrop is clicked, THE InsightsDrawer SHALL set `drawerOpen: false`.
4. THE InsightsDrawer SHALL occupy 50% viewport height on ≥ 768px and 80% on < 768px.
5. Tabs (horizontally scrollable): **Answer State** | **Sources** | **Reasoning** | **Simulation** | **Capability** | **Gaps** | **Memory Controls**.
6. **Answer State tab**: confidence (large), sources count, gaps count, capability kind — using metric card grid.
7. **Sources tab**: each source ID from `message.apiResponse.sources` as a pill. Each pill has a "Learn" button that, when clicked, calls:
   ```
   POST /v1/training/ingest
   { user_id, workspace_id, content: sourceId, modality: "text", source_trust: 0.85, domain_hint: "user_confirm_source" }
   ```
   and an "Unlearn" button (shown after Learn succeeds) that calls:
   ```
   POST /v1/memory/delete
   { user_id, workspace_id, signature_id: returnedSignatureId, reason: "user_unlearn_source" }
   ```
8. **Reasoning tab**: `message.apiResponse.layer_results` — each layer with activated dot, name, deterministic/bounded label, summary.
9. **Simulation tab**: `message.apiResponse.simulation_results` — each with scenario name and pass ✓ / fail ✗ badge.
10. **Capability tab**: `message.apiResponse.capability_plan` fields + `capability_results` list.
11. **Gaps tab**: `message.apiResponse.gaps` — each as a warning-styled item.
12. **Memory Controls tab**:
    - "Learn this response" button → calls:
      ```
      POST /v1/training/ingest
      { user_id, workspace_id, content: message.content, modality: "text", source_trust: min(0.98, max(0.5, message.apiResponse.confidence)), domain_hint: "learn_this_user_confirmed" }
      ```
      then calls `POST /v1/feedback` with `{ rating: "positive", notes: "learn_this", source_signature_ids: message.apiResponse.sources }`.
    - After success: show "Unlearn" button that calls `POST /v1/memory/delete` with the returned `signature.id`.
    - Shows `trace_id` as a reference code.
    - Shows current `feedbackStatus` from Store.
13. THE InsightsDrawer SHALL render a backdrop that closes the drawer when clicked.

---

### Requirement 7: Composer

**User Story:** As a user, I want a polished floating input at the bottom of the screen for typing and sending messages easily.

#### Acceptance Criteria

1. THE Composer SHALL render as a floating rounded-rectangle box centered horizontally, max-width 760px, with elevated shadow.
2. Left: attachment `Paperclip` button → triggers hidden `<input type="file">`.
3. Center: auto-resizing `<textarea>` with placeholder "Ask JimsAI anything…", grows to 220px max.
4. WHEN Enter is pressed without Shift, THE Composer SHALL submit.
5. WHEN Shift+Enter is pressed, THE Composer SHALL insert a newline without submitting.
6. Bottom-right row: canvas hint toggle, invention hint toggle, model label `"Qwen3"`, send button.
7. WHEN canvasHint is toggled active, `canvas_hint: true` is sent in the query body; same for inventionHint.
8. WHEN send is clicked with non-empty input, THE Store SHALL append user message, set loading, POST to `/v1/query`, append assistant message with full `apiResponse`, clear loading.
9. WHEN file is selected, file text is appended to textarea.
10. WHEN `loading: true`, the send button is disabled.
11. WHEN viewport < 768px, the Composer is full-width and sticks to the bottom, above the MobileNav top bar.

---

### Requirement 8: State Management

**User Story:** As a developer, I want a Zustand store managing all shared state cleanly, with online-first thread data.

#### Acceptance Criteria

1. THE Store SHALL be in `frontend/app/user/store.ts`.
2. Fields: `activeThreadId`, `threads: Thread[]`, `messages: Record<string, Message[]>`, `threadsLoaded: boolean`, `messagesLoaded: Record<string, boolean>`.
3. Fields: `drawerOpen`, `drawerMessageIndex`, `drawerTab`.
4. Fields: `sidebarPanel: "threads" | "learn" | null`, `mobileNavOpen: boolean`.
5. Fields: `loading`, `feedbackStatus`, `learnedSignatureIds: Record<string, string>`.
6. Fields: `canvasHint`, `inventionHint`.
7. WHEN a Message is stored, the full `ApiResponse` SHALL be stored alongside `role` and `content`.
8. THE Store SHALL persist only `activeThreadId` to `localStorage` — no thread list or messages in localStorage.
9. WHEN the Store initialises, it SHALL restore `activeThreadId` from localStorage if present.
10. THE Store SHALL expose async actions: `loadThreads(apiBase, headers)`, `loadMessages(threadId, apiBase, headers)`, `sendQuery(input, apiBase, headers)`, `submitFeedback(rating, message, apiBase, headers)`, `learnResponse(message, apiBase, headers)`, `unlearnResponse(traceId, apiBase, headers)`.

---

### Requirement 9: Component File Structure

**User Story:** As a developer, I want well-structured small component files that are easy to navigate and extend.

#### Acceptance Criteria

1. `frontend/app/user/ChatLayout.tsx` — root layout.
2. `frontend/app/user/Sidebar.tsx` — desktop icon sidebar + ThreadsPanel + LearnPanel.
3. `frontend/app/user/MobileNav.tsx` — hamburger button + full-width drawer nav for mobile.
4. `frontend/app/user/MessageList.tsx` — scrollable message container.
5. `frontend/app/user/MessageBubble.tsx` — individual message + action row.
6. `frontend/app/user/MarkdownRenderer.tsx` — GFM markdown with `react-markdown` + `remark-gfm`.
7. `frontend/app/user/Composer.tsx` — floating input composer.
8. `frontend/app/user/InsightsDrawer.tsx` — bottom-sheet insights drawer.
9. `frontend/app/user/store.ts` — Zustand store.
10. `frontend/app/user/types.ts` — shared TypeScript types.
11. `frontend/app/user/page.tsx` — thin shell: `"use client"; import ChatLayout; export default () => <ChatLayout />`.
12. New CSS SHALL be added to `frontend/app/globals.css` without removing existing design tokens.

---

### Requirement 10: Dependencies

**User Story:** As a developer, I want minimal new dependencies for a lean bundle.

#### Acceptance Criteria

1. THE frontend SHALL add `react-markdown` and `remark-gfm` to `package.json`.
2. THE MarkdownRenderer SHALL NOT use any markdown editor library — only `react-markdown` + `remark-gfm`.
3. NO other new npm dependencies SHALL be added.

---

### Requirement 11: Mobile-First Experience

**User Story:** As a mobile user, I want native-feeling navigation and a chat UI that works on any phone.

#### Acceptance Criteria

1. WHEN viewport < 768px, THE ChatLayout SHALL hide the Sidebar and show a top bar with hamburger `☰` button.
2. WHEN the hamburger button is tapped, THE MobileDrawerNav SHALL slide in from the left with a 280px width (or 80vw, whichever is smaller) and a backdrop.
3. THE MobileDrawerNav SHALL contain nav items with icon + text label, the user's email, and a Sign Out button — it SHALL NOT be a bottom tab bar.
4. WHEN viewport < 768px, message bubbles SHALL take the full available width.
5. WHEN viewport < 768px, THE InsightsDrawer SHALL occupy 80% of viewport height.
6. THE Composer SHALL remain above the mobile keyboard using `position: sticky; bottom: 0` and appropriate `env(safe-area-inset-bottom)` padding.
7. THE ChatLayout SHALL produce no horizontal scrollbar from 320px to 767px.
