# Autonomous PM – Project Overview

**Autonomous PM** is an AI-native project management platform. Work comes in from Slack, GitHub and a web
dashboard, and a team of small AI agents takes care of the routine project-manager jobs:

- triaging and prioritising tickets
- spotting duplicate reports
- breaking big tickets into sub-tasks
- writing the daily standup
- keeping ticket status in sync with GitHub
- handing a ticket to a coding agent (Claude Code, Codex or Cursor) with all the context it needs

Every change is recorded on the ticket's timeline with who made it and why, so the AI's decisions stay
explainable.

---

## Architecture at a glance

The platform is a set of small services. The **Ticket Service** is the single source of truth; every other
service reads from it or writes to it.

```mermaid
flowchart TB
    subgraph IN["Where work comes from"]
        SL["Slack Intake :3006"]
        UI["Web Dashboard :3000"]
        GH["GitHub Status :3002"]
    end

    OR["Orchestrator :3005<br/>LangGraph workflows"]
    TS[("Ticket Service :3001<br/>tickets + timeline")]

    subgraph AG["AI agents"]
        PR["Priority Agent :3003"]
        SU["Standup Agent :3004"]
        DA["Dev Agent :3007<br/>breakdown + coding sessions"]
    end

    subgraph EXT["Outside services"]
        LLM["LLM provider<br/>Gemini / OpenAI / Anthropic"]
        SLK["Slack channels"]
        CA["Coding agents<br/>Claude Code / Codex / Cursor"]
    end

    SL --> OR
    OR --> TS
    OR --> AG
    UI --> TS
    UI --> DA
    GH --> TS
    AG --> TS
    AG --> LLM
    SU --> SLK
    DA -. "brief + MCP config" .-> CA
    CA -. "MCP tools" .-> TS
```

| Service | Port | Tech | Role |
|---|---|---|---|
| Web Dashboard | 3000 | Next.js 14, Tailwind | The team's view of all work |
| Ticket Service | 3001 | Python, FastAPI, SQL/MongoDB | Tickets, timeline, links, similarity |
| GitHub Status | 3002 | Node.js, Express | Turns GitHub events into status changes |
| Priority Agent | 3003 | Python, FastAPI, LLM | Scores and prioritises open tickets |
| Standup Agent | 3004 | Python, FastAPI, LLM | Writes and posts the daily standup |
| Orchestrator | 3005 | Python, FastAPI, LangGraph | Chains the agents into workflows |
| Slack Intake | 3006 | Node.js, Slack Bolt | Creates tickets from Slack |
| Dev Agent | 3007 | Python, FastAPI, git | AI breakdown and coding-agent hand-off |

---

## Features

### 1. Ticket management (Ticket Service)

The central store for all work. Every ticket has an ID like `APM-12`, a type (bug, feature, task,
incident, …), a status, a priority, an AI priority score, an assignee and its source (Slack, dashboard,
GitHub, API). Tickets can be linked: a ticket can be a **sub-task** of another, or marked as a **duplicate** of
another. A REST API serves the dashboard, the agents and the integrations.

```mermaid
stateDiagram-v2
    [*] --> Open: created
    Open --> InProgress: work starts / PR opened / commit pushed
    InProgress --> InReview: PR ready for review
    InProgress --> Blocked: waiting on something
    Blocked --> InProgress: unblocked
    InReview --> Done: PR merged
    InReview --> Open: PR closed without merging
    Open --> Closed: closed as duplicate
    Done --> Open: issue reopened
    Done --> [*]
    Closed --> [*]

    state "In Progress" as InProgress
    state "In Review" as InReview
```

### 2. Web dashboard

A calm, professional workspace with warm pastel colours, light and dark mode, and keyboard shortcuts
(`/` to search, `n` for a new ticket).

- An overview of total, active, completed and blocked work, with a status-distribution bar.
- List and board (kanban) views with filters and search.
- A ticket side panel with three tabs: **Overview**, **Activity** and **Coding agent**.
- An Agent settings dialog for linking the codebase.

```mermaid
flowchart LR
    D["Dashboard"] --> O["Overview stats<br/>+ status bar"]
    D --> L["List / Board views<br/>filters + search"]
    D --> N["New ticket dialog<br/>live duplicate check"]
    D --> S["Agent settings<br/>linked repo, default agent"]
    L --> P["Ticket side panel"]
    P --> T1["Overview<br/>description, duplicates,<br/>AI score, sub-tasks"]
    P --> T2["Activity<br/>live timeline"]
    P --> T3["Coding agent<br/>prepare + launch session"]
```

### 3. Slack intake

People report work where they already talk. A message in a watched channel containing a trigger word
("bug", "broken", "error", "outage", …), or the `/ticket <description>` slash command, creates a ticket.

The message goes through the orchestrator, which:

1. creates the ticket
2. checks it for duplicates
3. prioritises it
4. prepares a coding-agent session, if that's turned on

The bot then replies in the thread with the ticket ID, the AI priority and its reasoning, any likely
duplicates, and the session's branch. If the orchestrator can't be reached, the ticket is still created
directly.

```mermaid
sequenceDiagram
    actor U as Team member
    participant S as Slack
    participant I as Slack Intake
    participant O as Orchestrator
    participant T as Ticket Service

    U->>S: "Login is broken on Safari" or /ticket ...
    S->>I: message event
    I->>O: slack_message workflow
    O->>T: create ticket, check duplicates
    O->>O: prioritise, prepare agent session
    O-->>I: ticket + priority + duplicates + session
    I-->>S: reply in thread
    S-->>U: APM-12 created · High (82/100)<br/>Possible duplicate of APM-1
    Note over I,T: If the orchestrator is unreachable,<br/>Slack Intake creates the ticket directly
```

### 4. GitHub status sync

Developers never update tickets by hand. When a commit message, PR title or branch name mentions a ticket
(`APM-12`, `[TICKET:APM-12]`, `fixes #42`), GitHub's webhook moves the ticket automatically and posts an
update to Slack. The reason ("PR #31 merged: …") is recorded on the ticket's timeline.

```mermaid
flowchart LR
    C["Commit pushed<br/>mentions APM-12"] --> IP["In Progress"]
    PO["PR opened / reopened"] --> IP
    PM["PR merged"] --> DN["Done"]
    PC["PR closed, not merged"] --> OP["Open"]
    IC["Issue closed"] --> DN
    IR["Issue reopened"] --> OP

    IP & DN & OP --> TL["Timeline entry<br/>with the PR / commit as reason"]
    IP & DN & OP --> SN["Slack notification"]
```

### 5. AI prioritisation

The Priority Agent reads every open ticket and asks the LLM to rank them. It weighs production impact,
how many users are affected, security, deadlines and dependencies. Each ticket gets a priority (Low → Critical),
a score from 1 to 100 and a short reason. It runs automatically every hour (configurable), for every new Slack
ticket, and on demand. The reasoning appears on the ticket's timeline.

```mermaid
flowchart TB
    TR["Every 60 min<br/>new Slack ticket<br/>or on demand"] --> F["Fetch open tickets"]
    F --> L["LLM ranks them<br/>impact, users, security,<br/>deadlines, dependencies"]
    L --> U["Update priority + score"]
    U --> E["Timeline: Priority Medium → High<br/>reason: Blocks sign-in for Safari users"]
```

### 6. AI daily standup

Every weekday morning (09:00 by default, with a configurable schedule and timezone), the Standup Agent reads
the active tickets and groups them by person. The LLM then writes a short team summary and a one-line update
for each person. The standup is posted to the Slack standup channel, and it can also be generated on demand.

```mermaid
flowchart TB
    CR["Cron: 09:00 Mon–Fri"] --> A["Collect active tickets"]
    A --> G["Group by assignee<br/>count open, in progress,<br/>blocked, done today"]
    G --> L["LLM writes summary<br/>+ one line per person"]
    L --> P["Post to #standup"]
```

### 7. Orchestrator workflows

The orchestrator chains the agents into workflows using LangGraph. A step that fails (for example, the LLM is
unavailable) is reported, and the rest of the workflow still runs.

| Workflow | Steps |
|---|---|
| `slack_message` | create ticket → check duplicates → prioritise → prepare agent session |
| `full_pipeline` | the same steps, then generate the standup |
| `manual_standup` | generate the standup |
| `github_event` | record a GitHub event |

```mermaid
flowchart TB
    S(["Trigger"]) --> C["Create ticket"]
    C --> D["Check duplicates"]
    D --> P["Prioritise"]
    P --> A["Prepare agent session<br/>if auto-prepare is on"]
    A --> E(["End: slack_message"])
    A --> SU["Generate standup"]
    SU --> E2(["End: full_pipeline"])
```

### 8. Duplicate detection

The same problem often gets reported twice. Every ticket is compared with all the others by meaning-bearing
words, using TF-IDF with cosine similarity. This needs no API key and gives the same result every time.

- **While typing:** the New-ticket dialog shows "Similar tickets already exist", with match percentages.
- **On creation:** likely duplicates are recorded on the new ticket's timeline.
- **In the ticket panel:** a "This may be a duplicate" notice with a one-click **Mark duplicate**, which links
  the ticket and closes it.
- **In Slack:** the bot's reply lists likely duplicates.

Sub-tasks are never flagged as duplicates of their own parent.

```mermaid
flowchart TB
    N["New or draft ticket"] --> T["Extract words<br/>drop stop-words, stem plurals<br/>title counts double"]
    T --> V["TF-IDF vectors"]
    V --> C["Cosine similarity vs every other ticket"]
    C --> R{"Score ≥ 35%?"}
    R -- yes --> W["Warn: dialog, ticket panel,<br/>Slack reply, timeline"]
    W --> M["One click: Mark duplicate<br/>link + close"]
    R -- no --> K["Treat as new work"]
```

### 9. AI breakdown into sub-tasks

Big or vague tickets are hard to start. **Break down with AI** asks the LLM to split a ticket into 3–8
sub-tasks, each small enough for one person and one pull request. Each comes with a type, an estimate in
hours and its dependencies. The result is a **proposal**: you tick the ones you want, and only those are
created as linked sub-tasks. A progress bar on the parent shows how many are done. You can also add sub-tasks
by hand.

```mermaid
sequenceDiagram
    actor U as You
    participant D as Dashboard
    participant A as Dev Agent
    participant L as LLM
    participant T as Ticket Service

    U->>D: Break down with AI
    D->>A: propose breakdown for APM-4
    A->>T: ticket + existing sub-tasks
    A->>L: split into 3–8 reviewable sub-tasks
    L-->>A: titles, types, estimates, dependencies
    A-->>D: proposal (nothing created yet)
    U->>D: tick the ones to keep → Create
    D->>A: apply selected sub-tasks
    A->>T: create linked sub-tasks
    T-->>D: APM-10 … APM-13 under APM-4
```

### 10. Explainable activity timeline

Every ticket has a timeline of everything that happened to it: who did it and **why**. That includes:

- creation, status, priority and assignee changes
- links (sub-task, duplicate) and possible-duplicate warnings
- sub-tasks being created
- coding-agent sessions being prepared
- progress notes from coding agents

AI decisions carry their reasoning, PR-driven changes carry the PR, and repeated small re-scores are left out so
the history stays readable. The Activity tab refreshes live while it's open.

```mermaid
flowchart LR
    subgraph Actors
        H["People<br/>dashboard"]
        PA["Priority agent"]
        GH["GitHub"]
        DD["Duplicate detector"]
        BA["Breakdown agent"]
        CA["Coding agent<br/>via MCP"]
    end
    H & PA & GH & DD & BA & CA --> E[("Timeline events<br/>who · what · why · when")]
    E --> V["Activity tab<br/>live updates"]
    E --> B["Agent briefs<br/>ticket history"]
    E --> M["MCP tool<br/>get_ticket_timeline"]
```

### 11. Coding-agent hand-off (manual mode)

The standout feature. One click on **Coding agent → Prepare agent session** turns a ticket into a ready-to-start
session for **Claude Code, Codex or Cursor**:

1. **A workspace of its own:** a git worktree on a new branch `apm/APM-12-<title>`, so your main checkout is
   never touched.
2. **A context brief** (`.apm/APM-12.md`) containing:
   - the ticket, the AI priority reasoning and its history
   - related tickets, sub-tasks and earlier commits
   - **the most relevant files in the codebase**, ranked by how strongly they match the ticket, with short code excerpts
   - the repo's own rules (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules`) and how to run its tests
   - AI-drafted acceptance criteria and a suggested plan
3. **A one-line command** to start the chosen agent. For Cursor there is also a link that sends the prompt
   straight to its chat.

It's **manual mode**: the agent reads the brief, summarises the ticket, proposes a plan and **waits for the
developer's go-ahead** before changing code. Sessions can also be prepared automatically for every new ticket
(*auto-prepare*), so the context is ready when someone picks the ticket up.

```mermaid
flowchart TB
    T["Ticket APM-12"] --> G["Gather context<br/>ticket, timeline, related,<br/>parent / sub-tasks"]
    R[("Linked codebase")] --> W["Create worktree<br/>branch apm/APM-12-…"]
    W --> S["Search code for the ticket's terms<br/>rank files, take excerpts,<br/>recent commits, conventions, tests"]
    G --> B["Write brief<br/>.apm/APM-12.md"]
    S --> B
    P["LLM: acceptance criteria + plan"] --> B
    B --> CMD["Ready-to-run command"]
    CMD --> CC["claude …"]
    CMD --> CX["codex …"]
    CMD --> CU["cursor … / prompt link"]
    CC & CX & CU --> PL["Agent proposes a plan<br/>and waits for go-ahead"]
```

### 12. Ticket tools inside the coding agent (MCP server)

The coding agent stays connected to the board while it works. A bundled **Model Context Protocol** server
(`autonomous-pm`) is wired into each session automatically:

- Claude Code gets it through `--mcp-config`.
- Cursor gets it through `.cursor/mcp.json`.
- Codex gets it from a config snippet shown in the dashboard.

It gives the agent seven tools:

| Tool | What it does |
|---|---|
| `get_ticket` | Full ticket details |
| `get_ticket_timeline` | History, including the AI's reasoning |
| `find_similar_tickets` | Related tickets that may hold earlier fixes |
| `list_subtasks` | Sub-tasks and their status |
| `search_tickets` | Search the board |
| `add_progress_note` | Log progress on the ticket's timeline |
| `update_ticket_status` | Move to In Progress, In Review or Blocked |

Agents can't mark work **Done**; that happens when the pull request is merged.

```mermaid
sequenceDiagram
    participant A as Coding agent
    participant M as MCP server
    participant T as Ticket Service
    participant D as Dashboard

    A->>M: get_ticket(APM-12)
    M->>T: GET /tickets/APM-12
    T-->>A: details, priority, links
    A->>M: add_progress_note("Found the cause in llm_client.py")
    M->>T: POST timeline note
    A->>M: update_ticket_status(In Review)
    M->>T: status → In Review (reason recorded)
    T-->>D: Activity tab updates live
    A-xM: update_ticket_status(Done)
    M-->>A: refused: Done is set when the PR merges
```

---

## End-to-end user flow

From a message in Slack to merged code, with people deciding at each key step:

```mermaid
flowchart LR
    subgraph S1["1 · Report"]
        direction TB
        START(["Problem noticed"]) --> SRC{"Where?"}
        SRC -- Slack --> SLK["Message or /ticket"]
        SRC -- Dashboard --> NEW["New ticket dialog"]
        NEW --> LIVE{"Similar ticket shown<br/>while typing?"}
        LIVE -- "same issue" --> EXIST["Use the existing ticket"]
        LIVE -- "new issue" --> MADE["Ticket created"]
        SLK --> MADE
    end

    subgraph S2["2 · Triage"]
        direction TB
        DUP{"Likely duplicate?"}
        DUP -- yes --> MARK["Mark duplicate<br/>ticket closed"]
        DUP -- no --> PRIO["AI prioritises<br/>score + reasoning"]
        PRIO --> BIG{"Too big or vague?"}
        BIG -- yes --> BD["Break down with AI<br/>approve sub-tasks"]
        BIG -- no --> READY["Ready to build"]
        BD --> READY
    end

    subgraph S3["3 · Build"]
        direction TB
        PICK["Pick a ticket"] --> PREP["Prepare agent session<br/>branch · worktree · brief"]
        PREP --> RUN["Run Claude Code,<br/>Codex or Cursor"]
        RUN --> PLAN["Agent proposes a plan"]
        PLAN --> OK{"Developer<br/>approves?"}
        OK -- adjust --> PLAN
        OK -- yes --> CODE["Agent writes code<br/>logs notes via MCP"]
    end

    subgraph S4["4 · Ship"]
        direction TB
        PRQ["Commit 'APM-12: …'<br/>open a pull request"] --> SYNC["GitHub sync<br/>In Progress / In Review"]
        SYNC --> MERGE{"PR merged?"}
        MERGE -- yes --> DONE(["Done · Slack notified"])
        MERGE -- "closed, not merged" --> BACK["Back to Build"]
        DONE --> STAND["Next morning:<br/>AI standup in Slack"]
    end

    S1 --> S2 --> S3 --> S4
```

Every step along the way – AI decisions, GitHub events, agent notes and people's edits – is recorded on the
ticket's timeline with who did it and why.
