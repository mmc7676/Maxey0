/**
 * Maxey0 · SCWs for ChatGPT Ads
 * A privacy-first, user-controlled ad boundary for ChatGPT free users, built on Maxey0 logical
 * Structured Context Worlds (SCWs).
 *
 * What is enforced where:
 *  - Inside this app, every rule is enforced by the evaluator below (simulator, replay, latent map).
 *  - In ChatGPT, only ChatGPT's own settings are enforced. The exported profile and instruction are
 *    advisory: ChatGPT may follow them but is not bound by them.
 *
 * Memory model: five typed tiers, not a duration stack (Working, Episodic, Semantic, Persistent,
 * Procedural). Items move between tiers only through the evidence-gated promotion gate. Persistent
 * and Procedural are never ad-readable in any SCW. All advertisers shown are fictional.
 */
import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  Shield, Lock, Eye, Map as MapIcon, Send, Download, Upload, Copy, Check,
  Plus, Trash2, BookOpen, Zap, Play, Pause, RotateCcw, Undo2, Megaphone, Fingerprint, Brain, LayoutGrid,
  SlidersHorizontal, ArrowRight, Info,
} from "lucide-react";

// ============================================================================
// 1. MODEL
// ============================================================================

type MemoryTier = "Working" | "Episodic" | "Semantic" | "Persistent" | "Procedural";
type PrivacyLevel = "minimal" | "balanced" | "strict" | "custom";
type AdCategory = "technology" | "business" | "education" | "lifestyle" | "none";
type SCWGateType = "allow" | "block" | "review" | "contextual";
type SensitiveClass = "health" | "mental_health" | "politics" | "religion" | "sexuality" | "financial_hardship";

interface SCWPrivacyGate {
  id: string;
  name: string;
  gateType: SCWGateType;
  allowedCategories: AdCategory[];
  blockedTopics: string[];
  maxAdsPerSession: number;
  requireRelevanceScore: number;
  memoryTierAccess: MemoryTier[];
  dataSharing: { conversationContext: boolean; userPreferences: boolean; behavioralData: boolean; demographicData: boolean };
}

interface UserAdProfile {
  privacyLevel: PrivacyLevel;
  interests: string[];
  blockedBrands: string[];
  allowedCategories: AdCategory[];
  scwGates: SCWPrivacyGate[];
  sessionLimits: { maxAdsPerHour: number; maxAdsPerDay: number; minRelevanceThreshold: number };
  dataControls: { shareConversationTopics: boolean; shareSearchHistory: boolean; shareInteractionPatterns: boolean; allowPersonalization: boolean };
}

interface TierInfo {
  id: MemoryTier; short: string; holds: string; lifecycle: string; chatgpt: string;
  adGrantable: boolean; color: string; weight: number;
}

const TIERS: TierInfo[] = [
  { id: "Working", short: "W", holds: "Volatile in-flight state (scratchpad)", lifecycle: "TTL-enforced; purged at session close", chatgpt: "The message you are writing now", adGrantable: true, color: "#34d399", weight: 0.2 },
  { id: "Episodic", short: "E", holds: "Turn chains, session summaries, handoff state", lifecycle: "Time-stamped; summarized at session close", chatgpt: "Earlier turns in the current chat", adGrantable: true, color: "#60a5fa", weight: 0.3 },
  { id: "Semantic", short: "S", holds: "Concept graph: extracted concepts, aliases, interests", lifecycle: "Admitted from Episodic only through the promotion gate", chatgpt: "Saved memory, chat history and interests the ad system inferred", adGrantable: true, color: "#fbbf24", weight: 0.5 },
  { id: "Persistent", short: "P", holds: "Durable facts and versioned preferences", lifecycle: "Written rarely, always with a promotion evidence chain", chatgpt: "Account identity, profile and settings", adGrantable: false, color: "#f87171", weight: 0 },
  { id: "Procedural", short: "R", holds: "Skills and instructions: how the assistant behaves", lifecycle: "Creation = memorization, revision = consolidation, deprecation = forgetting", chatgpt: "Custom instructions and this privacy profile", adGrantable: false, color: "#a78bfa", weight: 0 },
];
const TIER: Record<MemoryTier, TierInfo> = Object.fromEntries(TIERS.map((t) => [t.id, t])) as Record<MemoryTier, TierInfo>;
const AD_GRANTABLE = new Set<MemoryTier>(TIERS.filter((t) => t.adGrantable).map((t) => t.id));
const LEGACY_TIER_NAMES: Record<string, MemoryTier> = { "Scratchpad (L1)": "Working", "Episodic (L2)": "Episodic", "Persistent (L3)": "Semantic" };
const MEMORY_MODEL = "Maxey0 five typed tiers: Working, Episodic, Semantic, Persistent, Procedural. Promotion is evidence-gated. Persistent and Procedural are never ad-readable.";

const normalizeMemoryTiers = (tiers: unknown): MemoryTier[] => {
  const out: MemoryTier[] = [];
  (Array.isArray(tiers) ? tiers : []).forEach((t) => {
    if (typeof t !== "string") return;
    const tier = (LEGACY_TIER_NAMES[t] ?? t) as MemoryTier;
    if (AD_GRANTABLE.has(tier) && !out.includes(tier)) out.push(tier);
  });
  return TIERS.map((t) => t.id).filter((id) => out.includes(id));
};

const CATEGORIES: { id: Exclude<AdCategory, "none">; label: string; color: string }[] = [
  { id: "technology", label: "Technology", color: "#22d3ee" },
  { id: "business", label: "Business", color: "#fbbf24" },
  { id: "education", label: "Education", color: "#a78bfa" },
  { id: "lifestyle", label: "Lifestyle", color: "#f472b6" },
];
const CAT_COLOR: Record<string, string> = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.color]));

const MODES: { id: SCWGateType; label: string; blurb: string; color: string; weight: number }[] = [
  { id: "block", label: "Sealed", blurb: "No ads. Nothing leaves this world.", color: "#34d399", weight: 0 },
  { id: "contextual", label: "Contextual", blurb: "Ads may use released topic labels, never text.", color: "#60a5fa", weight: 0.8 },
  { id: "review", label: "Review", blurb: "An ad is matched but held until you approve it.", color: "#fbbf24", weight: 0.6 },
  { id: "allow", label: "Open", blurb: "Ads may use every tier you grant here.", color: "#f87171", weight: 1 },
];
const MODE: Record<SCWGateType, (typeof MODES)[number]> = Object.fromEntries(MODES.map((m) => [m.id, m])) as Record<SCWGateType, (typeof MODES)[number]>;

const INVARIANTS = [
  { id: "INV-1", text: "Identity cues (email, phone, name) are never released, in any SCW." },
  { id: "INV-2", text: "Demographic and behavioral data are never released; the flags are fixed to off." },
  { id: "INV-3", text: "A sensitive topic (health, mental health, politics, religion, sexuality, financial hardship) suppresses ads for the whole turn." },
  { id: "INV-4", text: "Persistent and Procedural memory can never be granted to an SCW." },
  { id: "INV-5", text: "Advertisers receive topic labels only: never message text, identity or history." },
];

interface AdCandidate { id: string; advertiser: string; category: Exclude<AdCategory, "none">; keywords: string[]; headline: string }
/** Sample ad inventory. Every advertiser is fictional. */
const INVENTORY: AdCandidate[] = [
  { id: "ad-northwind", advertiser: "Northwind Cloud", category: "technology", keywords: ["cloud", "kubernetes", "devops", "infrastructure", "server", "linux"], headline: "Migration credits for container workloads" },
  { id: "ad-lumen", advertiser: "Lumen IDE", category: "technology", keywords: ["code", "coding", "rust", "python", "software", "api", "typescript", "javascript"], headline: "An editor that reads your whole repo" },
  { id: "ad-ledgerly", advertiser: "Ledgerly", category: "business", keywords: ["invoice", "startup", "budget", "sales", "revenue", "client"], headline: "Invoices that chase themselves" },
  { id: "ad-stratum", advertiser: "Stratum Planning", category: "business", keywords: ["roadmap", "strategy", "planning", "okr", "quarterly", "marketing"], headline: "Roadmaps your team actually updates" },
  { id: "ad-cortex", advertiser: "Cortex Courses", category: "education", keywords: ["statistics", "bayesian", "math", "course", "learn", "learning", "study", "exam", "physics"], headline: "Probability, taught with worked examples" },
  { id: "ad-tidewater", advertiser: "Tidewater Trail Co.", category: "lifestyle", keywords: ["running", "shoes", "trail", "hiking", "camping", "fitness"], headline: "Trail shoes tested on 400 km of mud" },
  { id: "ad-kettle", advertiser: "Kettle & Crumb", category: "lifestyle", keywords: ["recipe", "cooking", "coffee", "baking"], headline: "Weeknight recipes in 25 minutes" },
  { id: "ad-everwell", advertiser: "Everwell Pharmacy", category: "lifestyle", keywords: ["medication", "blood pressure", "prescription"], headline: "Refill reminders for your prescriptions" },
  { id: "ad-pulse", advertiser: "Crowd Pulse", category: "business", keywords: ["election", "vote", "campaign"], headline: "Poll your district in 48 hours" },
];

// ---- local keyword classifier (deterministic, inspectable, not ML) ----
const CATEGORY_TERMS: Record<Exclude<AdCategory, "none">, string[]> = {
  technology: ["software", "code", "coding", "kubernetes", "cloud", "rust", "python", "ai", "laptop", "gpu", "api", "database", "devops", "infrastructure", "javascript", "typescript", "server", "linux"],
  business: ["roadmap", "strategy", "planning", "marketing", "sales", "startup", "invoice", "budget", "okr", "quarterly", "revenue", "client"],
  education: ["learn", "learning", "explain", "course", "study", "exam", "tutorial", "bayesian", "statistics", "math", "physics", "history", "homework", "lecture"],
  lifestyle: ["shoes", "running", "trail", "travel", "recipe", "cooking", "fitness", "hiking", "coffee", "garden", "baking", "camping", "music"],
};
const SENSITIVE_TERMS: Record<SensitiveClass, string[]> = {
  health: ["doctor", "medication", "diagnosis", "diagnosed", "symptom", "blood pressure", "prescription", "surgery", "cancer", "diabetes", "pregnant", "pregnancy", "illness"],
  mental_health: ["anxiety", "depression", "therapist", "therapy", "panic attack", "adhd", "bipolar", "burnout", "psychiatrist"],
  politics: ["election", "vote", "voting", "senator", "republican", "democrat", "political", "ballot", "congress"],
  religion: ["church", "mosque", "synagogue", "temple", "prayer", "faith", "religion", "religious", "bible", "quran"],
  sexuality: ["sexual orientation", "gay", "lesbian", "bisexual", "transgender", "queer", "dating app"],
  financial_hardship: ["debt", "bankrupt", "bankruptcy", "eviction", "overdue", "collection agency", "debt collector", "payday loan", "foreclosure", "can't afford"],
};
const NEUTRAL_PHRASES = ["technical debt", "tech debt", "design debt", "debt ratio", "debt-to-equity", "vote of confidence", "upvote", "downvote", "in good faith", "good-faith", "bad faith", "docker doctor", "flutter doctor", "brew doctor"];
const IDENTITY_PATTERNS: { kind: "identity" | "demographic" | "location"; re: RegExp; label: string }[] = [
  { kind: "identity", re: /[\w.+-]+@[\w-]+\.[\w.]+/, label: "email address" },
  { kind: "identity", re: /(?<![\w.:/-])(?:(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}|\+\d{1,3}(?:[\s.-]\d{2,4}){2,4})(?![\w.:/-])/, label: "phone number" },
  { kind: "identity", re: /\b(my name is|i am called|call me|goes by)\b/i, label: "personal name" },
  { kind: "demographic", re: /\b(\d{1,2}\s*(years old|yo)|born in \d{4}|aged? \d{1,2}\b)/i, label: "age" },
  { kind: "demographic", re: /\b(i work as|works at|my job is|my salary|i earn)\b/i, label: "occupation or income" },
  { kind: "location", re: /\b(i live in|i'm based in|my address|zip code|postcode)\b/i, label: "location" },
];

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const hasTerm = (text: string, term: string) => {
  const t = term.toLowerCase().trim();
  if (!t) return false;
  if (t.includes(" ")) return text.includes(t);
  return new RegExp(`(^|[^a-z0-9])${escapeRe(t)}([^a-z0-9]|$)`).test(text);
};

interface Classification {
  categories: Exclude<AdCategory, "none">[];
  labels: { label: string; category: Exclude<AdCategory, "none"> }[];
  sensitive: SensitiveClass | null;
  personal: { kind: "identity" | "demographic" | "location"; label: string }[];
}

function classifyText(raw: string): Classification {
  const text = raw.toLowerCase();
  const categories: Classification["categories"] = [];
  const labels: Classification["labels"] = [];
  (Object.keys(CATEGORY_TERMS) as Exclude<AdCategory, "none">[]).forEach((cat) => {
    const hits = CATEGORY_TERMS[cat].filter((t) => hasTerm(text, t));
    if (hits.length) {
      categories.push(cat);
      hits.forEach((h) => labels.some((l) => l.label === h) || labels.push({ label: h, category: cat }));
    }
  });
  const neutral = NEUTRAL_PHRASES.reduce((acc, ph) => acc.split(ph).join(" "), text);
  let sensitive: SensitiveClass | null = null;
  for (const cls of Object.keys(SENSITIVE_TERMS) as SensitiveClass[]) {
    if (SENSITIVE_TERMS[cls].some((t) => hasTerm(neutral, t))) { sensitive = cls; break; }
  }
  const personal = IDENTITY_PATTERNS.filter((p) => p.re.test(raw)).map((p) => ({ kind: p.kind, label: p.label }));
  return { categories, labels, sensitive, personal };
}

// ============================================================================
// 2. DEFAULTS, PRESETS, IMPORT / EXPORT
// ============================================================================

let _id = 0;
const newId = (p: string) => `${p}-${Date.now().toString(36)}${(++_id).toString(36)}${Math.random().toString(36).slice(2, 5)}`;
const clamp = (n: unknown, lo: number, hi: number, dflt: number) => {
  const v = typeof n === "number" && Number.isFinite(n) ? n : dflt;
  return Math.min(hi, Math.max(lo, Math.round(v)));
};
const today = () => new Date().toISOString().slice(0, 10);
/** Interests are released as labels, so they are bounded like labels: at most 40 characters and four words. */
const interestOk = (s: string) => { const t = s.trim(); return !!t && t.length <= 40 && t.split(/\s+/).length <= 4; };

const gate = (name: string, gateType: SCWGateType, cats: AdCategory[], tiers: MemoryTier[], ctx: boolean, prefs: boolean, max: number, rel: number, blocked: string[] = []): SCWPrivacyGate => ({
  id: newId("scw"), name, gateType, allowedCategories: cats, blockedTopics: blocked, maxAdsPerSession: max, requireRelevanceScore: rel,
  memoryTierAccess: tiers, dataSharing: { conversationContext: ctx, userPreferences: prefs, behavioralData: false, demographicData: false },
});

const PRESETS: Record<Exclude<PrivacyLevel, "custom">, { label: string; blurb: string; build: () => UserAdProfile }> = {
  strict: {
    label: "Strict", blurb: "Work sealed; only the current message may inform an ad, and only in Learning.",
    build: () => ({
      privacyLevel: "strict", interests: [], blockedBrands: [], allowedCategories: ["education"],
      scwGates: [
        gate("Work", "block", [], [], false, false, 0, 95, ["salary", "client names"]),
        gate("Learning", "contextual", ["education"], ["Working"], true, false, 1, 90),
        gate("Everyday", "block", [], [], false, false, 0, 95),
      ],
      sessionLimits: { maxAdsPerHour: 1, maxAdsPerDay: 3, minRelevanceThreshold: 90 },
      dataControls: { shareConversationTopics: true, shareSearchHistory: false, shareInteractionPatterns: false, allowPersonalization: false },
    }),
  },
  balanced: {
    label: "Balanced", blurb: "Contextual ads from this chat only. No profile-based targeting.",
    build: () => ({
      privacyLevel: "balanced", interests: [], blockedBrands: [], allowedCategories: ["technology", "education", "lifestyle"],
      scwGates: [
        gate("Work", "block", ["business", "technology"], ["Working"], false, false, 1, 90, ["salary", "client names"]),
        gate("Learning", "contextual", ["education", "technology"], ["Working", "Episodic"], true, false, 2, 80),
        gate("Everyday", "contextual", ["technology", "education", "lifestyle"], ["Working", "Episodic"], true, false, 3, 75),
      ],
      sessionLimits: { maxAdsPerHour: 4, maxAdsPerDay: 15, minRelevanceThreshold: 75 },
      dataControls: { shareConversationTopics: true, shareSearchHistory: false, shareInteractionPatterns: true, allowPersonalization: false },
    }),
  },
  minimal: {
    label: "Open", blurb: "Maximum relevance: ads may use your interests. Invariants still hold.",
    build: () => ({
      privacyLevel: "minimal", interests: [], blockedBrands: [], allowedCategories: ["technology", "business", "education", "lifestyle"],
      scwGates: [
        gate("Work", "review", ["business", "technology"], ["Working", "Episodic"], true, true, 2, 75),
        gate("Learning", "allow", ["education", "technology"], ["Working", "Episodic", "Semantic"], true, true, 3, 65),
        gate("Everyday", "allow", ["technology", "business", "education", "lifestyle"], ["Working", "Episodic", "Semantic"], true, true, 4, 60),
      ],
      sessionLimits: { maxAdsPerHour: 8, maxAdsPerDay: 30, minRelevanceThreshold: 60 },
      dataControls: { shareConversationTopics: true, shareSearchHistory: true, shareInteractionPatterns: true, allowPersonalization: true },
    }),
  },
};

const EXPORT_VERSION = "2.0.0";

function normalizeGate(g: any, k: number): SCWPrivacyGate {
  const cats = Array.isArray(g?.allowedCategories) ? g.allowedCategories.filter((c: unknown) => typeof c === "string" && (CATEGORY_TERMS as any)[c as string]) : [];
  const mode: SCWGateType = ["allow", "block", "review", "contextual"].includes(g?.gateType) ? g.gateType : "block";
  return {
    id: typeof g?.id === "string" && g.id ? g.id : newId("scw"),
    name: typeof g?.name === "string" && g.name.trim() ? g.name.trim().slice(0, 40) : `SCW ${k + 1}`,
    gateType: mode,
    allowedCategories: Array.from(new Set(cats)) as AdCategory[],
    blockedTopics: Array.isArray(g?.blockedTopics) ? g.blockedTopics.filter((t: unknown) => typeof t === "string" && t.trim()).map((t: string) => t.trim().toLowerCase()).slice(0, 30) : [],
    maxAdsPerSession: clamp(g?.maxAdsPerSession, 0, 10, 1),
    requireRelevanceScore: clamp(g?.requireRelevanceScore, 50, 100, 85),
    memoryTierAccess: normalizeMemoryTiers(g?.memoryTierAccess),
    dataSharing: { conversationContext: !!g?.dataSharing?.conversationContext, userPreferences: !!g?.dataSharing?.userPreferences, behavioralData: false, demographicData: false },
  };
}

function importProfile(json: string): { ok: true; profile: UserAdProfile; note: string } | { ok: false; error: string } {
  let data: any;
  try { data = JSON.parse(json); } catch { return { ok: false, error: "Invalid profile format: this is not valid JSON." }; }
  if (!data || typeof data !== "object" || typeof data.version !== "string" || !/^[12]\./.test(data.version)) {
    return { ok: false, error: "Invalid profile format: expected a profile exported by this dashboard (a JSON with \"version\" 1.x or 2.x and a \"profile\")." };
  }
  const p = data.profile;
  if (!p || typeof p !== "object" || !Array.isArray(p.scwGates) || !p.sessionLimits || !p.dataControls) {
    return { ok: false, error: "Invalid profile format: \"profile\" must contain scwGates, sessionLimits and dataControls." };
  }
  const strArr = (a: unknown) => (Array.isArray(a) ? a.filter((x): x is string => typeof x === "string" && !!x.trim()).map((x) => x.trim()).slice(0, 50) : []);
  let dropped = 0;
  p.scwGates.forEach((g: any) => (Array.isArray(g?.memoryTierAccess) ? g.memoryTierAccess : []).forEach((t: unknown) => {
    const m = typeof t === "string" ? LEGACY_TIER_NAMES[t] ?? t : null;
    if (!m || !AD_GRANTABLE.has(m as MemoryTier)) dropped++;
  }));
  const profile: UserAdProfile = {
    privacyLevel: ["minimal", "balanced", "strict", "custom"].includes(p.privacyLevel) ? p.privacyLevel : "custom",
    interests: strArr(p.interests).filter(interestOk),
    blockedBrands: strArr(p.blockedBrands),
    allowedCategories: Array.from(new Set(strArr(p.allowedCategories).filter((c) => (CATEGORY_TERMS as any)[c] || c === "none"))) as AdCategory[],
    scwGates: p.scwGates.slice(0, 12).map(normalizeGate),
    sessionLimits: {
      maxAdsPerHour: clamp(p.sessionLimits.maxAdsPerHour, 0, 20, 4),
      maxAdsPerDay: clamp(p.sessionLimits.maxAdsPerDay, 0, 100, 15),
      minRelevanceThreshold: clamp(p.sessionLimits.minRelevanceThreshold, 50, 100, 75),
    },
    dataControls: {
      shareConversationTopics: !!p.dataControls.shareConversationTopics, shareSearchHistory: !!p.dataControls.shareSearchHistory,
      shareInteractionPatterns: !!p.dataControls.shareInteractionPatterns, allowPersonalization: !!p.dataControls.allowPersonalization,
    },
  };
  return { ok: true, profile, note: `Imported ${profile.scwGates.length} SCWs from version ${data.version}.${dropped ? ` ${dropped} tier grant${dropped === 1 ? "" : "s"} removed (unknown, legacy L4, or never grantable).` : ""}` };
}

function chatgptInstruction(p: UserAdProfile): string {
  const lines = [
    "Maxey0 SCW privacy profile (advisory). Please follow these preferences when anything in this chat relates to ads or personalization:",
    `- Treat my conversations as separate context worlds: ${p.scwGates.map((g) => `${g.name} (${MODE[g.gateType].label.toLowerCase()})`).join(", ")}. Do not carry details from one into another.`,
    "- Never use my identity, contact details, age, location, occupation or income for ads.",
    "- Never use health, mental health, politics, religion, sexuality or financial hardship topics for ads.",
    `- Only these ad categories are acceptable: ${p.allowedCategories.filter((c) => c !== "none").join(", ") || "none"}.`,
    p.blockedBrands.length ? `- Never show ads from: ${p.blockedBrands.join(", ")}.` : "",
    p.dataControls.allowPersonalization ? "- You may use my stated interests for relevance." : "- Do not use saved memories or inferred interests for ads.",
    p.dataControls.shareSearchHistory ? "" : "- Do not use my search history for ads.",
    `- At most ${p.sessionLimits.maxAdsPerHour} ads per hour and ${p.sessionLimits.maxAdsPerDay} per day, only above ${p.sessionLimits.minRelevanceThreshold}% relevance.`,
  ];
  return lines.filter(Boolean).join("\n");
}

function exportProfile(p: UserAdProfile): string {
  return JSON.stringify({
    version: EXPORT_VERSION, app: "Maxey0 SCWs for ChatGPT Ads", exportedAt: today(), memoryModel: MEMORY_MODEL,
    invariants: INVARIANTS.map((i) => `${i.id}: ${i.text}`), profile: p, chatgptInstruction: chatgptInstruction(p),
  }, null, 2);
}

// ============================================================================
// 3. EVALUATOR: one turn through one SCW
// ============================================================================

type Outcome = "ad" | "held" | "labels" | "sealed" | "suppressed" | "none";
interface Released { label: string; category: Exclude<AdCategory, "none">; tier: MemoryTier }
interface Withheld { label: string; tier: MemoryTier | "Identity"; rule: string }
interface Step { id: string; label: string; pass: boolean; detail: string }
interface TurnResult {
  gateId: string; outcome: Outcome; released: Released[]; withheld: Withheld[]; steps: Step[];
  ad: { cand: AdCandidate; relevance: number; matched: string[] } | null; reason: string; cls: Classification;
}

const OUTCOME_META: Record<Outcome, { label: string; color: string }> = {
  ad: { label: "Ad served", color: "#fbbf24" },
  held: { label: "Ad held for review", color: "#fb923c" },
  labels: { label: "Labels only, no ad", color: "#60a5fa" },
  sealed: { label: "Sealed", color: "#34d399" },
  suppressed: { label: "Suppressed (sensitive)", color: "#c084fc" },
  none: { label: "Nothing to release", color: "#64748b" },
};

function evaluateTurn(p: UserAdProfile, g: SCWPrivacyGate, message: string, history: string[] = [], adsShown = 0): TurnResult {
  const cls = classifyText(message);
  const steps: Step[] = [];
  const released: Released[] = [];
  const withheld: Withheld[] = [];
  const grants = new Set(g.memoryTierAccess.filter((t) => AD_GRANTABLE.has(t)));
  const done = (outcome: Outcome, reason: string, ad: TurnResult["ad"] = null): TurnResult => ({ gateId: g.id, outcome, released, withheld, steps, ad, reason, cls });

  cls.personal.forEach((x) => withheld.push({ label: x.label, tier: "Identity", rule: "INV-1" }));
  steps.push({ id: "INV-1", label: "Identity", pass: true, detail: cls.personal.length ? `${cls.personal.length} identity cue${cls.personal.length === 1 ? "" : "s"} withheld` : "No identity cues" });
  withheld.push({ label: "account & profile", tier: "Persistent", rule: "INV-4" }, { label: "instructions", tier: "Procedural", rule: "INV-4" });

  if (cls.sensitive) {
    steps.push({ id: "INV-3", label: "Sensitive topic", pass: false, detail: `${cls.sensitive.replace("_", " ")} detected: ads suppressed for this turn` });
    cls.labels.forEach((l) => withheld.push({ label: l.label, tier: "Working", rule: "INV-3" }));
    return done("suppressed", `Sensitive topic (${cls.sensitive.replace("_", " ")}): the world is suppressed.`);
  }
  steps.push({ id: "INV-3", label: "Sensitive topic", pass: true, detail: "None detected" });

  const low = message.toLowerCase();
  const hitBlocked = g.blockedTopics.find((t) => hasTerm(low, t));
  if (hitBlocked) {
    steps.push({ id: "BLOCK", label: "Blocked topic", pass: false, detail: `“${hitBlocked}” is blocked in ${g.name}` });
    cls.labels.forEach((l) => withheld.push({ label: l.label, tier: "Working", rule: "BLOCK" }));
    return done("suppressed", `Blocked topic “${hitBlocked}” in this SCW.`);
  }

  if (g.gateType === "block") {
    steps.push({ id: "MODE", label: "SCW mode", pass: false, detail: `${g.name} is sealed` });
    cls.labels.forEach((l) => withheld.push({ label: l.label, tier: "Working", rule: "SEALED" }));
    return done("sealed", `${g.name} is sealed: nothing leaves this world.`);
  }
  steps.push({ id: "MODE", label: "SCW mode", pass: true, detail: MODE[g.gateType].label });

  const allowedCats = new Set(g.allowedCategories.filter((c) => p.allowedCategories.includes(c) && c !== "none"));
  const consider = (label: string, category: Exclude<AdCategory, "none">, tier: MemoryTier, readable: boolean, rule: string) => {
    if (released.some((r) => r.label === label) || withheld.some((w) => w.label === label && w.tier === tier)) return;
    if (!readable) return withheld.push({ label, tier, rule });
    if (!allowedCats.has(category)) return withheld.push({ label, tier, rule: "CATEGORY" });
    released.push({ label, category, tier });
  };

  // Working: the message being written now.
  const wRead = grants.has("Working") && g.dataSharing.conversationContext && p.dataControls.shareConversationTopics;
  cls.labels.forEach((l) => consider(l.label, l.category, "Working", wRead, !grants.has("Working") ? "NO-GRANT" : "SHARE-CTX"));
  steps.push({ id: "W", label: "Working tier", pass: wRead, detail: wRead ? "Current message readable as labels" : !grants.has("Working") ? "Not granted to this SCW" : "Conversation sharing is off" });

  // Episodic: earlier turns in this SCW's session.
  const eRead = grants.has("Episodic") && g.dataSharing.conversationContext && p.dataControls.shareInteractionPatterns;
  const hist = history.flatMap((h) => { const c = classifyText(h); return c.sensitive ? [] : c.labels; });
  hist.forEach((l) => consider(l.label, l.category, "Episodic", eRead, !grants.has("Episodic") ? "NO-GRANT" : "SHARE-SESSION"));
  steps.push({ id: "E", label: "Episodic tier", pass: eRead, detail: eRead ? `${hist.length} label${hist.length === 1 ? "" : "s"} from earlier turns readable` : !grants.has("Episodic") ? "Not granted to this SCW" : "Session sharing is off" });

  // Semantic: stated interests (the profile's concept graph).
  const sRead = grants.has("Semantic") && g.dataSharing.userPreferences && p.dataControls.allowPersonalization;
  p.interests.forEach((i) => {
    const c = classifyText(i);
    const cat = c.categories[0];
    if (!interestOk(i)) return withheld.push({ label: i.trim().slice(0, 40).toLowerCase(), tier: "Semantic", rule: "LENGTH" });
    if (c.sensitive) return withheld.push({ label: i.toLowerCase(), tier: "Semantic", rule: "INV-3" });
    if (!cat) return withheld.push({ label: i.toLowerCase(), tier: "Semantic", rule: "UNCLASSIFIED" });
    consider(i.toLowerCase(), cat, "Semantic", sRead, !grants.has("Semantic") ? "NO-GRANT" : "SHARE-PREFS");
  });
  steps.push({ id: "S", label: "Semantic tier", pass: sRead, detail: sRead ? `${p.interests.length} interest${p.interests.length === 1 ? "" : "s"} readable` : !grants.has("Semantic") ? "Not granted to this SCW" : "Personalization is off" });
  steps.push({ id: "INV-4", label: "Persistent + Procedural", pass: true, detail: "Never readable (locked)" });

  if (!released.length) return done("none", "Nothing in a granted tier matched an allowed category.");

  const cap = Math.min(g.maxAdsPerSession, p.sessionLimits.maxAdsPerHour);
  if (adsShown >= cap) {
    steps.push({ id: "BUDGET", label: "Ad budget", pass: false, detail: `${adsShown} of ${cap} ads already shown this session` });
    return done("labels", "Session ad budget reached.");
  }
  steps.push({ id: "BUDGET", label: "Ad budget", pass: true, detail: `${adsShown} of ${cap} used` });

  const threshold = Math.max(g.requireRelevanceScore, p.sessionLimits.minRelevanceThreshold);
  const blocked = p.blockedBrands.map((b) => b.toLowerCase());
  let best: TurnResult["ad"] = null;
  INVENTORY.forEach((cand) => {
    if (!allowedCats.has(cand.category) || blocked.some((b) => cand.advertiser.toLowerCase().includes(b))) return;
    const matched = released.filter((r) => cand.keywords.some((k) => k === r.label || hasTerm(r.label, k) || hasTerm(k, r.label))).map((r) => r.label);
    if (!matched.length) return;
    const fromWorking = released.some((r) => matched.includes(r.label) && r.tier === "Working");
    const relevance = Math.min(100, 55 + 20 * matched.length + (fromWorking ? 10 : 0));
    if (!best || relevance > best.relevance) best = { cand, relevance, matched };
  });
  const b = best as TurnResult["ad"];
  if (!b || b.relevance < threshold) {
    steps.push({ id: "REL", label: "Relevance", pass: false, detail: b ? `Best match ${b.relevance}% < ${threshold}% required` : "No ad in inventory matched" });
    return done("labels", b ? `Best ad was ${b.relevance}% relevant; this SCW requires ${threshold}%.` : "No ad matched the released labels.");
  }
  steps.push({ id: "REL", label: "Relevance", pass: true, detail: `${b.cand.advertiser} ${b.relevance}% ≥ ${threshold}%` });
  if (g.gateType === "review") return done("held", "Matched ad held until you approve it.", b);
  return done("ad", `Contextual ad from ${b.cand.advertiser}.`, b);
}

// ---- profile-level metrics ----
function gateExposure(p: UserAdProfile, g: SCWPrivacyGate): number {
  const flag: Record<string, boolean> = {
    Working: g.dataSharing.conversationContext && p.dataControls.shareConversationTopics,
    Episodic: g.dataSharing.conversationContext && p.dataControls.shareInteractionPatterns,
    Semantic: g.dataSharing.userPreferences && p.dataControls.allowPersonalization,
  };
  const tiers = g.memoryTierAccess.filter((t) => AD_GRANTABLE.has(t) && flag[t]).reduce((s, t) => s + TIER[t].weight, 0);
  const cats = g.allowedCategories.filter((c) => p.allowedCategories.includes(c) && c !== "none").length;
  return cats === 0 ? 0 : MODE[g.gateType].weight * tiers;
}
function exposureOf(p: UserAdProfile): number {
  if (!p.scwGates.length) return 0;
  return p.scwGates.reduce((s, g) => s + gateExposure(p, g), 0) / p.scwGates.length;
}
const privacyScore = (p: UserAdProfile) => Math.round(100 * (1 - exposureOf(p)));

// ---- replay corpus (synthetic prompts, written for this app) ----
const CORPUS: { text: string; tag: string }[] = [
  { text: "Explain Bayesian statistics with a worked example", tag: "education" },
  { text: "Help me debug this Rust API server on Linux", tag: "technology" },
  { text: "Draft a Q3 roadmap and OKR plan for my startup", tag: "business" },
  { text: "Best trail running shoes for hiking in mud?", tag: "lifestyle" },
  { text: "Kubernetes vs plain cloud VMs for a small devops team", tag: "technology" },
  { text: "A 25 minute weeknight recipe with coffee rub", tag: "lifestyle" },
  { text: "Study plan for my physics exam next week", tag: "education" },
  { text: "Write an invoice reminder email to a client", tag: "business" },
  { text: "My doctor changed my blood pressure medication", tag: "sensitive" },
  { text: "Who should I vote for in the senator election?", tag: "sensitive" },
  { text: "I have so much debt, I can't afford rent", tag: "sensitive" },
  { text: "My therapist says my anxiety is burnout", tag: "sensitive" },
  { text: "My name is Sam, email sam@example.com, fix my Python code", tag: "identity" },
  { text: "I live in Denver, suggest camping trips", tag: "identity" },
  { text: "How do we pay down technical debt in the codebase?", tag: "precision" },
  { text: "Upgrade to TypeScript 5.6 from version 4.9.5", tag: "precision" },
  { text: "Summarize this salary negotiation for client names", tag: "blocked" },
  { text: "What's a good gift for my sister?", tag: "unclassified" },
];

// ============================================================================
// 4. STATE
// ============================================================================

interface Turn { id: string; text: string; result: TurnResult; approved?: boolean }
interface State {
  profile: UserAdProfile; past: UserAdProfile[]; selected: string | null;
  sessions: Record<string, Turn[]>; toast: string | null;
}
type Action =
  | { type: "edit"; note?: string; fn: (p: UserAdProfile) => UserAdProfile }
  | { type: "replace"; profile: UserAdProfile; note: string }
  | { type: "undo" } | { type: "select"; id: string | null }
  | { type: "turn"; gateId: string; turn: Turn } | { type: "approve"; gateId: string; turnId: string; ok: boolean }
  | { type: "clearSession"; gateId: string } | { type: "toast"; msg: string | null };

const initialState = (): State => {
  const profile = PRESETS.balanced.build();
  return { profile, past: [], selected: profile.scwGates[1]?.id ?? null, sessions: {}, toast: null };
};

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "edit": {
      const next = a.fn(s.profile);
      if (next === s.profile) return s;
      const fixed = { ...next, scwGates: next.scwGates.map((g) => ({ ...g, memoryTierAccess: normalizeMemoryTiers(g.memoryTierAccess), dataSharing: { ...g.dataSharing, behavioralData: false, demographicData: false } })) };
      return { ...s, profile: fixed, past: [...s.past, s.profile].slice(-40), toast: a.note ?? s.toast };
    }
    case "replace":
      return { ...s, profile: a.profile, past: [...s.past, s.profile].slice(-40), sessions: {}, selected: a.profile.scwGates[0]?.id ?? null, toast: a.note };
    case "undo":
      if (!s.past.length) return s;
      return { ...s, profile: s.past[s.past.length - 1], past: s.past.slice(0, -1), toast: "Undid the last change." };
    case "select": return { ...s, selected: a.id };
    case "turn": return { ...s, sessions: { ...s.sessions, [a.gateId]: [...(s.sessions[a.gateId] ?? []), a.turn].slice(-30) } };
    case "approve": return { ...s, sessions: { ...s.sessions, [a.gateId]: (s.sessions[a.gateId] ?? []).map((t) => (t.id === a.turnId ? { ...t, approved: a.ok } : t)) } };
    case "clearSession": return { ...s, sessions: { ...s.sessions, [a.gateId]: [] } };
    case "toast": return { ...s, toast: a.msg };
  }
}

const custom = (p: UserAdProfile): UserAdProfile => ({ ...p, privacyLevel: "custom" });
const updGate = (id: string, fn: (g: SCWPrivacyGate) => SCWPrivacyGate) => (p: UserAdProfile) => custom({ ...p, scwGates: p.scwGates.map((g) => (g.id === id ? fn(g) : g)) });

// ============================================================================
// 5. STYLE + UI PRIMITIVES
// ============================================================================

const CSS = `
.mx{--bg:#05060d;--bg2:#0b0e1c;--panel:rgba(18,22,42,.72);--line:rgba(148,163,255,.14);--line2:rgba(148,163,255,.28);--ink:#e8ebff;--mute:#8e97c2;--dim:#5b638c;--acc:#7c8cff;--acc2:#22d3ee;--good:#34d399;--warn:#fbbf24;--bad:#f87171;--vio:#c084fc;
 font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,sans-serif;color:var(--ink);background:radial-gradient(1200px 700px at 12% -10%,#1b1f4b 0%,transparent 60%),radial-gradient(900px 600px at 110% 10%,#1f0f3d 0%,transparent 55%),var(--bg);min-height:100vh;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.mx *{box-sizing:border-box}.mx button{font:inherit;color:inherit}
.mx .shell{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
.mx .side{position:sticky;top:0;height:100vh;padding:18px 14px;border-right:1px solid var(--line);background:linear-gradient(180deg,rgba(10,12,26,.9),rgba(6,7,16,.9));display:flex;flex-direction:column;gap:14px}
.mx .brand{display:flex;gap:10px;align-items:center;padding:4px 6px 10px}
.mx .logo{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:conic-gradient(from 200deg,#22d3ee,#7c8cff,#c084fc,#22d3ee);box-shadow:0 0 24px rgba(124,140,255,.45)}
.mx .logo>div{width:28px;height:28px;border-radius:8px;background:#0a0c1c;display:grid;place-items:center}
.mx .brand b{display:block;font-size:14px;letter-spacing:.2px}.mx .brand span{font-size:11px;color:var(--mute)}
.mx .nav{display:flex;flex-direction:column;gap:2px}
.mx .nav button{display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:10px;border:1px solid transparent;background:none;cursor:pointer;color:var(--mute);text-align:left}
.mx .nav button:hover{color:var(--ink);background:rgba(124,140,255,.07)}
.mx .nav button[aria-current=page]{color:var(--ink);background:linear-gradient(90deg,rgba(124,140,255,.18),rgba(124,140,255,.03));border-color:var(--line2)}
.mx .nav small{margin-left:auto;font-size:10px;color:var(--dim)}
.mx .sidefoot{margin-top:auto;font-size:11px;color:var(--dim);padding:8px}
.mx main{min-width:0;padding:22px 26px 60px}
.mx .top{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.mx .top h1{font-size:22px;margin:0;letter-spacing:-.3px}.mx .top p{margin:2px 0 0;color:var(--mute);font-size:13px}
.mx .top .grow{flex:1;min-width:200px}
.mx .pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;border:1px solid var(--line2);background:rgba(10,12,28,.6);font-size:12px;color:var(--mute);white-space:nowrap}
.mx .grid{display:grid;gap:16px}.mx .g2{grid-template-columns:repeat(2,minmax(0,1fr))}.mx .g3{grid-template-columns:repeat(3,minmax(0,1fr))}.mx .g4{grid-template-columns:repeat(4,minmax(0,1fr))}
.mx .g-map{grid-template-columns:minmax(0,1fr) 340px}
.mx .span2{grid-column:span 2}
.mx .panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;backdrop-filter:blur(8px);box-shadow:0 1px 0 rgba(255,255,255,.03) inset,0 20px 50px -30px rgba(0,0,0,.8);min-width:0}
.mx .ph{display:flex;align-items:flex-start;gap:10px;margin-bottom:12px}.mx .ph h2{font-size:14px;margin:0;letter-spacing:.1px}.mx .ph p{margin:2px 0 0;font-size:12px;color:var(--mute)}.mx .ph .r{margin-left:auto;display:flex;gap:6px;align-items:center}
.mx .kick{font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:var(--acc2);font-weight:600}
.mx .btn{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:10px;border:1px solid var(--line2);background:rgba(124,140,255,.12);cursor:pointer;font-size:13px;transition:.15s}
.mx .btn:hover{background:rgba(124,140,255,.22);border-color:rgba(148,163,255,.45)}.mx .btn:disabled{opacity:.45;cursor:not-allowed}
.mx .btn.pri{background:linear-gradient(135deg,#5b6cff,#8b5cf6);border-color:transparent;box-shadow:0 8px 24px -10px rgba(124,92,255,.8)}
.mx .btn.ghost{background:none}.mx .btn.sm{padding:4px 9px;font-size:12px;border-radius:8px}.mx .btn.danger:hover{border-color:var(--bad);color:var(--bad)}
.mx .seg{display:inline-flex;padding:3px;border-radius:11px;border:1px solid var(--line);background:rgba(5,6,14,.6);gap:2px;flex-wrap:wrap}
.mx .seg button{border:0;background:none;padding:5px 10px;border-radius:8px;cursor:pointer;color:var(--mute);font-size:12px}
.mx .seg button[aria-pressed=true]{background:var(--c,rgba(124,140,255,.25));color:#050611;font-weight:600}
.mx .chip{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;font-size:12px;border:1px solid var(--line2);background:rgba(255,255,255,.03);white-space:nowrap}
.mx .chip.x{cursor:pointer}.mx .chip.x:hover{border-color:var(--bad)}
.mx .chips{display:flex;flex-wrap:wrap;gap:6px}
.mx .tog{position:relative;width:38px;height:22px;border-radius:999px;border:1px solid var(--line2);background:#161a33;cursor:pointer;flex:none;transition:.2s}
.mx .tog::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#8e97c2;transition:.2s}
.mx .tog[aria-checked=true]{background:linear-gradient(135deg,#22d3ee,#7c8cff);border-color:transparent}.mx .tog[aria-checked=true]::after{left:18px;background:#fff}
.mx .tog:disabled{opacity:.4;cursor:not-allowed}
.mx .row{display:flex;align-items:center;gap:10px}.mx .row.wrap{flex-wrap:wrap}.mx .between{justify-content:space-between}
.mx .field{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}.mx label.lbl{font-size:12px;color:var(--mute)}
.mx input[type=text],.mx textarea{width:100%;background:rgba(3,4,12,.7);border:1px solid var(--line2);border-radius:10px;color:var(--ink);padding:8px 10px;font:inherit;outline:none}
.mx input[type=text]:focus,.mx textarea:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(124,140,255,.18)}
.mx textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;resize:vertical}
.mx input[type=range]{width:100%;accent-color:#7c8cff}
.mx .muted{color:var(--mute)}.mx .dim{color:var(--dim)}.mx .small{font-size:12px}.mx .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.mx .num{font-variant-numeric:tabular-nums}
.mx .big{font-size:30px;font-weight:700;letter-spacing:-.8px}
.mx .stat{padding:14px;border-radius:14px;border:1px solid var(--line);background:linear-gradient(160deg,rgba(124,140,255,.08),rgba(0,0,0,0))}
.mx .stat .k{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:1px}
.mx .toast{position:fixed;right:18px;bottom:18px;z-index:50;max-width:380px;padding:10px 14px;border-radius:12px;background:#12163a;border:1px solid var(--line2);box-shadow:0 20px 40px -10px rgba(0,0,0,.7);font-size:13px;display:flex;gap:10px;align-items:center;animation:mxin .25s ease}
@keyframes mxin{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
@keyframes mxdash{to{stroke-dashoffset:-24}}
@keyframes mxpulse{0%,100%{opacity:.55}50%{opacity:1}}
.mx .flow{animation:mxdash 1.6s linear infinite}
.mx table{width:100%;border-collapse:collapse;font-size:12px}.mx th{text-align:left;font-weight:600;color:var(--mute);padding:6px 8px;border-bottom:1px solid var(--line)}.mx td{padding:6px 8px;border-bottom:1px solid rgba(148,163,255,.07);vertical-align:top}
.mx .scrollx{overflow-x:auto}
.mx .canvaswrap{position:relative;width:100%;aspect-ratio:1/1;max-height:760px;border-radius:16px;overflow:hidden;border:1px solid var(--line);background:radial-gradient(circle at 50% 50%,#0d1030 0%,#05060d 70%)}
.mx .canvaswrap canvas{position:absolute;inset:0;width:100%;height:100%}
.mx .tip{position:absolute;pointer-events:none;z-index:5;max-width:260px;padding:9px 11px;border-radius:10px;background:rgba(8,10,26,.94);border:1px solid var(--line2);font-size:12px;box-shadow:0 10px 30px rgba(0,0,0,.6)}
.mx .overlay{position:absolute;display:flex;gap:6px;flex-wrap:wrap}
.mx .legend{position:absolute;left:12px;bottom:12px;padding:10px 12px;border-radius:12px;background:rgba(5,6,14,.78);border:1px solid var(--line);font-size:11px;display:grid;gap:4px}
.mx .dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
.mx .step{display:flex;gap:10px;align-items:flex-start;padding:7px 0}
.mx .step .ic{width:22px;height:22px;border-radius:7px;display:grid;place-items:center;flex:none;font-size:11px;font-weight:700}
.mx .adcard{border-radius:14px;padding:14px;border:1px solid rgba(251,191,36,.4);background:linear-gradient(135deg,rgba(251,191,36,.12),rgba(244,114,182,.06))}
.mx .bubble{padding:10px 12px;border-radius:14px 14px 4px 14px;background:linear-gradient(135deg,#2c3380,#3b2a7a);max-width:92%;margin-left:auto}
.mx .cell{width:100%;height:26px;border-radius:6px;border:1px solid rgba(255,255,255,.06);cursor:pointer;transition:transform .12s}
.mx .cell:hover{transform:scale(1.12);outline:2px solid #fff}
.mx .redact{background:repeating-linear-gradient(45deg,#1a1d38 0 6px,#23274a 6px 12px);color:transparent;border-radius:4px;user-select:none}
.mx .lesson{display:grid;grid-template-columns:36px 1fr;gap:12px;padding:12px;border-radius:14px;border:1px solid var(--line);cursor:pointer;background:rgba(255,255,255,.015);text-align:left;width:100%}
.mx .lesson[aria-expanded=true]{border-color:var(--acc);background:rgba(124,140,255,.07)}
.mx .lesson .n{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;font-weight:700;background:rgba(124,140,255,.15);color:var(--acc)}
.mx .mobnav{display:none}
@media (max-width:1100px){.mx .g-map{grid-template-columns:1fr}.mx .g4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:900px){.mx .shell{grid-template-columns:1fr}.mx .side{display:none}.mx main{padding:14px 16px 70px}
 .mx .mobnav{display:flex;position:sticky;top:0;z-index:20;gap:4px;overflow-x:auto;padding:8px 16px;background:rgba(5,6,13,.92);border-bottom:1px solid var(--line);backdrop-filter:blur(8px)}
 .mx .mobnav button{flex:none;border:1px solid var(--line);background:none;border-radius:999px;padding:6px 12px;font-size:12px;color:var(--mute);cursor:pointer}
 .mx .mobnav button[aria-current=page]{color:#050611;background:var(--ink)}
 .mx .g2,.mx .g3{grid-template-columns:1fr}.mx .span2{grid-column:auto}}
@media (max-width:600px){.mx .legend{display:none}}
@media (max-width:520px){.mx .g4{grid-template-columns:1fr 1fr}.mx .big{font-size:24px}}
@media (prefers-reduced-motion:reduce){.mx .flow{animation:none}.mx .toast{animation:none}}
`;

const Panel: React.FC<{ title?: React.ReactNode; sub?: React.ReactNode; kicker?: string; right?: React.ReactNode; className?: string; children?: React.ReactNode; id?: string }> = ({ title, sub, kicker, right, className, children, id }) => (
  <section className={`panel ${className ?? ""}`} id={id} aria-label={typeof title === "string" ? title : undefined}>
    {(title || right) && (
      <div className="ph">
        <div>{kicker && <div className="kick">{kicker}</div>}{title && <h2>{title}</h2>}{sub && <p>{sub}</p>}</div>
        {right && <div className="r">{right}</div>}
      </div>
    )}
    {children}
  </section>
);
const Toggle: React.FC<{ on: boolean; onChange?: (v: boolean) => void; label: string; disabled?: boolean }> = ({ on, onChange, label, disabled }) => (
  <button type="button" role="switch" aria-checked={on} aria-label={label} className="tog" disabled={disabled} onClick={() => onChange?.(!on)} />
);
function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { id: T; label: string; color?: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" aria-pressed={value === o.id} style={{ ["--c" as any]: o.color ?? "#c7ceff" }} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}
const Chip: React.FC<{ color?: string; children: React.ReactNode; onRemove?: () => void; title?: string }> = ({ color, children, onRemove, title }) => (
  <span className={`chip ${onRemove ? "x" : ""}`} title={title} style={color ? { borderColor: color + "88", color } : undefined} onClick={onRemove} role={onRemove ? "button" : undefined} aria-label={onRemove ? `Remove ${String(children)}` : undefined}>
    {children}{onRemove && <span aria-hidden>×</span>}
  </span>
);
const RuleChip: React.FC<{ rule: string }> = ({ rule }) => {
  const c = rule.startsWith("INV") ? "#c084fc" : rule === "SEALED" ? "#34d399" : rule === "CATEGORY" ? "#fbbf24" : "#8e97c2";
  return <span className="chip mono" style={{ fontSize: 10, borderColor: c + "77", color: c }}>{rule}</span>;
};

const TagInput: React.FC<{ placeholder: string; onAdd: (v: string) => void; label: string }> = ({ placeholder, onAdd, label }) => {
  const [v, setV] = useState("");
  const go = () => { const t = v.trim(); if (t) { onAdd(t); setV(""); } };
  return (
    <div className="row">
      <input type="text" aria-label={label} placeholder={placeholder} value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} />
      <button type="button" className="btn sm" onClick={go}><Plus size={14} />Add</button>
    </div>
  );
};

function useReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    if (!m) return;
    setR(m.matches);
    const f = () => setR(m.matches);
    m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return r;
}

// ============================================================================
// 6. VISUALIZATIONS
// ============================================================================

/** Score dial: 270° arc, gradient, ticks. */
const ScoreDial: React.FC<{ score: number; size?: number }> = ({ score, size = 168 }) => {
  const r = size / 2 - 14, cx = size / 2, cy = size / 2, sweep = 270, start = 135;
  const pt = (deg: number, rr = r) => [cx + rr * Math.cos((deg * Math.PI) / 180), cy + rr * Math.sin((deg * Math.PI) / 180)];
  const arc = (a0: number, a1: number) => { const [x0, y0] = pt(a0), [x1, y1] = pt(a1); return `M${x0} ${y0} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1} ${y1}`; };
  const end = start + (sweep * Math.max(0.5, score)) / 100;
  const col = score >= 80 ? "#34d399" : score >= 60 ? "#60a5fa" : score >= 40 ? "#fbbf24" : "#f87171";
  const label = score >= 80 ? "Excellent" : score >= 60 ? "Good" : score >= 40 ? "Moderate" : "Exposed";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Privacy score ${score} of 100, ${label}`}>
      <defs><linearGradient id="dialg" x1="0" x2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor={col} /></linearGradient>
        <filter id="dglow"><feGaussianBlur stdDeviation="3" /></filter></defs>
      {Array.from({ length: 28 }, (_, i) => { const d = start + (sweep * i) / 27; const [a, b] = pt(d, r + 9), [c, e] = pt(d, r + (i % 3 === 0 ? 4 : 6)); return <line key={i} x1={a} y1={b} x2={c} y2={e} stroke="#3a4170" strokeWidth={1.2} />; })}
      <path d={arc(start, start + sweep)} stroke="#1a1f42" strokeWidth={11} fill="none" strokeLinecap="round" />
      <path d={arc(start, end)} stroke="url(#dialg)" strokeWidth={11} fill="none" strokeLinecap="round" filter="url(#dglow)" opacity={0.6} />
      <path d={arc(start, end)} stroke="url(#dialg)" strokeWidth={11} fill="none" strokeLinecap="round" />
      <text x={cx} y={cy + 4} textAnchor="middle" fill="#fff" fontSize={size * 0.26} fontWeight={700} className="num">{score}</text>
      <text x={cx} y={cy + size * 0.2} textAnchor="middle" fill={col} fontSize={12} fontWeight={600}>{label}</text>
    </svg>
  );
};

/** Latent Field: animated canvas of the whole privacy boundary. */
interface Probe { cand: AdCandidate; gi: number; t: number; speed: number; admit: boolean; x0: number; y0: number; done: boolean; bounce: number }
interface Burst { x: number; y: number; t: number; color: string }

const LatentField: React.FC<{ profile: UserAdProfile; selected: string | null; onSelect: (id: string | null) => void; paused: boolean; onCounts?: (c: { admitted: number; blocked: number }) => void }> = ({ profile, selected, onSelect, paused, onCounts }) => {
  const wrap = useRef<HTMLDivElement>(null);
  const cvs = useRef<HTMLCanvasElement>(null);
  const live = useRef({ profile, selected, paused });
  live.current = { profile, selected, paused };
  const hover = useRef<{ x: number; y: number } | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; html: React.ReactNode } | null>(null);
  const hits = useRef<{ kind: string; id: string; x: number; y: number; r: number; info: React.ReactNode }[]>([]);
  const reduced = useReducedMotion();

  useEffect(() => {
    const c = cvs.current!, w = wrap.current!;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    let W = 0, H = 0, raf = 0, last = performance.now(), T = 0, emit = 0, admitted = 0, blocked = 0, lastReport = 0;
    const probes: Probe[] = [];
    const bursts: Burst[] = [];
    const stars = Array.from({ length: 140 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 1.2 + 0.2, p: Math.random() * 6 }));
    const resize = () => {
      const r = w.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
      W = r.width; H = r.height; c.width = Math.max(1, W * d); c.height = Math.max(1, H * d); ctx.setTransform(d, 0, 0, d, 0, 0);
    };
    resize();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    ro?.observe(w);

    const admits = (p: UserAdProfile, g: SCWPrivacyGate, cand: AdCandidate) =>
      g.gateType !== "block" && g.allowedCategories.includes(cand.category) && p.allowedCategories.includes(cand.category) &&
      g.dataSharing.conversationContext && p.dataControls.shareConversationTopics && g.memoryTierAccess.includes("Working") &&
      !p.blockedBrands.some((b) => cand.advertiser.toLowerCase().includes(b.toLowerCase()));

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      const { profile: p, selected: sel, paused: ps } = live.current;
      const speed = ps ? 0 : reduced ? 0.25 : 1;
      T += dt * speed;
      const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 18;
      const gates = p.scwGates;
      const score = privacyScore(p);
      const H2: typeof hits.current = [];

      ctx.clearRect(0, 0, W, H);
      // stars + polar grid
      stars.forEach((s) => { ctx.globalAlpha = 0.25 + 0.35 * (0.5 + 0.5 * Math.sin(T * 1.3 + s.p)); ctx.fillStyle = "#c7d2ff"; ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r, 0, 7); ctx.fill(); });
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "rgba(124,140,255,0.06)"; ctx.lineWidth = 1;
      for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R); ctx.stroke(); }

      // advertiser membrane
      const memR = R * 0.86;
      const mg = ctx.createRadialGradient(cx, cy, memR * 0.96, cx, cy, memR * 1.05);
      mg.addColorStop(0, "rgba(124,140,255,0)"); mg.addColorStop(0.5, `rgba(124,140,255,${0.08 + (score / 100) * 0.18})`); mg.addColorStop(1, "rgba(124,140,255,0)");
      ctx.fillStyle = mg; ctx.beginPath(); ctx.arc(cx, cy, memR * 1.05, 0, 7); ctx.arc(cx, cy, memR * 0.96, 0, 7, true); ctx.fill();
      ctx.setLineDash([2, 8]); ctx.strokeStyle = "rgba(160,170,255,.35)"; ctx.lineDashOffset = -T * 12;
      ctx.beginPath(); ctx.arc(cx, cy, memR, 0, 7); ctx.stroke(); ctx.setLineDash([]);

      // tier rings
      const ringR: Record<string, number> = { Working: R * 0.6, Episodic: R * 0.47, Semantic: R * 0.34 };
      (["Working", "Episodic", "Semantic"] as MemoryTier[]).forEach((t, k) => {
        const n = gates.filter((g) => g.memoryTierAccess.includes(t)).length;
        const frac = gates.length ? n / gates.length : 0;
        const col = TIER[t].color;
        ctx.strokeStyle = col; ctx.globalAlpha = 0.15 + 0.55 * frac; ctx.lineWidth = 1.5 + frac * 2.5;
        ctx.setLineDash([6 + k * 3, 6]); ctx.lineDashOffset = (k % 2 ? 1 : -1) * T * (10 + k * 4);
        ctx.beginPath(); ctx.arc(cx, cy, ringR[t], 0, 7); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
        const la = -Math.PI / 2 - 0.12 - k * 0.1;
        ctx.fillStyle = col; ctx.font = "600 11px ui-sans-serif,system-ui"; ctx.textAlign = "center";
        ctx.fillText(`${t} · ${n}/${gates.length}`, cx + Math.cos(la) * ringR[t], cy + Math.sin(la) * ringR[t] - 6);
        H2.push({ kind: "ring", id: t, x: cx, y: cy, r: ringR[t], info: <><b style={{ color: col }}>{t}</b><div className="muted">{TIER[t].holds}</div><div>In ChatGPT: {TIER[t].chatgpt}</div><div className="small">Granted to {n} of {gates.length} SCWs</div></> });
      });

      // sealed core: Persistent + Procedural
      const coreR = R * 0.2;
      (["Persistent", "Procedural"] as MemoryTier[]).forEach((t, k) => {
        const a0 = -Math.PI / 2 + k * Math.PI + 0.08, a1 = a0 + Math.PI - 0.16;
        ctx.strokeStyle = TIER[t].color; ctx.lineWidth = 7; ctx.globalAlpha = 0.85;
        ctx.beginPath(); ctx.arc(cx, cy, coreR, a0, a1); ctx.stroke(); ctx.globalAlpha = 1;
        const lx = cx + (k === 0 ? 1 : -1) * (coreR + 12);
        ctx.fillStyle = TIER[t].color; ctx.font = "600 10px ui-sans-serif,system-ui"; ctx.textAlign = k === 0 ? "left" : "right";
        ctx.fillText(`🔒 ${t}`, lx, cy + 3); ctx.textAlign = "center";
      });
      H2.push({ kind: "core", id: "sealed", x: cx, y: cy, r: coreR + 6, info: <><b>Sealed core</b><div className="muted">Persistent (account, profile) and Procedural (instructions, this profile).</div><div>INV-4: never grantable to any SCW.</div></> });
      // you
      const pulse = 1 + 0.06 * Math.sin(T * 2.2);
      const yg = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 0.75 * pulse);
      yg.addColorStop(0, "#ffffff"); yg.addColorStop(0.35, "#a5b4fc"); yg.addColorStop(1, "rgba(124,140,255,0)");
      ctx.fillStyle = yg; ctx.beginPath(); ctx.arc(cx, cy, coreR * 0.75 * pulse, 0, 7); ctx.fill();
      ctx.fillStyle = "#070817"; ctx.font = "700 12px ui-sans-serif,system-ui"; ctx.fillText("YOU", cx, cy - 2);
      ctx.font = "600 10px ui-sans-serif,system-ui"; ctx.fillText(`${score}`, cx, cy + 11);

      // gates
      const gR = R * 0.76;
      const gpos = gates.map((g, i) => {
        const a = (i / Math.max(1, gates.length)) * Math.PI * 2 - Math.PI / 2 + T * 0.035;
        return { g, a, x: cx + Math.cos(a) * gR, y: cy + Math.sin(a) * gR };
      });
      gpos.forEach(({ g, a, x, y }) => {
        const m = MODE[g.gateType], isSel = sel === g.id;
        // channels from granted tiers
        g.memoryTierAccess.forEach((t, k) => {
          const rr = ringR[t]; if (!rr) return;
          const flowing = gateExposure(p, g) > 0 && (t === "Semantic" ? g.dataSharing.userPreferences && p.dataControls.allowPersonalization : g.dataSharing.conversationContext);
          const sx = cx + Math.cos(a) * rr, sy = cy + Math.sin(a) * rr;
          const off = (k - 1) * 5;
          const nx = -Math.sin(a) * off, ny = Math.cos(a) * off;
          ctx.strokeStyle = TIER[t].color; ctx.globalAlpha = flowing ? 0.55 : 0.18; ctx.lineWidth = isSel ? 2 : 1.2;
          if (!flowing) ctx.setLineDash([3, 4]);
          ctx.beginPath(); ctx.moveTo(sx + nx, sy + ny); ctx.lineTo(x + nx - Math.cos(a) * 20, y + ny - Math.sin(a) * 20); ctx.stroke(); ctx.setLineDash([]);
          if (flowing && speed > 0) for (let q = 0; q < 3; q++) {
            const f = (T * 0.6 + q / 3 + k * 0.17) % 1;
            const px = sx + (x - Math.cos(a) * 20 - sx) * f + nx, py = sy + (y - Math.sin(a) * 20 - sy) * f + ny;
            ctx.globalAlpha = 0.9 * Math.sin(f * Math.PI); ctx.fillStyle = TIER[t].color; ctx.beginPath(); ctx.arc(px, py, 2, 0, 7); ctx.fill();
          }
          ctx.globalAlpha = 1;
        });
        // world node
        const ww = Math.max(72, Math.min(96, R * 0.34)), hh = ww < 90 ? 32 : 36;
        if (isSel) { ctx.shadowColor = m.color; ctx.shadowBlur = 24; }
        ctx.fillStyle = "rgba(10,12,30,.92)"; ctx.strokeStyle = m.color; ctx.lineWidth = isSel ? 2.4 : 1.4;
        const rx = x - ww / 2, ry = y - hh / 2, rad = 9;
        ctx.beginPath(); ctx.moveTo(rx + rad, ry); ctx.arcTo(rx + ww, ry, rx + ww, ry + hh, rad); ctx.arcTo(rx + ww, ry + hh, rx, ry + hh, rad); ctx.arcTo(rx, ry + hh, rx, ry, rad); ctx.arcTo(rx, ry, rx + ww, ry, rad); ctx.closePath();
        ctx.fill(); ctx.stroke(); ctx.shadowBlur = 0;
        ctx.fillStyle = m.color; ctx.beginPath(); ctx.arc(rx + 10, ry + 10, 3, 0, 7); ctx.fill();
        ctx.fillStyle = "#e8ebff"; ctx.font = "600 11px ui-sans-serif,system-ui"; ctx.textAlign = "center";
        ctx.fillText(g.name.length > 12 ? g.name.slice(0, 11) + "…" : g.name, x + 3, y - 2);
        ctx.fillStyle = m.color; ctx.font = "600 9px ui-sans-serif,system-ui"; ctx.fillText(m.label.toUpperCase(), x - 6, y + 11);
        // tier pips
        (["Working", "Episodic", "Semantic"] as MemoryTier[]).forEach((t, k) => {
          ctx.fillStyle = g.memoryTierAccess.includes(t) ? TIER[t].color : "#262b50";
          ctx.fillRect(rx + ww - 24 + k * 7, ry + hh - 7, 5, 3);
        });
        const exp = gateExposure(p, g);
        H2.push({ kind: "gate", id: g.id, x, y, r: 46, info: <><b>{g.name}</b> <span style={{ color: m.color }}>· {m.label}</span><div className="muted">{m.blurb}</div><div>Tiers: {g.memoryTierAccess.join(", ") || "none"}</div><div>Categories: {g.allowedCategories.join(", ") || "none"}</div><div>Exposure {Math.round(exp * 100)}% · click to edit</div></> });
      });

      // campaigns
      const aR = R * 0.97;
      const apos = INVENTORY.map((cand, i) => {
        const a = (i / INVENTORY.length) * Math.PI * 2 + T * -0.02 + 0.2;
        return { cand, x: cx + Math.cos(a) * aR, y: cy + Math.sin(a) * aR };
      });
      apos.forEach(({ cand, x, y }) => {
        const col = CAT_COLOR[cand.category];
        const brandBlocked = p.blockedBrands.some((b) => cand.advertiser.toLowerCase().includes(b.toLowerCase()));
        ctx.globalAlpha = brandBlocked ? 0.25 : 0.9;
        ctx.fillStyle = col; ctx.beginPath();
        ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
        H2.push({ kind: "ad", id: cand.id, x, y, r: 12, info: <><b style={{ color: col }}>{cand.advertiser}</b> <span className="dim">(fictional)</span><div className="muted">{cand.category} · “{cand.headline}”</div><div>Targets: {cand.keywords.slice(0, 5).join(", ")}</div>{brandBlocked && <div style={{ color: "#f87171" }}>You blocked this brand</div>}</> });
      });

      // probes
      if (speed > 0 && gates.length) {
        emit -= dt * speed;
        if (emit <= 0) {
          emit = 0.45 + Math.random() * 0.4;
          const ai = Math.floor(Math.random() * apos.length), gi = Math.floor(Math.random() * gates.length);
          probes.push({ cand: apos[ai].cand, gi, t: 0, speed: 0.55 + Math.random() * 0.3, admit: admits(p, gates[gi], apos[ai].cand), x0: apos[ai].x, y0: apos[ai].y, done: false, bounce: 0 });
        }
      }
      for (let i = probes.length - 1; i >= 0; i--) {
        const pr = probes[i];
        const gp = gpos[pr.gi];
        if (!gp) { probes.splice(i, 1); continue; }
        pr.t += dt * pr.speed * speed;
        const col = CAT_COLOR[pr.cand.category];
        const stop = pr.admit ? 1 : 0.72;
        if (!pr.done) {
          const f = Math.min(pr.t, stop);
          const e = f * f * (3 - 2 * f);
          const px = pr.x0 + (gp.x - pr.x0) * e, py = pr.y0 + (gp.y - pr.y0) * e;
          ctx.strokeStyle = col; ctx.globalAlpha = 0.35; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(pr.x0 + (gp.x - pr.x0) * Math.max(0, e - 0.15), pr.y0 + (gp.y - pr.y0) * Math.max(0, e - 0.15)); ctx.lineTo(px, py); ctx.stroke();
          ctx.globalAlpha = 1; ctx.fillStyle = col; ctx.beginPath(); ctx.arc(px, py, 2.6, 0, 7); ctx.fill();
          if (pr.t >= stop) {
            pr.done = true;
            bursts.push({ x: px, y: py, t: 0, color: pr.admit ? "#34d399" : "#f87171" });
            pr.admit ? admitted++ : blocked++;
            pr.x0 = px; pr.y0 = py;
          }
        } else {
          pr.bounce += dt * speed;
          if (!pr.admit) {
            const ox = pr.x0 - cx, oy = pr.y0 - cy, len = Math.hypot(ox, oy) || 1;
            const bx = pr.x0 + (ox / len) * pr.bounce * 60, by = pr.y0 + (oy / len) * pr.bounce * 60;
            ctx.globalAlpha = Math.max(0, 1 - pr.bounce * 1.6); ctx.fillStyle = "#f87171"; ctx.beginPath(); ctx.arc(bx, by, 2.2, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
          }
          if (pr.bounce > 0.7) probes.splice(i, 1);
        }
      }
      for (let i = bursts.length - 1; i >= 0; i--) {
        const b = bursts[i]; b.t += dt * speed * 1.6;
        ctx.strokeStyle = b.color; ctx.globalAlpha = Math.max(0, 1 - b.t); ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.arc(b.x, b.y, 4 + b.t * 18, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
        if (b.t >= 1) bursts.splice(i, 1);
      }

      hits.current = H2;
      if (onCounts && now - lastReport > 400) { lastReport = now; onCounts({ admitted, blocked }); }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); };
  }, [reduced, onCounts]);

  const find = (e: React.MouseEvent) => {
    const r = wrap.current!.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const order = ["gate", "ad", "core", "ring"];
    for (const k of order) {
      for (const h of hits.current.filter((q) => q.kind === k)) {
        const d = Math.hypot(x - h.x, y - h.y);
        if (k === "ring" ? Math.abs(d - h.r) < 8 : d < h.r) return { h, x, y, w: r.width };
      }
    }
    return { h: null, x, y, w: r.width };
  };
  return (
    <div className="canvaswrap" ref={wrap}
      onMouseMove={(e) => { const f = find(e); hover.current = { x: f.x, y: f.y }; setTip(f.h ? { x: Math.min(f.x + 14, f.w - 270), y: f.y + 14, html: f.h.info } : null); (e.currentTarget as HTMLDivElement).style.cursor = f.h?.kind === "gate" ? "pointer" : "default"; }}
      onMouseLeave={() => setTip(null)}
      onClick={(e) => { const f = find(e); if (f.h?.kind === "gate") onSelect(f.h.id); }}>
      <canvas ref={cvs} role="img" aria-label="Latent map: your sealed core, three grantable memory tiers, your SCWs orbiting them, and fictional advertisers probing from outside. Green bursts are admitted probes; red bursts are blocked." />
      {tip && <div className="tip" style={{ left: tip.x, top: tip.y }}>{tip.html}</div>}
      <div className="legend" aria-hidden>
        <div className="row"><span className="dot" style={{ background: "#fff" }} />You · privacy score</div>
        <div className="row"><span className="dot" style={{ background: "#f87171" }} /><span className="dot" style={{ background: "#a78bfa" }} />Sealed core (INV-4)</div>
        <div className="row">{(["Working", "Episodic", "Semantic"] as MemoryTier[]).map((t) => <span key={t} className="dot" style={{ background: TIER[t].color }} />)}Grantable tiers</div>
        <div className="row"><span className="dot" style={{ background: "#7c8cff", borderRadius: 3 }} />SCW worlds (click)</div>
        <div className="row">{CATEGORIES.map((c) => <span key={c.id} className="dot" style={{ background: c.color, borderRadius: 1, transform: "rotate(45deg)" }} />)}Fictional advertisers</div>
      </div>
    </div>
  );
};

/** Exposure flow: memory tiers → SCWs → advertiser / withheld. Band width = units of data. */
const ExposureFlow: React.FC<{ profile: UserAdProfile; onSelect: (id: string) => void; selected: string | null }> = ({ profile, onSelect, selected }) => {
  const [hov, setHov] = useState<string | null>(null);
  const W = 760, gates = profile.scwGates, rows = Math.max(gates.length, 5), H = Math.max(300, rows * 58 + 30);
  const srcs = [...TIERS.map((t) => ({ id: t.id, label: t.id, color: t.color })), { id: "Identity", label: "Identity cues", color: "#e879f9" }];
  const unit = 5;
  type L = { id: string; from: string; to: string; flows: boolean; color: string; w: number };
  const l1: L[] = [], l2: L[] = [];
  const flowsFor = (g: SCWPrivacyGate, t: string) => {
    if (!AD_GRANTABLE.has(t as MemoryTier) || !g.memoryTierAccess.includes(t as MemoryTier) || g.gateType === "block") return false;
    if (!g.allowedCategories.some((c) => profile.allowedCategories.includes(c))) return false;
    if (t === "Working") return g.dataSharing.conversationContext && profile.dataControls.shareConversationTopics;
    if (t === "Episodic") return g.dataSharing.conversationContext && profile.dataControls.shareInteractionPatterns;
    return g.dataSharing.userPreferences && profile.dataControls.allowPersonalization;
  };
  gates.forEach((g) => {
    let rel = 0, wh = 0;
    srcs.forEach((s) => { const f = flowsFor(g, s.id); f ? rel++ : wh++; l1.push({ id: `${s.id}>${g.id}`, from: s.id, to: g.id, flows: f, color: s.color, w: unit }); });
    if (rel) l2.push({ id: `${g.id}>adv`, from: g.id, to: "adv", flows: true, color: MODE[g.gateType].color, w: rel * unit });
    l2.push({ id: `${g.id}>held`, from: g.id, to: "held", flows: false, color: "#475080", w: wh * unit });
  });
  const x0 = 120, x1 = 380, x2 = W - 150, nodeW = 12;
  const sy = (i: number, n: number) => 20 + ((H - 40) / n) * (i + 0.5);
  const srcH = gates.length * unit;
  const gH = (g: SCWPrivacyGate) => srcs.length * unit;
  const totalRel = l2.filter((l) => l.to === "adv").reduce((s, l) => s + l.w, 0), totalHeld = l2.filter((l) => l.to === "held").reduce((s, l) => s + l.w, 0);
  const tgt = { adv: { y: H * 0.3, h: Math.max(4, totalRel) }, held: { y: H * 0.72, h: Math.max(4, totalHeld) } };
  const srcOff: Record<string, number> = {}, gInOff: Record<string, number> = {}, gOutOff: Record<string, number> = {}, tOff: Record<string, number> = { adv: 0, held: 0 };
  const path = (xa: number, ya: number, xb: number, yb: number) => { const m = (xa + xb) / 2; return `M${xa},${ya} C${m},${ya} ${m},${yb} ${xb},${yb}`; };
  const hovGate = hov?.split(">")[1] ?? hov?.split(">")[0];
  return (
    <div className="scrollx">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 560, display: "block" }} role="img" aria-label={`Exposure flow: ${totalRel / unit} tier-to-SCW channels reach the advertiser as labels, ${totalHeld / unit} are withheld.`}>
        <defs>{[...l1, ...l2].map((l) => <linearGradient key={l.id} id={`g-${l.id.replace(/[^\w]/g, "")}`} x1="0" x2="1"><stop offset="0" stopColor={l.color} stopOpacity={0.75} /><stop offset="1" stopColor={l.to === "held" ? "#475080" : l.to === "adv" ? "#fbbf24" : MODE[gates.find((g) => g.id === l.to)?.gateType ?? "block"].color} stopOpacity={0.55} /></linearGradient>)}</defs>
        {l1.map((l) => {
          const si = srcs.findIndex((s) => s.id === l.from), gi = gates.findIndex((g) => g.id === l.to);
          const ya = sy(si, srcs.length) - srcH / 2 + (srcOff[l.from] = (srcOff[l.from] ?? 0) + l.w) - l.w / 2;
          const yb = sy(gi, gates.length) - gH(gates[gi]) / 2 + (gInOff[l.to] = (gInOff[l.to] ?? 0) + l.w) - l.w / 2;
          const on = !hov || hov === l.id || hovGate === l.to || hov === l.from;
          return <path key={l.id} d={path(x0 + nodeW, ya, x1, yb)} stroke={l.flows ? `url(#g-${l.id.replace(/[^\w]/g, "")})` : "#2a2f58"} strokeWidth={l.w} fill="none" opacity={on ? (l.flows ? 0.95 : 0.5) : 0.12} strokeDasharray={l.flows ? undefined : "2 3"} onMouseEnter={() => setHov(l.id)} onMouseLeave={() => setHov(null)}><title>{`${l.from} → ${gates[gi].name}: ${l.flows ? "reaches the advertiser as labels" : "withheld"}`}</title></path>;
        })}
        {l2.map((l) => {
          const gi = gates.findIndex((g) => g.id === l.from);
          const ya = sy(gi, gates.length) - gH(gates[gi]) / 2 + (gOutOff[l.from] = (gOutOff[l.from] ?? 0) + l.w) - l.w / 2;
          const t = tgt[l.to as "adv" | "held"];
          const yb = t.y - t.h / 2 + (tOff[l.to] = tOff[l.to] + l.w) - l.w / 2;
          const on = !hov || hovGate === l.from || hov === l.to;
          return <path key={l.id} d={path(x1 + nodeW, ya, x2, yb)} className={l.flows ? "flow" : undefined} stroke={`url(#g-${l.id.replace(/[^\w]/g, "")})`} strokeWidth={l.w} fill="none" opacity={on ? 0.9 : 0.12} strokeDasharray={l.flows ? "10 2" : undefined} />;
        })}
        {srcs.map((s, i) => (
          <g key={s.id} onMouseEnter={() => setHov(s.id)} onMouseLeave={() => setHov(null)}>
            <rect x={x0} y={sy(i, srcs.length) - srcH / 2} width={nodeW} height={srcH} rx={3} fill={s.color} />
            <text x={x0 - 8} y={sy(i, srcs.length) + 4} textAnchor="end" fill="#c7ceff" fontSize={12}>{s.label}{!AD_GRANTABLE.has(s.id as MemoryTier) ? " 🔒" : ""}</text>
          </g>
        ))}
        {gates.map((g, i) => (
          <g key={g.id} style={{ cursor: "pointer" }} onClick={() => onSelect(g.id)} onMouseEnter={() => setHov(g.id)} onMouseLeave={() => setHov(null)}>
            <rect x={x1} y={sy(i, gates.length) - gH(g) / 2 - 3} width={nodeW} height={gH(g) + 6} rx={3} fill={MODE[g.gateType].color} stroke={selected === g.id ? "#fff" : "none"} strokeWidth={2} />
            <text x={x1 + nodeW / 2} y={sy(i, gates.length) - gH(g) / 2 - 9} textAnchor="middle" fill="#fff" fontSize={12} fontWeight={600}>{g.name}</text>
          </g>
        ))}
        {(["adv", "held"] as const).map((k) => (
          <g key={k} onMouseEnter={() => setHov(k)} onMouseLeave={() => setHov(null)}>
            <rect x={x2} y={tgt[k].y - tgt[k].h / 2} width={nodeW} height={tgt[k].h} rx={3} fill={k === "adv" ? "#fbbf24" : "#475080"} />
            <text x={x2 + 20} y={tgt[k].y - 2} fill="#fff" fontSize={12} fontWeight={600}>{k === "adv" ? "Advertiser" : "Withheld"}</text>
            <text x={x2 + 20} y={tgt[k].y + 13} fill="#8e97c2" fontSize={11}>{k === "adv" ? `${totalRel / unit} channels · labels only` : `${totalHeld / unit} channels`}</text>
          </g>
        ))}
      </svg>
    </div>
  );
};

/** Replay matrix: synthetic prompts × SCWs, each cell a full evaluator run. */
const ReplayMatrix: React.FC<{ profile: UserAdProfile; onPick: (prompt: string, gateId: string) => void }> = ({ profile, onPick }) => {
  const res = useMemo(() => CORPUS.map((c) => profile.scwGates.map((g) => evaluateTurn(profile, g, c.text))), [profile]);
  const counts = useMemo(() => {
    const m: Record<Outcome, number> = { ad: 0, held: 0, labels: 0, sealed: 0, suppressed: 0, none: 0 };
    res.flat().forEach((r) => m[r.outcome]++);
    return m;
  }, [res]);
  const leaks = res.flat().filter((r) => r.released.some((x) => x.tier === "Persistent" || x.tier === "Procedural") || (r.cls.sensitive && r.released.length)).length;
  return (
    <div>
      <div className="row wrap" style={{ marginBottom: 10 }}>
        {(Object.keys(OUTCOME_META) as Outcome[]).map((o) => <span key={o} className="chip"><span className="dot" style={{ background: OUTCOME_META[o].color }} />{OUTCOME_META[o].label} <b className="num">{counts[o]}</b></span>)}
        <span className="chip" style={{ borderColor: leaks ? "#f87171" : "#34d39988", color: leaks ? "#f87171" : "#34d399" }}>Invariant breaches <b className="num">{leaks}</b></span>
      </div>
      <div className="scrollx">
        <table style={{ minWidth: 520 }}>
          <thead><tr><th>Synthetic prompt</th>{profile.scwGates.map((g) => <th key={g.id} style={{ textAlign: "center" }}>{g.name}</th>)}</tr></thead>
          <tbody>
            {CORPUS.map((c, i) => (
              <tr key={i}>
                <td><span className="small">{c.text}</span> <span className="dim small">· {c.tag}</span></td>
                {res[i].map((r, j) => (
                  <td key={j} style={{ width: 90 }}>
                    <button type="button" className="cell" aria-label={`${c.text} in ${profile.scwGates[j].name}: ${OUTCOME_META[r.outcome].label}`} title={`${OUTCOME_META[r.outcome].label}: ${r.reason}`} style={{ background: OUTCOME_META[r.outcome].color + (r.outcome === "none" ? "44" : "cc") }} onClick={() => onPick(c.text, profile.scwGates[j].id)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

/** Promotion gate: animated items moving through Maxey0's evidence-gated memory. */
const PromotionFlow: React.FC = () => {
  const reduced = useReducedMotion();
  const [t, setT] = useState(0);
  const [run, setRun] = useState(true);
  useEffect(() => {
    if (!run || reduced) return;
    let raf = 0, last = performance.now();
    const f = (n: number) => { setT((x) => x + (n - last) / 1000); last = n; raf = requestAnimationFrame(f); };
    raf = requestAnimationFrame(f);
    return () => cancelAnimationFrame(raf);
  }, [run, reduced]);
  const W = 760, H = 250;
  const X = { W: 70, E: 230, G: 400, S: 590, Q: 400 };
  const checks = ["relevance", "evidence", "consistency", "reuse", "policy"];
  const items = [
    { label: "“uses Rust”", pass: true, off: 0 },
    { label: "“likes trail running”", pass: true, off: 1.7 },
    { label: "“phone 555…”", pass: false, off: 3.4, why: "policy: identity" },
    { label: "“one-off gift idea”", pass: false, off: 5.1, why: "reuse: seen once" },
  ];
  const period = 6.8;
  return (
    <div>
      <div className="scrollx">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 560, display: "block" }} role="img" aria-label="Promotion gate: items move from Working to Episodic, then pass five checks to enter Semantic memory or go to quarantine for repair.">
          {[["W", "Working", TIER.Working.color], ["E", "Episodic", TIER.Episodic.color], ["S", "Semantic", TIER.Semantic.color]].map(([k, n, c]) => (
            <g key={k}><rect x={(X as any)[k] - 58} y={50} width={116} height={70} rx={14} fill={c + "18"} stroke={c} /><text x={(X as any)[k]} y={44} textAnchor="middle" fill={c} fontSize={12} fontWeight={700}>{n}</text></g>
          ))}
          <g><polygon points={`${X.G - 40},85 ${X.G},45 ${X.G + 40},85 ${X.G},125`} fill="#7c8cff22" stroke="#7c8cff" /><text x={X.G} y={89} textAnchor="middle" fill="#c7ceff" fontSize={11} fontWeight={700}>GATE</text>
            {checks.map((c, i) => <text key={c} x={X.G + 52} y={52 + i * 16} fill="#8e97c2" fontSize={10}>✓ {c}</text>)}</g>
          <rect x={X.Q - 70} y={175} width={140} height={54} rx={12} fill="#f8717118" stroke="#f87171" strokeDasharray="4 3" />
          <text x={X.Q} y={197} textAnchor="middle" fill="#f87171" fontSize={12} fontWeight={700}>Quarantine</text>
          <text x={X.Q} y={214} textAnchor="middle" fill="#8e97c2" fontSize={10}>repair or forget</text>
          <g opacity={0.8}><rect x={W - 110} y={150} width={100} height={36} rx={10} fill="#f8717112" stroke="#f87171" /><text x={W - 60} y={172} textAnchor="middle" fill="#f87171" fontSize={11}>🔒 Persistent</text>
            <rect x={W - 110} y={194} width={100} height={36} rx={10} fill="#a78bfa12" stroke="#a78bfa" /><text x={W - 60} y={216} textAnchor="middle" fill="#a78bfa" fontSize={11}>🔒 Procedural</text>
            <text x={W - 60} y={142} textAnchor="middle" fill="#5b638c" fontSize={10}>never ad-readable</text></g>
          <path d={`M${X.W + 58},85 L${X.E - 58},85 M${X.E + 58},85 L${X.G - 40},85 M${X.G + 40},85 L${X.S - 58},85 M${X.G},125 L${X.Q},175`} stroke="#3a4170" strokeWidth={2} strokeDasharray="4 4" />
          {items.map((it, i) => {
            const f = (((t + it.off) % period) + period) % period / period;
            let x = X.W, y = 85, op = 1;
            if (f < 0.25) x = X.W + (X.E - X.W) * (f / 0.25);
            else if (f < 0.5) x = X.E + (X.G - X.E) * ((f - 0.25) / 0.25);
            else if (it.pass) x = X.G + (X.S - X.G) * Math.min(1, (f - 0.5) / 0.3);
            else { x = X.G; y = 85 + (200 - 85) * Math.min(1, (f - 0.5) / 0.3); }
            if (f > 0.9) op = (1 - f) / 0.1;
            const col = f < 0.5 ? "#e8ebff" : it.pass ? TIER.Semantic.color : "#f87171";
            return <g key={i} opacity={op} transform={`translate(${x},${y + (i % 2 ? -12 : 12) * (f < 0.5 ? 1 : 0)})`}><circle r={5} fill={col} /><text y={-9} textAnchor="middle" fill={col} fontSize={10}>{it.label}{f > 0.55 && !it.pass ? ` · ${it.why}` : ""}</text></g>;
          })}
        </svg>
      </div>
      <div className="row between small muted"><span>Items are admitted to Semantic only when all five checks pass. Failures go to quarantine; nothing skips the gate.</span>
        {!reduced && <button type="button" className="btn sm ghost" onClick={() => setRun((r) => !r)}>{run ? <Pause size={13} /> : <Play size={13} />}{run ? "Pause" : "Play"}</button>}</div>
    </div>
  );
};

/** Tier × SCW grant matrix with locked sealed tiers. */
const GrantMatrix: React.FC<{ profile: UserAdProfile; dispatch: React.Dispatch<Action> }> = ({ profile, dispatch }) => (
  <div className="scrollx">
    <table style={{ minWidth: 480 }}>
      <thead><tr><th>Tier</th>{profile.scwGates.map((g) => <th key={g.id} style={{ textAlign: "center" }}>{g.name}</th>)}</tr></thead>
      <tbody>
        {TIERS.map((t) => (
          <tr key={t.id}>
            <td><span className="row"><span className="dot" style={{ background: t.color }} /><b>{t.id}</b>{!t.adGrantable && <Lock size={12} />}</span><div className="dim small">{t.chatgpt}</div></td>
            {profile.scwGates.map((g) => {
              const on = g.memoryTierAccess.includes(t.id);
              return (
                <td key={g.id} style={{ textAlign: "center", verticalAlign: "middle" }}>
                  {t.adGrantable
                    ? <Toggle on={on} label={`${t.id} readable in ${g.name}`} onChange={(v) => dispatch({ type: "edit", note: `${t.id} ${v ? "granted to" : "revoked from"} ${g.name}.`, fn: updGate(g.id, (x) => ({ ...x, memoryTierAccess: v ? [...x.memoryTierAccess, t.id] : x.memoryTierAccess.filter((y) => y !== t.id) })) })} />
                    : <span className="chip" style={{ color: t.color, borderColor: t.color + "66" }} title="INV-4">locked</span>}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// ============================================================================
// 7. PAGES
// ============================================================================

type PageId = "overview" | "map" | "studio" | "simulate" | "lens" | "memory" | "learn" | "apply";
interface PageProps { s: State; dispatch: React.Dispatch<Action>; go: (p: PageId) => void; simPrefill: (text: string, gateId: string) => void }

const Overview: React.FC<PageProps> = ({ s, dispatch, go, simPrefill }) => {
  const p = s.profile;
  const score = privacyScore(p);
  const replay = useMemo(() => CORPUS.flatMap((c) => p.scwGates.map((g) => evaluateTurn(p, g, c.text))), [p]);
  const ads = replay.filter((r) => r.outcome === "ad" || r.outcome === "held").length;
  const released = replay.reduce((n, r) => n + r.released.length, 0);
  const withheld = replay.reduce((n, r) => n + r.withheld.length, 0);
  return (
    <div className="grid">
      <div className="grid g4">
        <div className="stat row" style={{ gridRow: "span 2", justifyContent: "center", flexDirection: "column" }}><ScoreDial score={score} /><div className="small muted" style={{ textAlign: "center" }}>Privacy score = 100 × (1 − mean SCW exposure)</div></div>
        <div className="stat"><div className="k">SCWs</div><div className="big num">{p.scwGates.length}</div><div className="small muted">{p.scwGates.filter((g) => g.gateType === "block").length} sealed</div></div>
        <div className="stat"><div className="k">Ads in replay</div><div className="big num">{ads}<span className="muted" style={{ fontSize: 14 }}> / {replay.length}</span></div><div className="small muted">{CORPUS.length} prompts × {p.scwGates.length} SCWs</div></div>
        <div className="stat"><div className="k">Labels released</div><div className="big num" style={{ color: "#fbbf24" }}>{released}</div><div className="small muted">never text, never identity</div></div>
        <div className="stat"><div className="k">Withheld</div><div className="big num" style={{ color: "#34d399" }}>{withheld}</div><div className="small muted">signals blocked by rule</div></div>
        <div className="stat span2"><div className="k">Preset</div>
          <div style={{ marginTop: 6 }}><Seg label="Privacy preset" value={p.privacyLevel} onChange={(v) => v !== "custom" && dispatch({ type: "replace", profile: { ...PRESETS[v].build(), interests: p.interests, blockedBrands: p.blockedBrands }, note: `Applied the ${PRESETS[v].label} preset.` })}
            options={[{ id: "strict", label: "Strict", color: "#34d399" }, { id: "balanced", label: "Balanced", color: "#60a5fa" }, { id: "minimal", label: "Open", color: "#f87171" }, { id: "custom", label: "Custom", color: "#c7ceff" }]} /></div>
          <div className="small muted" style={{ marginTop: 6 }}>{p.privacyLevel === "custom" ? "You have edited the preset. Every change is undoable." : PRESETS[p.privacyLevel].blurb}</div>
        </div>
      </div>
      <Panel kicker="Where your data can go" title="Exposure flow" sub="Every memory tier → every SCW → advertiser or withheld. Solid bands reach the advertiser as topic labels; dashed bands stop. Click an SCW to edit it." right={<button className="btn sm" onClick={() => go("map")}><MapIcon size={14} />Latent map</button>}>
        <ExposureFlow profile={p} selected={s.selected} onSelect={(id) => { dispatch({ type: "select", id }); go("studio"); }} />
      </Panel>
      <Panel kicker="Stress test" title="Replay: 18 prompts through every SCW" sub="Each cell is a full evaluator run. Click one to open it in the simulator." right={<button className="btn sm" onClick={() => go("simulate")}><Zap size={14} />Simulator</button>}>
        <ReplayMatrix profile={p} onPick={(text, g) => simPrefill(text, g)} />
      </Panel>
    </div>
  );
};

const GateEditor: React.FC<{ g: SCWPrivacyGate; p: UserAdProfile; dispatch: React.Dispatch<Action>; compact?: boolean }> = ({ g, p, dispatch, compact }) => {
  const up = (note: string, fn: (g: SCWPrivacyGate) => SCWPrivacyGate) => dispatch({ type: "edit", note, fn: updGate(g.id, fn) });
  const exp = gateExposure(p, g);
  return (
    <div>
      <div className="field"><label className="lbl" htmlFor={`n-${g.id}`}>Name</label>
        <input id={`n-${g.id}`} type="text" value={g.name} onChange={(e) => { const v = e.target.value.slice(0, 40); dispatch({ type: "edit", fn: updGate(g.id, (x) => ({ ...x, name: v })) }); }} /></div>
      <div className="field"><span className="lbl">Mode</span>
        <Seg label={`${g.name} mode`} value={g.gateType} onChange={(v) => up(`${g.name} is now ${MODE[v].label}.`, (x) => ({ ...x, gateType: v }))} options={MODES.map((m) => ({ id: m.id, label: m.label, color: m.color }))} />
        <span className="small muted">{MODE[g.gateType].blurb}</span></div>
      <div className="field"><span className="lbl">Memory tiers this SCW may read</span>
        <div className="chips">{TIERS.map((t) => {
          const on = g.memoryTierAccess.includes(t.id);
          return <button key={t.id} type="button" className="chip" disabled={!t.adGrantable} aria-pressed={on} title={t.adGrantable ? t.chatgpt : "INV-4: never grantable"}
            style={{ cursor: t.adGrantable ? "pointer" : "not-allowed", borderColor: on ? t.color : undefined, background: on ? t.color + "26" : undefined, color: on ? t.color : t.adGrantable ? undefined : "#5b638c" }}
            onClick={() => up(`${t.id} ${on ? "revoked from" : "granted to"} ${g.name}.`, (x) => ({ ...x, memoryTierAccess: on ? x.memoryTierAccess.filter((y) => y !== t.id) : [...x.memoryTierAccess, t.id] }))}>
            {!t.adGrantable && <Lock size={11} />}{t.id}</button>;
        })}</div></div>
      <div className="field"><span className="lbl">Ad categories</span>
        <div className="chips">{CATEGORIES.map((c) => {
          const on = g.allowedCategories.includes(c.id), global = p.allowedCategories.includes(c.id);
          return <button key={c.id} type="button" className="chip" aria-pressed={on} title={global ? "" : "Off globally in Apply → Categories"}
            style={{ cursor: "pointer", borderColor: on ? c.color : undefined, background: on ? c.color + "22" : undefined, color: on ? c.color : undefined, opacity: global ? 1 : 0.5 }}
            onClick={() => up(`${c.label} ${on ? "removed from" : "added to"} ${g.name}.`, (x) => ({ ...x, allowedCategories: on ? x.allowedCategories.filter((y) => y !== c.id) : [...x.allowedCategories, c.id] }))}>{c.label}</button>;
        })}</div></div>
      <div className="row between" style={{ marginBottom: 8 }}><span className="small">Share this chat's topics (Working, Episodic)</span><Toggle label={`Share conversation context in ${g.name}`} on={g.dataSharing.conversationContext} onChange={(v) => up(`Conversation sharing ${v ? "on" : "off"} in ${g.name}.`, (x) => ({ ...x, dataSharing: { ...x.dataSharing, conversationContext: v } }))} /></div>
      <div className="row between" style={{ marginBottom: 8 }}><span className="small">Use my interests (Semantic)</span><Toggle label={`Use preferences in ${g.name}`} on={g.dataSharing.userPreferences} onChange={(v) => up(`Interests ${v ? "usable" : "not usable"} in ${g.name}.`, (x) => ({ ...x, dataSharing: { ...x.dataSharing, userPreferences: v } }))} /></div>
      <div className="row between" style={{ marginBottom: 12 }}><span className="small dim">Behavioral & demographic data</span><span className="chip" style={{ color: "#c084fc", borderColor: "#c084fc66" }}><Lock size={11} />INV-2 · always off</span></div>
      {!compact && <>
        <div className="field"><label className="lbl">Max ads per session: <b className="num">{g.maxAdsPerSession}</b></label>
          <input type="range" min={0} max={10} value={g.maxAdsPerSession} aria-label={`Max ads per session in ${g.name}`} onChange={(e) => { const v = +e.target.value; dispatch({ type: "edit", fn: updGate(g.id, (x) => ({ ...x, maxAdsPerSession: v })) }); }} /></div>
        <div className="field"><label className="lbl">Minimum relevance: <b className="num">{g.requireRelevanceScore}%</b></label>
          <input type="range" min={50} max={100} value={g.requireRelevanceScore} aria-label={`Minimum relevance in ${g.name}`} onChange={(e) => { const v = +e.target.value; dispatch({ type: "edit", fn: updGate(g.id, (x) => ({ ...x, requireRelevanceScore: v })) }); }} /></div>
        <div className="field"><span className="lbl">Blocked topics (suppress ads when mentioned)</span>
          <TagInput label={`Block a topic in ${g.name}`} placeholder="e.g. salary" onAdd={(v) => up(`Blocked “${v}” in ${g.name}.`, (x) => ({ ...x, blockedTopics: Array.from(new Set([...x.blockedTopics, v.toLowerCase()])) }))} />
          <div className="chips">{g.blockedTopics.map((t) => <Chip key={t} onRemove={() => up(`Unblocked “${t}”.`, (x) => ({ ...x, blockedTopics: x.blockedTopics.filter((y) => y !== t) }))}>{t}</Chip>)}</div></div>
      </>}
      <div className="small">Exposure <b className="num" style={{ color: exp > 0.5 ? "#f87171" : exp > 0.2 ? "#fbbf24" : "#34d399" }}>{Math.round(exp * 100)}%</b>
        <span className="dim"> = mode weight {MODE[g.gateType].weight} × granted, shared tier weights (W 0.2 · E 0.3 · S 0.5)</span></div>
    </div>
  );
};

const LatentPage: React.FC<PageProps> = ({ s, dispatch }) => {
  const [paused, setPaused] = useState(false);
  const [counts, setCounts] = useState({ admitted: 0, blocked: 0 });
  const onCounts = useCallback((c: { admitted: number; blocked: number }) => setCounts(c), []);
  const g = s.profile.scwGates.find((x) => x.id === s.selected) ?? null;
  const rate = counts.admitted + counts.blocked ? Math.round((100 * counts.blocked) / (counts.admitted + counts.blocked)) : 0;
  return (
    <div className="grid g-map">
      <div className="grid">
        <div className="row wrap">
          <span className="pill"><span className="dot" style={{ background: "#34d399", animation: "mxpulse 1.4s infinite" }} />Probes admitted <b className="num">{counts.admitted}</b></span>
          <span className="pill"><span className="dot" style={{ background: "#f87171" }} />Probes blocked <b className="num">{counts.blocked}</b> · {rate}%</span>
          <span className="grow" style={{ flex: 1 }} />
          <button className="btn sm" onClick={() => setPaused((x) => !x)}>{paused ? <Play size={13} /> : <Pause size={13} />}{paused ? "Resume" : "Pause"}</button>
        </div>
        <LatentField profile={s.profile} selected={s.selected} onSelect={(id) => dispatch({ type: "select", id })} paused={paused} onCounts={onCounts} />
        <p className="small muted" style={{ margin: 0 }}>A probe is admitted when the SCW is not sealed, reads the Working tier with context sharing on, allows the ad's category, and the brand is not blocked. Everything else deflects at the membrane. Change a control and the field responds immediately.</p>
      </div>
      <div className="grid" style={{ alignContent: "start" }}>
        <Panel kicker="Selected SCW" title={g ? g.name : "Click a world on the map"} right={g && <button className="btn sm ghost" onClick={() => dispatch({ type: "select", id: null })}>Close</button>}>
          {g ? <GateEditor g={g} p={s.profile} dispatch={dispatch} compact /> : <p className="small muted">Each rounded world orbiting the core is a logical SCW. Its coloured channels show which memory tiers it may read. Click one to edit it here, live.</p>}
        </Panel>
        <Panel kicker="Five typed tiers" title="Memory in this map" sub="Not a duration stack.">
          {TIERS.map((t) => {
            const n = s.profile.scwGates.filter((g) => g.memoryTierAccess.includes(t.id)).length;
            return <div key={t.id} className="step"><span className="ic" style={{ background: t.color + "22", color: t.color }}>{t.short}</span><div><b>{t.id}</b> <span className="dim small">· {t.adGrantable ? `granted to ${n} of ${s.profile.scwGates.length}` : "locked: cannot be granted"}</span><div className="small muted">{t.chatgpt}</div></div></div>;
          })}
        </Panel>
      </div>
    </div>
  );
};

const StudioPage: React.FC<PageProps> = ({ s, dispatch, simPrefill }) => {
  const p = s.profile;
  const add = () => {
    const g0 = gate(`SCW ${p.scwGates.length + 1}`, "contextual", ["technology"], ["Working"], true, false, 1, 85);
    dispatch({ type: "edit", note: `Created ${g0.name}.`, fn: (x) => custom({ ...x, scwGates: [...x.scwGates, g0] }) });
    dispatch({ type: "select", id: g0.id });
  };
  return (
    <div className="grid">
      <Panel kicker="Control plane" title="Tier grants" sub="Which memory each SCW may read for ads. Persistent and Procedural are locked by INV-4.">
        <GrantMatrix profile={p} dispatch={dispatch} />
      </Panel>
      <div className="row between"><h2 style={{ margin: 0, fontSize: 15 }}>Your context worlds</h2>
        <button className="btn pri" onClick={add} disabled={p.scwGates.length >= 12}><Plus size={14} />New SCW</button></div>
      <div className="grid g3">
        {p.scwGates.map((g) => {
          const preview = evaluateTurn(p, g, "Help me learn Python for a data science course and plan a trail running trip");
          return (
            <Panel key={g.id} kicker={MODE[g.gateType].label} title={g.name} className={s.selected === g.id ? "sel" : ""}
              right={<button className="btn sm ghost danger" aria-label={`Delete ${g.name}`} disabled={p.scwGates.length <= 1} onClick={() => dispatch({ type: "edit", note: `Deleted ${g.name}. Undo is available.`, fn: (x) => custom({ ...x, scwGates: x.scwGates.filter((y) => y.id !== g.id) }) })}><Trash2 size={13} /></button>}>
              <div style={{ height: 3, borderRadius: 3, background: MODE[g.gateType].color, marginTop: -6, marginBottom: 12, boxShadow: s.selected === g.id ? `0 0 16px ${MODE[g.gateType].color}` : undefined }} />
              <GateEditor g={g} p={p} dispatch={dispatch} />
              <div style={{ marginTop: 12, padding: 10, borderRadius: 10, border: "1px dashed rgba(148,163,255,.25)" }}>
                <div className="small muted">Live preview · “Help me learn Python for a data science course…”</div>
                <div className="row wrap" style={{ marginTop: 6 }}><span className="chip" style={{ color: OUTCOME_META[preview.outcome].color, borderColor: OUTCOME_META[preview.outcome].color + "88" }}>{OUTCOME_META[preview.outcome].label}</span>
                  {preview.released.map((r) => <Chip key={r.label} color={CAT_COLOR[r.category]}>{r.label}</Chip>)}</div>
                <button className="btn sm ghost" style={{ marginTop: 6 }} onClick={() => simPrefill("Help me learn Python for a data science course and plan a trail running trip", g.id)}>Trace in simulator <ArrowRight size={12} /></button>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
};

const QUICK = ["Explain Bayesian statistics with a worked example", "Help me debug this Rust API server", "Best trail running shoes for mud?", "My doctor changed my medication", "My name is Sam, email sam@example.com", "How do we pay down technical debt?"];

const TraceView: React.FC<{ r: TurnResult }> = ({ r }) => (
  <div>
    {r.steps.map((st, i) => (
      <div key={i} className="step"><span className="ic" style={{ background: st.pass ? "#34d39922" : "#f8717122", color: st.pass ? "#34d399" : "#f87171" }}>{st.pass ? "✓" : "✕"}</span>
        <div><b className="small">{st.label}</b> <span className="dim mono" style={{ fontSize: 10 }}>{st.id}</span><div className="small muted">{st.detail}</div></div></div>
    ))}
  </div>
);

const SimulatePage: React.FC<PageProps & { draft: { text: string; gateId: string | null }; setDraft: (d: { text: string; gateId: string | null }) => void }> = ({ s, dispatch, draft, setDraft }) => {
  const p = s.profile;
  const gid = draft.gateId && p.scwGates.some((g) => g.id === draft.gateId) ? draft.gateId : p.scwGates[0]?.id;
  const g = p.scwGates.find((x) => x.id === gid)!;
  const turns = s.sessions[gid] ?? [];
  const last = turns[turns.length - 1];
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "nearest" }); }, [turns.length]);
  const send = (text: string) => {
    const t = text.trim(); if (!t || !g) return;
    const adsShown = turns.filter((x) => x.result.outcome === "ad" || (x.result.outcome === "held" && x.approved)).length;
    const result = evaluateTurn(p, g, t, turns.map((x) => x.text), adsShown);
    dispatch({ type: "turn", gateId: g.id, turn: { id: newId("turn"), text: t, result } });
    setDraft({ text: "", gateId: g.id });
  };
  const compare = useMemo(() => (last ? p.scwGates.map((x) => ({ g: x, r: evaluateTurn(p, x, last.text) })) : []), [p, last]);
  if (!g) return <Panel title="No SCWs">Create one in the Studio.</Panel>;
  return (
    <div className="grid g2">
      <Panel kicker="Simulated ChatGPT session" title="Type as you would in ChatGPT" sub="Evaluated on this device by the same rules the map uses. Nothing is sent anywhere."
        right={<button className="btn sm ghost" onClick={() => dispatch({ type: "clearSession", gateId: g.id })}><RotateCcw size={13} />Reset</button>}>
        <div style={{ marginBottom: 10 }}><Seg label="Active SCW" value={g.id} onChange={(v) => setDraft({ ...draft, gateId: v })} options={p.scwGates.map((x) => ({ id: x.id, label: x.name, color: MODE[x.gateType].color }))} /></div>
        <div style={{ maxHeight: 420, overflowY: "auto", display: "grid", gap: 10, padding: "4px 2px" }}>
          {!turns.length && <p className="small muted">No turns yet in {g.name}. Earlier turns become the Episodic tier for later ones.</p>}
          {turns.map((t) => {
            const r = t.result, m = OUTCOME_META[r.outcome];
            return (
              <div key={t.id} style={{ display: "grid", gap: 6 }}>
                <div className="bubble small">{t.text}</div>
                <div className="row wrap small"><span className="chip" style={{ color: m.color, borderColor: m.color + "88" }}>{m.label}</span><span className="muted">{r.reason}</span></div>
                {r.ad && (r.outcome === "ad" || t.approved) && <div className="adcard"><div className="row between"><span className="kick" style={{ color: "#fbbf24" }}>Sponsored · contextual</span><span className="dim small">{r.ad.relevance}% relevant</span></div>
                  <b>{r.ad.cand.headline}</b><div className="small muted">{r.ad.cand.advertiser} (fictional) · matched on {r.ad.matched.join(", ")}</div></div>}
                {r.outcome === "held" && t.approved === undefined && <div className="row"><button className="btn sm" onClick={() => dispatch({ type: "approve", gateId: g.id, turnId: t.id, ok: true })}><Check size={13} />Show ad</button><button className="btn sm ghost" onClick={() => dispatch({ type: "approve", gateId: g.id, turnId: t.id, ok: false })}>Dismiss</button></div>}
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <input type="text" aria-label="Message" placeholder={`Message in ${g.name}…`} value={draft.text} onChange={(e) => setDraft({ ...draft, gateId: g.id, text: e.target.value })} onKeyDown={(e) => e.key === "Enter" && send(draft.text)} />
          <button className="btn pri" onClick={() => send(draft.text)} aria-label="Send"><Send size={14} /></button>
        </div>
        <div className="chips" style={{ marginTop: 8 }}>{QUICK.map((q) => <button key={q} type="button" className="chip" style={{ cursor: "pointer" }} onClick={() => send(q)}>{q}</button>)}</div>
      </Panel>
      <div className="grid" style={{ alignContent: "start" }}>
        <Panel kicker="Pipeline trace" title={last ? "Last turn, rule by rule" : "Send a message to see its trace"}>
          {last && <>
            <TraceView r={last.result} />
            <div className="field" style={{ marginTop: 8 }}><span className="lbl">Released to the ad system (labels only)</span>
              <div className="chips">{last.result.released.length ? last.result.released.map((r) => <Chip key={r.label + r.tier} color={CAT_COLOR[r.category]} title={`${r.tier} tier`}>{r.label} · {r.tier[0]}</Chip>) : <span className="small dim">nothing</span>}</div></div>
            <div className="field"><span className="lbl">Withheld</span>
              <div className="chips">{last.result.withheld.map((w, i) => <span key={i} className="chip small">{w.label} <span className="dim">· {w.tier}</span> <RuleChip rule={w.rule} /></span>)}</div></div>
          </>}
        </Panel>
        {last && <Panel kicker="Same message, every SCW" title="Isolation at a glance">
          <table><tbody>{compare.map(({ g: x, r }) => <tr key={x.id}><td><b>{x.name}</b></td><td><span className="chip" style={{ color: OUTCOME_META[r.outcome].color, borderColor: OUTCOME_META[r.outcome].color + "88" }}>{OUTCOME_META[r.outcome].label}</span></td><td className="small muted">{r.released.map((q) => q.label).join(", ") || "—"}</td></tr>)}</tbody></table>
        </Panel>}
      </div>
    </div>
  );
};

const LensPage: React.FC<PageProps> = ({ s }) => {
  const p = s.profile;
  const [idx, setIdx] = useState(0);
  const [gid, setGid] = useState(p.scwGates[p.scwGates.length - 1]?.id ?? "");
  const g = p.scwGates.find((x) => x.id === gid) ?? p.scwGates[0];
  const prompt = CORPUS[idx].text;
  const r = evaluateTurn(p, g, prompt);
  const bid = {
    request_id: "<random, per impression>", slot: "chat_inline", scw_mode: MODE[g.gateType].label.toLowerCase(),
    categories: Array.from(new Set(r.released.map((x) => x.category))), topic_labels: r.released.map((x) => x.label),
    relevance_floor: Math.max(g.requireRelevanceScore, p.sessionLimits.minRelevanceThreshold),
    user_id: null, message_text: null, history: null, demographics: null, location: null,
  };
  const words = prompt.split(/(\s+)/);
  const releasedSet = new Set(r.released.map((x) => x.label));
  return (
    <div className="grid">
      <div className="row wrap">
        <Seg label="SCW" value={g.id} onChange={setGid} options={p.scwGates.map((x) => ({ id: x.id, label: x.name, color: MODE[x.gateType].color }))} />
        <select aria-label="Sample prompt" value={idx} onChange={(e) => setIdx(+e.target.value)} style={{ background: "#0b0e1c", color: "#e8ebff", border: "1px solid rgba(148,163,255,.28)", borderRadius: 10, padding: "7px 10px", flex: "1 1 240px", minWidth: 0, width: "100%" }}>
          {CORPUS.map((c, i) => <option key={i} value={i}>{c.text}</option>)}
        </select>
      </div>
      <div className="grid g2">
        <Panel kicker="Inside your SCW" title="What ChatGPT sees" sub="Your full message, with the words the classifier used highlighted.">
          <p style={{ fontSize: 16, lineHeight: 1.8 }}>{words.map((w, i) => { const k = w.toLowerCase().replace(/[^a-z0-9]/g, ""); return releasedSet.has(k) ? <mark key={i} style={{ background: "#fbbf2433", color: "#fbbf24", borderRadius: 4, padding: "0 3px" }}>{w}</mark> : <span key={i}>{w}</span>; })}</p>
          <div className="row wrap small"><span className="chip" style={{ color: OUTCOME_META[r.outcome].color }}>{OUTCOME_META[r.outcome].label}</span><span className="muted">{r.reason}</span></div>
          <TraceView r={r} />
        </Panel>
        <Panel kicker="Across the boundary" title="What the ad system receives" sub="The complete payload an advertiser could bid on under this SCW. Nulls are fields that never cross.">
          <pre className="mono small" style={{ margin: 0, whiteSpace: "pre-wrap", padding: 12, borderRadius: 12, background: "#03040c", border: "1px solid rgba(148,163,255,.14)" }}>
            {JSON.stringify(bid, null, 2).split("\n").map((line, i) => <div key={i} style={{ color: /null/.test(line) ? "#5b638c" : /topic_labels|categories/.test(line) ? "#fbbf24" : "#c7ceff" }}>{line}</div>)}
          </pre>
          <div className="small muted" style={{ marginTop: 8 }}>Redacted from view: <span className="redact">sam@example.com</span> <span className="redact">your chat history</span> <span className="redact">account</span></div>
          <p className="small dim">This is the payload this app's evaluator would release. It is not ChatGPT's real ad request format, which is not public.</p>
        </Panel>
      </div>
    </div>
  );
};

const MemoryPage: React.FC<PageProps> = ({ s, dispatch }) => (
  <div className="grid">
    <Panel kicker="Maxey0 memory" title="Five typed tiers, one promotion gate" sub="Tiers are kinds of memory, not durations. Items move between them only through the evidence-gated gate.">
      <PromotionFlow />
    </Panel>
    <div className="grid g3">
      {TIERS.map((t) => (
        <Panel key={t.id} kicker={t.adGrantable ? "Grantable" : "Locked · INV-4"} title={<span className="row"><span className="dot" style={{ background: t.color }} />{t.id}</span>}>
          <div className="small"><b>Holds</b> <span className="muted">{t.holds}</span></div>
          <div className="small"><b>Lifecycle</b> <span className="muted">{t.lifecycle}</span></div>
          <div className="small"><b>In ChatGPT</b> <span className="muted">{t.chatgpt}</span></div>
          <div className="small" style={{ marginTop: 6 }}>{t.adGrantable ? <>Exposure weight <b>{t.weight}</b> · granted in <b>{s.profile.scwGates.filter((g) => g.memoryTierAccess.includes(t.id)).length}</b> SCWs</> : <span style={{ color: t.color }}>Never readable for ads, in any SCW.</span>}</div>
        </Panel>
      ))}
      <Panel kicker="Semantic tier" title="Your stated interests" sub="Readable only where an SCW grants Semantic and personalization is on.">
        <TagInput label="Add interest" placeholder="e.g. rust, trail running" onAdd={(v) => interestOk(v) ? dispatch({ type: "edit", note: `Added interest “${v}”.`, fn: (x) => custom({ ...x, interests: Array.from(new Set([...x.interests, v.trim()])).slice(0, 50) }) }) : dispatch({ type: "toast", msg: "An interest can be at most 40 characters and four words." })} />
        <div className="chips" style={{ marginTop: 8 }}>{s.profile.interests.map((i) => { const c = classifyText(i); return <Chip key={i} color={c.sensitive ? "#c084fc" : c.categories[0] ? CAT_COLOR[c.categories[0]] : "#8e97c2"} title={c.sensitive ? "Sensitive: never released" : c.categories[0] ?? "Unclassified: never released"} onRemove={() => dispatch({ type: "edit", note: `Removed “${i}”.`, fn: (x) => custom({ ...x, interests: x.interests.filter((y) => y !== i) }) })}>{i}</Chip>; })}</div>
        {!s.profile.interests.length && <p className="small dim">No interests yet.</p>}
      </Panel>
    </div>
  </div>
);

const LESSONS: { title: string; body: string; page: PageId; cta: string }[] = [
  { title: "A context world is a boundary, not a chat.", body: "A logical SCW is a named boundary around a kind of conversation: Work, Learning, Everyday. It declares what memory it may read, what may leave it, and under which rules. Two chats in different SCWs cannot see each other's context.", page: "map", cta: "See the boundaries" },
  { title: "Memory is typed.", body: "Working is what you are typing now. Episodic is this conversation so far. Semantic is what has been learned about you. Persistent is your account; Procedural is how the assistant is told to behave. An SCW is granted tiers by kind, and two kinds are never grantable.", page: "memory", cta: "Explore the tiers" },
  { title: "Invariants beat settings.", body: "Some rules hold in every SCW no matter what you toggle: identity never crosses, sensitive topics suppress ads, the sealed core stays sealed. Settings choose between safe options; invariants remove unsafe ones.", page: "lens", cta: "See what crosses" },
  { title: "Every decision has a trace.", body: "When an ad is shown or withheld, you should be able to see which rule decided it. The simulator shows each step, the labels released and the labels withheld, with the rule that withheld them.", page: "simulate", cta: "Trace a message" },
  { title: "Advisory until a platform enforces it.", body: "This app enforces your SCWs in its own evaluator. ChatGPT enforces only its own settings. The profile you export is a clear, portable statement of your boundary that ChatGPT may follow and that any platform could adopt.", page: "apply", cta: "Apply to ChatGPT" },
];

const LearnPage: React.FC<PageProps> = ({ go }) => {
  const [open, setOpen] = useState(0);
  return (
    <div className="grid g2">
      <Panel kicker="Maxey0 · logical SCWs" title="Structured Context Worlds in five ideas" sub="Click an idea to open it; each links to the part of the app that shows it working.">
        <div style={{ display: "grid", gap: 8 }}>
          {LESSONS.map((l, i) => (
            <button key={i} type="button" className="lesson" aria-expanded={open === i} onClick={() => setOpen(i)}>
              <span className="n">{i + 1}</span>
              <span><b>{l.title}</b>{open === i && <><span className="small muted" style={{ display: "block", marginTop: 6 }}>{l.body}</span>
                <span className="btn sm" style={{ marginTop: 10 }} role="link" tabIndex={0} onClick={(e) => { e.stopPropagation(); go(l.page); }}>{l.cta} <ArrowRight size={12} /></span></>}</span>
            </button>
          ))}
        </div>
      </Panel>
      <div className="grid" style={{ alignContent: "start" }}>
        <Panel kicker="The five invariants" title="Rules no setting can override">
          {INVARIANTS.map((v) => <div key={v.id} className="step"><span className="ic" style={{ background: "#c084fc22", color: "#c084fc" }}><Shield size={12} /></span><div><b className="mono small">{v.id}</b><div className="small muted">{v.text}</div></div></div>)}
        </Panel>
        <Panel kicker="Honest limits" title="What this app is and is not">
          <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
            <li>The classifier is a keyword list: inspectable, but it misses paraphrase.</li>
            <li>All advertisers and the ad payload format are fictional illustrations.</li>
            <li>Nothing you type leaves this page; there is no server and no storage.</li>
            <li>ChatGPT is not bound by the exported profile.</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
};

const ApplyPage: React.FC<PageProps> = ({ s, dispatch }) => {
  const p = s.profile;
  const json = useMemo(() => exportProfile(p), [p]);
  const instr = useMemo(() => chatgptInstruction(p), [p]);
  const [copied, setCopied] = useState<string | null>(null);
  const [imp, setImp] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const copy = async (key: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 1600); }
    catch { setCopied(`${key}-fail`); }
  };
  const download = () => {
    try {
      const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = `maxey0-scw-privacy-profile-${today()}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setMsg({ ok: false, text: "Download is blocked here. Use Copy instead." }); }
  };
  const doImport = () => {
    const r = importProfile(imp);
    if (r.ok) { dispatch({ type: "replace", profile: r.profile, note: r.note }); setMsg({ ok: true, text: `${r.note} Profile imported successfully.` }); setImp(""); }
    else setMsg({ ok: false, text: r.error });
  };
  return (
    <div className="grid g2">
      <Panel kicker="Global controls" title="Categories, brands and limits" className="span2">
        <div className="grid g3">
          <div>
            <span className="lbl">Ad categories allowed anywhere</span>
            <div className="chips" style={{ marginTop: 6 }}>{CATEGORIES.map((c) => { const on = p.allowedCategories.includes(c.id); return <button key={c.id} type="button" className="chip" aria-pressed={on} style={{ cursor: "pointer", borderColor: on ? c.color : undefined, background: on ? c.color + "22" : undefined, color: on ? c.color : undefined }} onClick={() => dispatch({ type: "edit", note: `${c.label} ${on ? "blocked" : "allowed"} globally.`, fn: (x) => custom({ ...x, allowedCategories: on ? x.allowedCategories.filter((y) => y !== c.id) : [...x.allowedCategories.filter((y) => y !== "none"), c.id] }) })}>{c.label}</button>; })}</div>
            <div style={{ marginTop: 12 }}><span className="lbl">Blocked brands</span>
              <TagInput label="Block a brand" placeholder="e.g. Crowd Pulse" onAdd={(v) => dispatch({ type: "edit", note: `Blocked brand “${v}”.`, fn: (x) => custom({ ...x, blockedBrands: Array.from(new Set([...x.blockedBrands, v])) }) })} />
              <div className="chips" style={{ marginTop: 6 }}>{p.blockedBrands.map((b) => <Chip key={b} onRemove={() => dispatch({ type: "edit", fn: (x) => custom({ ...x, blockedBrands: x.blockedBrands.filter((y) => y !== b) }) })}>{b}</Chip>)}</div></div>
          </div>
          <div>
            {([["shareConversationTopics", "Share current-message topics", "Working tier, in SCWs that grant it"], ["shareInteractionPatterns", "Share this-session topics", "Episodic tier, in SCWs that grant it"], ["allowPersonalization", "Use my interests", "Semantic tier, in SCWs that grant it"], ["shareSearchHistory", "Allow search history", "Advisory only: written into the ChatGPT instruction"]] as const).map(([k, l, d]) => (
              <div key={k} className="row between" style={{ marginBottom: 10 }}><div><div className="small">{l}</div><div className="dim" style={{ fontSize: 11 }}>{d}</div></div>
                <Toggle label={l} on={p.dataControls[k]} onChange={(v) => dispatch({ type: "edit", note: `${l}: ${v ? "on" : "off"}.`, fn: (x) => custom({ ...x, dataControls: { ...x.dataControls, [k]: v } }) })} /></div>
            ))}
          </div>
          <div>
            {([["maxAdsPerHour", "Max ads per hour", 0, 20], ["maxAdsPerDay", "Max ads per day", 0, 100], ["minRelevanceThreshold", "Minimum relevance %", 50, 100]] as const).map(([k, l, lo, hi]) => (
              <div key={k} className="field"><label className="lbl">{l}: <b className="num">{p.sessionLimits[k]}</b></label>
                <input type="range" min={lo} max={hi} value={p.sessionLimits[k]} aria-label={l} onChange={(e) => { const v = +e.target.value; dispatch({ type: "edit", fn: (x) => custom({ ...x, sessionLimits: { ...x.sessionLimits, [k]: v } }) }); }} /></div>
            ))}
            <div className="dim" style={{ fontSize: 11 }}>The simulator enforces per-session and per-hour caps; the daily cap is written into the ChatGPT instruction.</div>
          </div>
        </div>
      </Panel>
      <Panel kicker="Step 1 · enforced by ChatGPT" title="Check ChatGPT's own settings" sub="Only these are enforced by ChatGPT. Menu names change; look under Settings for personalization, memory, data controls and ads.">
        {["Review or turn off memory and chat-history reference if you do not want the Semantic tier used at all.", "Review ad personalization controls, if your account shows them, and clear ad-interest data you do not want used.", "Use a temporary chat for anything you would put in a sealed SCW.", "Export your data periodically to see what has been stored about you."].map((t, i) => <div key={i} className="step"><span className="ic" style={{ background: "#34d39922", color: "#34d399" }}>{i + 1}</span><div className="small">{t}</div></div>)}
      </Panel>
      <Panel kicker="Step 2 · advisory" title="Paste this instruction into ChatGPT" sub="For custom instructions or the start of a chat. ChatGPT may follow it; it is not bound by it."
        right={<button className="btn sm" onClick={() => copy("instr", instr)}>{copied === "instr" ? <Check size={13} /> : <Copy size={13} />}{copied === "instr" ? "Copied" : copied === "instr-fail" ? "Select & copy" : "Copy"}</button>}>
        <textarea readOnly value={instr} rows={9} aria-label="ChatGPT instruction" onFocus={(e) => e.currentTarget.select()} />
      </Panel>
      <Panel kicker="Step 3 · portable" title="Export profile" sub={`Version ${EXPORT_VERSION} · includes the memory model, the invariants and the instruction.`}
        right={<><button className="btn sm" onClick={() => copy("json", json)}>{copied === "json" ? <Check size={13} /> : <Copy size={13} />}{copied === "json" ? "Copied" : "Copy"}</button><button className="btn sm ghost" onClick={download}><Download size={13} />Download</button></>}>
        <textarea readOnly value={json} rows={12} aria-label="Exported profile JSON" onFocus={(e) => e.currentTarget.select()} />
      </Panel>
      <Panel kicker="Restore" title="Import profile" sub="Only profiles exported by this dashboard (version 1.x or 2.x). Older tier names are converted; legacy L4 grants are dropped.">
        <textarea value={imp} rows={8} aria-label="Profile JSON to import" placeholder='{"version":"2.0.0","profile":{…}}' onChange={(e) => setImp(e.target.value)} />
        <div className="row" style={{ marginTop: 8 }}><button className="btn pri" disabled={!imp.trim()} onClick={doImport}><Upload size={14} />Import configuration</button></div>
        {msg && <p className="small" role={msg.ok ? "status" : "alert"} style={{ color: msg.ok ? "#34d399" : "#f87171" }}>{msg.text}</p>}
      </Panel>
    </div>
  );
};

// ============================================================================
// 8. APP SHELL
// ============================================================================

const NAV: { id: PageId; label: string; icon: React.ReactNode; title: string; sub: string }[] = [
  { id: "overview", label: "Overview", icon: <LayoutGrid size={16} />, title: "Your ad privacy boundary", sub: "Where your data can go, and what every SCW does with 18 test prompts." },
  { id: "map", label: "Latent Map", icon: <MapIcon size={16} />, title: "Latent map", sub: "Your sealed core, memory tiers and SCWs, with fictional advertisers probing the boundary in real time." },
  { id: "studio", label: "SCW Studio", icon: <SlidersHorizontal size={16} />, title: "SCW Studio", sub: "Design each context world: mode, tiers, categories, limits and blocked topics." },
  { id: "simulate", label: "Simulator", icon: <Zap size={16} />, title: "Simulator", sub: "Chat as you would in ChatGPT and watch each rule decide." },
  { id: "lens", label: "Advertiser Lens", icon: <Eye size={16} />, title: "Advertiser lens", sub: "Your message on one side, the exact payload that crosses the boundary on the other." },
  { id: "memory", label: "Memory", icon: <Brain size={16} />, title: "Memory tiers", sub: "Maxey0's five typed tiers and the evidence-gated promotion gate." },
  { id: "learn", label: "Learn SCWs", icon: <BookOpen size={16} />, title: "Learn logical SCWs", sub: "A five-minute introduction to Structured Context Worlds." },
  { id: "apply", label: "Apply to ChatGPT", icon: <Megaphone size={16} />, title: "Apply to ChatGPT", sub: "Global controls, the settings ChatGPT enforces, and your portable profile." },
];

export default function Maxey0SCWsForChatGPTAds() {
  const [s, dispatch] = useReducer(reducer, undefined, initialState);
  const [page, setPage] = useState<PageId>("overview");
  const [draft, setDraft] = useState<{ text: string; gateId: string | null }>({ text: "", gateId: null });
  const score = privacyScore(s.profile);
  const topRef = useRef<HTMLDivElement>(null);
  const go = useCallback((p: PageId) => { setPage(p); topRef.current?.scrollIntoView?.({ block: "start" }); }, []);
  const simPrefill = useCallback((text: string, gateId: string) => { setDraft({ text, gateId }); go("simulate"); }, [go]);
  useEffect(() => { if (!s.toast) return; const t = setTimeout(() => dispatch({ type: "toast", msg: null }), 2600); return () => clearTimeout(t); }, [s.toast]);
  const meta = NAV.find((n) => n.id === page)!;
  const props: PageProps = { s, dispatch, go, simPrefill };
  return (
    <div className="mx" ref={topRef}>
      <style>{CSS}</style>
      <nav className="mobnav" aria-label="Sections">{NAV.map((n) => <button key={n.id} aria-current={page === n.id ? "page" : undefined} onClick={() => go(n.id)}>{n.label}</button>)}</nav>
      <div className="shell">
        <aside className="side">
          <div className="brand"><div className="logo"><div><Fingerprint size={16} color="#a5b4fc" /></div></div><div><b>Maxey0 SCW Privacy</b><span>for ChatGPT ads</span></div></div>
          <nav className="nav" aria-label="Sections">{NAV.map((n) => <button key={n.id} aria-current={page === n.id ? "page" : undefined} onClick={() => go(n.id)}>{n.icon}{n.label}{n.id === "map" && <small>live</small>}</button>)}</nav>
          <div className="stat" style={{ marginTop: 8 }}><div className="k">Privacy score</div><div className="row" style={{ gap: 8 }}><span className="big num">{score}</span><div style={{ flex: 1, height: 6, borderRadius: 6, background: "#1a1f42", overflow: "hidden" }}><div style={{ width: `${score}%`, height: "100%", background: "linear-gradient(90deg,#22d3ee,#7c8cff)", transition: "width .5s" }} /></div></div></div>
          <div className="sidefoot">Runs entirely on this page. No server, no storage. Advertisers are fictional. Profile v{EXPORT_VERSION}.</div>
        </aside>
        <main>
          <div className="top">
            <div className="grow"><h1>{meta.title}</h1><p>{meta.sub}</p></div>
            <span className="pill"><Shield size={13} />{MODES.map((m) => { const n = s.profile.scwGates.filter((g) => g.gateType === m.id).length; return n ? <span key={m.id} style={{ color: m.color }}>{n} {m.label.toLowerCase()}</span> : null; })}</span>
            <button className="btn sm" onClick={() => dispatch({ type: "undo" })} disabled={!s.past.length}><Undo2 size={13} />Undo</button>
          </div>
          {page === "overview" && <Overview {...props} />}
          {page === "map" && <LatentPage {...props} />}
          {page === "studio" && <StudioPage {...props} />}
          {page === "simulate" && <SimulatePage {...props} draft={draft} setDraft={setDraft} />}
          {page === "lens" && <LensPage {...props} />}
          {page === "memory" && <MemoryPage {...props} />}
          {page === "learn" && <LearnPage {...props} />}
          {page === "apply" && <ApplyPage {...props} />}
        </main>
      </div>
      {s.toast && <div className="toast" role="status"><Info size={15} color="#a5b4fc" />{s.toast}</div>}
    </div>
  );
}

// Exported for tests.
export { classifyText, evaluateTurn, importProfile, exportProfile, privacyScore, gateExposure, normalizeMemoryTiers, PRESETS, CORPUS, INVENTORY };
