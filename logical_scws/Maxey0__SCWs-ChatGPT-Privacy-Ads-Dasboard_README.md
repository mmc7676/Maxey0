# Maxey0 SCWs for ChatGPT Ads

**A privacy-first ad boundary for ChatGPT Free and Go users, built on Maxey0 logical Structured Context Worlds (SCWs).**

You split your ChatGPT use into context worlds (Work, Learning, Everyday, or your own). For each world you decide which kinds of memory an ad system may read, which ad categories are acceptable, and how many ads you will tolerate. The app then shows you exactly what would cross each boundary, and what never can.

It is one React file (`Maxey0-SCWs_For_ChatGPT_Ads.tsx`). It runs entirely in the page: there is no server, no storage and no network call. Every advertiser in it is fictional.

> **What this app can and cannot do**
> Inside the app, every rule is enforced by one evaluator, the same function that drives the map, the simulator and the replay.
> In ChatGPT, only ChatGPT's own settings are enforced. The instruction and profile you export are **advisory**: ChatGPT may follow them, but it is not bound by them. The app says this wherever it matters.

---

## Contents

1. [Quick start](#quick-start)
2. [Core ideas](#core-ideas)
3. [User guide, page by page](#user-guide-page-by-page)
4. [Applying your boundary to ChatGPT](#applying-your-boundary-to-chatgpt)
5. [Profile file format](#profile-file-format)
6. [How decisions are made](#how-decisions-are-made)
7. [Privacy](#privacy)
8. [Limitations](#limitations)
9. [Publishing and running it](#publishing-and-running-it)
10. [Verification](#verification)
11. [Research and citation](#research-and-citation)
12. [Credits and licence](#credits-and-licence)

---

## Quick start

1. Open the app. It starts on the **Balanced** preset: Work is sealed, and Learning and Everyday allow contextual ads from the current chat only.
2. On **Overview**, pick **Strict**, **Balanced** or **Open**, and watch the privacy score, the exposure flow and the replay grid update.
3. Open **Latent Map** and click an SCW world to edit it live.
4. Try a few messages in the **Simulator**, including one about a medical appointment and one containing an email address, and read the trace.
5. On **Apply to ChatGPT**, work through ChatGPT's own settings, then copy the instruction and export your profile.

Every change can be undone with **Undo** (the last 40 changes are kept).

---

## Core ideas

### Logical SCW

A Structured Context World is a named boundary around one kind of conversation. A *logical* SCW is written as a declarative object, not built as a process or a sandbox. One pure function (the evaluator) decides what leaves it, and a fixed set of invariants overrides every setting. Each SCW declares:

| Field | Meaning |
|---|---|
| Mode | **Sealed** (nothing leaves), **Contextual** (topic labels only), **Review** (an ad is matched but held until you approve it) or **Open** (every tier you grant may be used) |
| Memory tiers | Which of Working, Episodic and Semantic the ad system may read in this world |
| Ad categories | Technology, Business, Education, Lifestyle; each must also be allowed globally |
| Sharing | Whether this chat's topics, and your stated interests, may be used here |
| Limits | Max ads per session and a minimum relevance score |
| Blocked topics | Words or phrases that suppress ads for the whole turn when mentioned |

Chats in different SCWs cannot see each other: each world keeps its own session history.

### Five typed memory tiers (Maxey0)

Memory is typed by **kind**, not by how long it lasts.

| Tier | Holds | In ChatGPT | Ad-readable? |
|---|---|---|---|
| **Working** | Volatile in-flight state | The message you are writing now | If granted and conversation sharing is on |
| **Episodic** | Turn chains, session summaries | Earlier turns in the current chat | If granted and session sharing is on |
| **Semantic** | Concept graph: concepts, interests | Saved memory, chat history, inferred ad interests | If granted and personalization is on |
| **Persistent** | Durable facts, versioned preferences | Account identity, profile, settings | **Never** |
| **Procedural** | Skills and instructions | Custom instructions and this profile | **Never** |

Items move between tiers only through Maxey0's evidence-gated **promotion gate**, which checks relevance, evidence, consistency, reuse and policy. Items that fail go to quarantine to be repaired or forgotten. The Memory page animates this.

### The five invariants

These hold in every SCW, whatever you set:

| ID | Rule |
|---|---|
| INV-1 | Identity cues (email, phone, name) are never released. Age, occupation or income, and location cues are withheld under the same rule. |
| INV-2 | Demographic and behavioral data are never released; those flags are fixed to off. |
| INV-3 | A sensitive topic (health, mental health, politics, religion, sexuality, financial hardship) suppresses ads for the whole turn. |
| INV-4 | Persistent and Procedural memory can never be granted to an SCW. |
| INV-5 | Advertisers receive topic labels only, never message text, identity or history. |

---

## User guide, page by page

### Overview
- **Privacy score dial.** `score = 100 × (1 − mean SCW exposure)`, where an SCW's exposure is its mode weight (Sealed 0, Review 0.6, Contextual 0.8, Open 1) × the sum of the tier weights it is granted *and* allowed to share (Working 0.2, Episodic 0.3, Semantic 0.5). An SCW with no allowed categories has zero exposure. The presets score 95 (Strict), 73 (Balanced) and 23 (Open).
- **Preset switch.** Applying a preset keeps your interests and blocked brands. Editing anything afterwards marks the profile *Custom*.
- **Exposure flow.** Every memory tier and identity cue flows into every SCW, then to *Advertiser* (solid, animated bands: labels only) or *Withheld* (dashed). Hover a band to highlight its path; click an SCW to edit it.
- **Replay grid.** 18 synthetic test prompts × every SCW. Each cell is a full evaluator run, coloured by outcome: ad served, ad held for review, labels only, sealed, suppressed or nothing to release. The *Invariant breaches* chip should always read 0. Click any cell to open it in the Simulator.

### Latent Map
An animated canvas of your whole boundary:
- **Centre:** you, with your privacy score.
- **Sealed core:** Persistent and Procedural, locked.
- **Three rings:** Semantic, Episodic and Working. Each is labelled with how many SCWs it is granted to, and gets brighter as that number grows.
- **Orbiting worlds:** your SCWs, coloured by mode. Coloured channels show the tiers each world reads; particles flow along a channel only when sharing is on.
- **Outer diamonds:** nine fictional advertisers, coloured by category. They continuously fire *probes* at your SCWs. A probe is admitted (green burst) only if the SCW is not sealed, reads Working with conversation sharing on, allows the ad's category, and the brand is not blocked. Otherwise it deflects at the membrane (red). Live counters sit above the map.

Hover anything for details. Click a world to open its editor in the side panel. **Pause** stops the animation, and it runs slower when your system asks for reduced motion.

### SCW Studio
- **Tier grants grid:** every tier × every SCW as a switch. Persistent and Procedural show as *locked*.
- **One card per SCW:** name, mode, tiers, categories, sharing switches, ad limit, relevance floor and blocked topics. Each card has a live preview of a fixed test message and a *Trace in simulator* link.
- **New SCW** adds a world (up to 12). The bin icon deletes one; at least one must remain.

### Simulator
Choose an SCW, then type as you would in ChatGPT, or tap a quick prompt. For each turn you see:
- the outcome and its reason, plus a fictional ad card when one is served (Review mode offers *Show ad* or *Dismiss*)
- **Pipeline trace:** each rule with pass or fail and its detail
- **Released:** the labels, each tagged with the tier it came from
- **Withheld:** every signal, with its tier and the rule code that withheld it
- **Isolation at a glance:** the same message evaluated in every SCW

Earlier turns in the same SCW become that world's Episodic tier, and ads already shown count against the session budget. **Reset** clears the world's session.

### Advertiser Lens
Choose an SCW and a sample prompt. On the left is your message, with the words the classifier used highlighted, and its trace. On the right is the complete payload the ad system would receive under that SCW. `user_id`, `message_text`, `history`, `demographics` and `location` are always `null`. The payload format is this app's illustration; ChatGPT's real ad request format is not public.

### Memory
The animated promotion gate, a card for each of the five tiers, and your **stated interests**, which make up the Semantic tier. Each interest can be at most 40 characters and four words, because it may be released as a label. Interests are coloured by the category the classifier assigns. Sensitive or unclassified interests are never released.

### Learn SCWs
Five short lessons on logical SCWs, each linking to the page that shows it working, plus the five invariants and an honest-limits panel.

### Apply to ChatGPT
Global controls, then three steps. [Applying your boundary to ChatGPT](#applying-your-boundary-to-chatgpt) explains each step.

| Control | What it does in the app |
|---|---|
| Ad categories allowed anywhere | Intersected with each SCW's categories |
| Blocked brands | Matching fictional advertisers are never served |
| Share current-message topics | Required for the Working tier |
| Share this-session topics | Required for the Episodic tier |
| Use my interests | Required for the Semantic tier |
| Allow search history | **Advisory only**: written into the ChatGPT instruction; the simulator does not model search |
| Max ads per hour | Enforced in the simulator, together with the per-session limit |
| Max ads per day | **Advisory only**: written into the instruction |
| Minimum relevance | Combined with each SCW's floor (the higher one applies) |

---

## Applying your boundary to ChatGPT

The app gives you three channels, and they carry different force.

1. **ChatGPT's own settings (enforced by ChatGPT).** Only these change what ChatGPT's systems actually do. Menu names change, so look under Settings for personalization, memory, data controls and ads. Consider:
   - memory and chat-history reference, if you do not want the Semantic tier used at all
   - ad personalization controls where your account shows them, and clearing ad-interest data you do not want used
   - Temporary Chat for anything you would put in a Sealed SCW
   - exporting your data from time to time to see what has been stored
2. **The instruction (advisory).** Copy it into custom instructions or the start of a chat. It restates your SCWs, invariants, categories, blocked brands and limits. ChatGPT may take it into account in conversation, but it cannot change how ads are selected.
3. **The profile file (portable).** Your whole configuration as JSON, for backup, sharing or a future platform that enforces SCWs.

---

## Profile file format

Export writes version `2.0.0`:

```json
{
  "version": "2.0.0",
  "app": "Maxey0 SCWs for ChatGPT Ads",
  "exportedAt": "2026-09-30",
  "memoryModel": "Maxey0 five typed tiers: Working, Episodic, Semantic, Persistent, Procedural. ...",
  "invariants": ["INV-1: ...", "INV-2: ...", "INV-3: ...", "INV-4: ...", "INV-5: ..."],
  "profile": {
    "privacyLevel": "balanced",
    "interests": [],
    "blockedBrands": [],
    "allowedCategories": ["technology", "education", "lifestyle"],
    "scwGates": [
      {
        "id": "scw-…",
        "name": "Learning",
        "gateType": "contextual",
        "allowedCategories": ["education", "technology"],
        "blockedTopics": [],
        "maxAdsPerSession": 2,
        "requireRelevanceScore": 80,
        "memoryTierAccess": ["Working", "Episodic"],
        "dataSharing": { "conversationContext": true, "userPreferences": false, "behavioralData": false, "demographicData": false }
      }
    ],
    "sessionLimits": { "maxAdsPerHour": 4, "maxAdsPerDay": 15, "minRelevanceThreshold": 75 },
    "dataControls": { "shareConversationTopics": true, "shareSearchHistory": false, "shareInteractionPatterns": true, "allowPersonalization": false }
  },
  "chatgptInstruction": "Maxey0 SCW privacy profile (advisory). ..."
}
```

`gateType` values map to modes: `block` = Sealed, `contextual` = Contextual, `review` = Review, `allow` = Open.

**Import** accepts only profiles exported by this dashboard: a JSON object with `version` 1.x or 2.x and a `profile` containing `scwGates`, `sessionLimits` and `dataControls`. Anything else is rejected with an *Invalid profile format* message. For example, ChatGPT's own "privacy-profile context export" is rejected, because it has no `version` field and a different `profile` shape.

On import:
- **Legacy tier names are converted:** `Scratchpad (L1)` → Working, `Episodic (L2)` → Episodic, `Persistent (L3)` → Semantic. `Permanent (L4)`, Persistent, Procedural and unknown names are dropped, and the message tells you how many were removed.
- **Behavioral and demographic flags are forced to `false`.**
- **Values are cleaned up:** limits are clamped to the ranges the interface allows (ads per hour 0–20, per day 0–100, relevance floors 50–100, ads per session 0–10), unknown categories and interests longer than 40 characters or four words are dropped, names are trimmed to 40 characters, and at most 12 SCWs are kept.

---

## How decisions are made

For one message in one SCW, the evaluator runs these steps in order and stops at the first one that ends the turn:

1. **INV-1:** identity, demographic and location cues go into the withheld ledger.
2. **INV-3:** a sensitive topic suppresses the whole turn.
3. **Blocked topic:** a match suppresses the turn.
4. **Mode:** Sealed releases nothing.
5. **Tiers:**
   - **Working:** labels from the current message
   - **Episodic:** labels from earlier turns in this SCW, skipping any turn that was sensitive
   - **Semantic:** your interests

   Each tier needs its grant and its sharing switches, and each label's category must be allowed by both the SCW and the global list.
6. **Budget:** the lower of the SCW's per-session limit and the hourly limit.
7. **Relevance:** the best fictional ad scores `55 + 20 × matched labels (+10 if matched from the current message)`, capped at 100, and must reach the higher of the two relevance floors.
8. **Review mode** holds the matched ad until you approve it.

Every withheld signal carries one rule code: `INV-1`, `INV-3`, `INV-4`, `BLOCK`, `SEALED`, `NO-GRANT`, `SHARE-CTX`, `SHARE-SESSION`, `SHARE-PREFS`, `CATEGORY`, `UNCLASSIFIED` or `LENGTH` (an interest over 40 characters or four words).

The classifier is a deterministic keyword list over four ad categories and six sensitive classes, with a small list of neutral compounds such as "technical debt" and "upvote", and pattern checks for email addresses, phone numbers (3-3-4 or international format), names, age, occupation or income, and location. It is inspectable, but it misses paraphrase.

---

## Privacy

- **Nothing leaves the page.** No server, no analytics, no storage. Everything you type lives in memory and is gone when you close the page.
- **No personal data is built in.** The app contains no user data. The test prompts are synthetic, and the advertisers are fictional.
- **Clipboard and download only when you ask.** The only ways data leaves the page are Copy (clipboard) and Download (a JSON file), and both happen only when you click them.

---

## Limitations

- **Not binding on ChatGPT.** It cannot make ChatGPT, or its ad system, honor your SCWs. Only ChatGPT's own settings bind ChatGPT.
- **A model, not the real ad system.** It shows what your policy would let an ad system read, not what OpenAI's system actually reads. OpenAI also uses signals, such as general location and language, that no user-side policy can withhold.
- **Keyword classifier.** It misses paraphrase and can misfire on words used out of context. Mistakes lean toward withholding.
- **Illustrative scoring.** The privacy score is this app's own formula, shown on the page, not an industry standard.
- **Not everything is simulated.** Search history and the daily ad cap are written into the instruction but not simulated.
- **No import of ChatGPT's data export.** This version does not read your ChatGPT data export in the page. The research replay of a real export was run offline with the same evaluator; see [Verification](#verification).

---

## Publishing and running it

**As a claude.ai artifact.** Paste the file into a React artifact, or ask Claude to publish it. It imports only `react` and `lucide-react`, both available in the artifact runtime, and carries its own CSS. It does not use Tailwind, shadcn/ui or browser storage.

**In your own React project** (React 18+):

```bash
npm install react react-dom lucide-react
```

```tsx
import App from "./Maxey0-SCWs_For_ChatGPT_Ads";
export default function Page() { return <App />; }
```

**Using the engine without the UI.** These are named exports: `classifyText`, `evaluateTurn`, `importProfile`, `exportProfile`, `privacyScore`, `gateExposure`, `normalizeMemoryTiers`, `PRESETS`, `CORPUS` and `INVENTORY`.

```ts
import { PRESETS, evaluateTurn } from "./Maxey0-SCWs_For_ChatGPT_Ads";
const p = PRESETS.balanced.build();
const r = evaluateTurn(p, p.scwGates[1], "Explain Bayesian statistics with a worked example");
console.log(r.outcome, r.released, r.withheld);
```

---

## Verification

Evidence for this version (file SHA-256 `ad921ad5…`), all produced by running code on 2026-09-29 and 2026-09-30. The property test, mutation check and export replay ran on build `4e12a49d…`, which differs only in display text (“window” renamed to “world”); the engine is identical. Type check and browser checks were re-run on `ad921ad5…`.

| Check | Result |
|---|---|
| TypeScript, strict mode with `noUnusedLocals` | 0 errors |
| Browser checks (headless Chromium, 1440 px and 400 px) | 11/11 engine checks, 17/17 UI checks, 0 script errors, no horizontal overflow on any page |
| Seeded property test (20,000 random profiles, SCWs, messages and histories) | 0 violations across 19 per-case checks: invariants, tier grants, sharing flags, categories, relevance, budget, blocked brands, sealed and review modes, determinism |
| Mutation check (7 injected faults, 5,000 cases each) | All 7 caught |
| Replay of one real ChatGPT export (602 chats, 9,295 user messages), run on the owner's computer, aggregate counts only | 0 invariant breaches under all three presets; 40 chats suppressed as sensitive |

**Not yet verified:** rendering inside the claude.ai artifact viewer itself.

---

## Research and citation

This app accompanies the paper *Logical Structured Context Worlds: Exact Context Boundaries Without a Runtime* (Maxey0, 2026), which defines logical SCWs, uses ChatGPT advertising privacy as its worked application, and reports the tests above.

```
Cohan, M., and Maxey0-Claude. Maxey0 SCWs for ChatGPT Ads (version 3). Maxey0, 2026.
```

---

## Credits and licence

- **Concept, architecture and direction:** Mike Cohan (Human0), Maxey0.
- **Version 1:** Maxey1 (Claude Sonnet 4.6).
- **This version:** Maxey0-Claude (Claude Opus 5.5), the orchestrating agent of the SCW0 project.
- **Contact:** human@maxey0.com.

Licence: *to be chosen by the author before public release.*

ChatGPT is a trademark of OpenAI. This project is independent and not affiliated with or endorsed by OpenAI.
