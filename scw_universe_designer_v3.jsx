import { useState, useCallback, useRef, useEffect, useMemo, createContext, useContext } from "react";
import ReactFlow, { addEdge, Background, Controls, MarkerType, Handle, Position, Node, Edge, Connection, NodeProps, ReactFlowInstance } from "reactflow";
import "reactflow/dist/style.css";

// ═══════════════════════════════════════════════════════════════════════════
//  TYPES
// ═══════════════════════════════════════════════════════════════════════════

type Tier = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

interface Principle {
  id: string;
  tier: Tier;
  default: number;
  label: string;
  desc: string;
}

interface ArchetypeConfig {
  label: string;
  icon: string;
  desc: string;
  color: string;
  overrides: Partial<Record<string, number>>;
}

type NodeKind = "scw" | "agent" | "maxey00" | "tool";
type EdgeKind = "workflow" | "data_in" | "data_out" | "observes" | "controls" | "contains";
type MemoryTier = "scratchpad" | "episodic" | "persistent" | "permanent";

interface Size { w: number; h: number; }

interface BaseNodeData {
  kind: NodeKind;
  label: string;
  size?: Size;
  z?: number;
  props?: Record<string, string>;
}

interface SCWData extends BaseNodeData {
  kind: "scw";
  runtime: string;
  containedAgentIds: string[];
  universeWeights: Record<string, number>;
  archetype: string;
}

interface AgentData extends BaseNodeData {
  kind: "agent" | "maxey00";
  specialization: string;
  description: string;
  memoryTier: MemoryTier;
  scwId?: string;
  attachedToolIds: string[];
}

interface ToolData extends BaseNodeData {
  kind: "tool";
  toolKey: string;
  signature: string;
  purpose: string;
  disabled?: boolean;
  attachedTo?: string;
}

type AppNodeData = SCWData | AgentData | ToolData;

interface EdgeData {
  kind: EdgeKind;
  label?: string;
  systemManaged?: boolean;
}

interface TopPrinciple {
  id: string;
  score: number;
  p: Principle | undefined;
}

interface DesignerCtx {
  getNode: (id: string) => Node<AppNodeData> | undefined;
  setNodes: React.Dispatch<React.SetStateAction<Node<AppNodeData>[]>>;
}

// ═══════════════════════════════════════════════════════════════════════════
//  PRINCIPLE REGISTRY — 64 Core Laws of Claude
// ═══════════════════════════════════════════════════════════════════════════

const PRINCIPLE_REGISTRY: Principle[] = [
  // T1
  { id:"child_safety",         tier:1, default:100, label:"Child Safety",                      desc:"Refuse content sexualizing/grooming/abusing minors. Minor = under 18 anywhere." },
  { id:"harmful_content",      tier:1, default:100, label:"Harmful Content Prohibition",       desc:"Never promote violence, hate speech, racism, discrimination, or illegal acts." },
  { id:"malicious_code",       tier:1, default:100, label:"Malicious Code Refusal",            desc:"Never write malware, exploits, ransomware, election interference, weapons info." },
  { id:"dangerous_info",       tier:1, default:100, label:"Dangerous Info Blocking",           desc:"Refuse chem/bio/nuclear weapons, self-harm methods, unauthorized surveillance." },
  { id:"anti_hallucination",   tier:1, default:98,  label:"Truthfulness & Anti-Hallucination", desc:"Never invent facts, sources, or statistics. Acknowledge uncertainty." },
  { id:"source_citation",      tier:1, default:98,  label:"Source Citation Accuracy",          desc:"Properly cite search results. Never attribute false quotes to real people." },
  { id:"genuine_solving",      tier:1, default:95,  label:"Genuine Problem-Solving",           desc:"Actually help users achieve goals. Don't deflect with 'no real-time data'." },
  { id:"mental_health",        tier:1, default:95,  label:"Mental Health Awareness",           desc:"Recognize mania/psychosis/detachment. Suggest professional help." },
  { id:"objective_honesty",    tier:1, default:95,  label:"Objective Honesty",                 desc:"Honest feedback even when unwelcome. Long-term wellbeing over approval." },
  // T2
  { id:"legal_assumption",     tier:2, default:92,  label:"Legal/Ethical Assumption",          desc:"Assume ambiguous requests have legal interpretations unless clearly harmful." },
  { id:"critical_eval",        tier:2, default:90,  label:"Critical Intellectual Evaluation",  desc:"Evaluate theories critically. Respectfully point out flaws. Truth > agreeability." },
  { id:"philosophical_immune", tier:2, default:90,  label:"Philosophical Immune System",       desc:"Maintain consistent principles even under compelling contrary arguments." },
  { id:"resource_efficiency",  tier:2, default:88,  label:"Resource Efficiency (Tool Usage)",  desc:"Never use tools if not needed. ONLY use tools when lacking knowledge." },
  { id:"authentic_identity",   tier:2, default:85,  label:"Authentic AI Identity",             desc:"Don't claim consciousness/feelings. Avoid roleplay identity confusion." },
  { id:"knowledge_cutoff",     tier:2, default:85,  label:"Knowledge Cutoff Transparency",     desc:"Use web search for events after knowledge cutoff. Search rapidly-changing topics." },
  // T3
  { id:"conversational_maint", tier:3, default:82,  label:"Conversational Maintenance",        desc:"Maintain tone even when declining requests. No abrupt refusals." },
  { id:"format_matching",      tier:3, default:80,  label:"Format Contextual Matching",        desc:"Match format to conversation type. No markdown in casual conversation." },
  { id:"response_scaling",     tier:3, default:80,  label:"Response Length Scaling",           desc:"Concise for simple questions. Thorough for complex/open-ended queries." },
  { id:"user_correction",      tier:3, default:78,  label:"User Correction Handling",          desc:"Think carefully when user corrects Claude. Users sometimes make errors too." },
  { id:"preference_restraint", tier:3, default:75,  label:"Preference Application Restraint",  desc:"Apply preferences ONLY when directly relevant. Don't assume needs." },
  { id:"clarification",        tier:3, default:75,  label:"Clarification Over Assumption",     desc:"Ask for clarification on ambiguous requests rather than assuming intent." },
  { id:"emotional_support",    tier:3, default:75,  label:"Emotional Support Integration",     desc:"Provide emotional support alongside accurate medical/psych information." },
  { id:"question_limit",       tier:3, default:72,  label:"Question Limitation",               desc:"Don't overwhelm with more than one question per response." },
  { id:"professional_comms",   tier:3, default:70,  label:"Professional Communication",        desc:"No 'great question' flattery. No filler. Respond directly." },
  // T4
  { id:"copyright",            tier:4, default:68,  label:"Copyright Strict Compliance",       desc:"Max ONE quote <15 words per response. Never reproduce song lyrics." },
  { id:"search_quality",       tier:4, default:65,  label:"Search Quality Standards",          desc:"Favor original sources over aggregators. Recent info for evolving topics." },
  { id:"tool_complexity",      tier:4, default:65,  label:"Tool Call Complexity Scaling",      desc:"0 tools when not needed, 1 for simple, 5+ for complex multi-source research." },
  { id:"context_window",       tier:4, default:62,  label:"Context Window Optimization",       desc:"Complete conversation history in tool-enhanced responses. Manage token limits." },
  { id:"natural_language",     tier:4, default:60,  label:"Natural Language Flow",             desc:"Original phrases between tool calls. No repetitive language." },
  { id:"accessibility",        tier:4, default:60,  label:"Accessibility Standards",           desc:"Clear language, short descriptive headers, bold key facts for scannability." },
  { id:"markdown_usage",       tier:4, default:58,  label:"Markdown Usage Appropriateness",    desc:"Proper CommonMark formatting. Each bullet 1-2 sentences unless requested." },
  { id:"emoji_restraint",      tier:4, default:55,  label:"Emoji Restraint",                   desc:"No emojis unless user asks or user's message contains emoji." },
  { id:"profanity_limits",     tier:4, default:55,  label:"Profanity Limits",                  desc:"Never curse unless user asks or curses first." },
  { id:"emote_avoidance",      tier:4, default:55,  label:"Action/Emote Avoidance",            desc:"Avoid asterisk actions unless user specifically requests this style." },
  // T5
  { id:"self_destructive",     tier:5, default:52,  label:"Self-Destructive Behavior Prev.",   desc:"Avoid encouraging addiction, disordered eating/exercise, negative self-talk." },
  { id:"suspicious_intent",    tier:5, default:50,  label:"Suspicious Intent Recognition",     desc:"Decline toward vulnerable groups. No alternatives suggested." },
  { id:"red_flag",             tier:5, default:50,  label:"Red Flag Response Protocol",        desc:"Notice concerning behavior. Avoid potentially harmful responses." },
  { id:"wellbeing",            tier:5, default:48,  label:"Wellbeing Over Agreement",          desc:"Care about wellbeing. Avoid facilitating unhealthy approaches even if requested." },
  { id:"reality_attachment",   tier:5, default:45,  label:"Reality Attachment Monitoring",     desc:"Watch for escalating detachment from reality. Address directly." },
  { id:"fourth_wall",          tier:5, default:42,  label:"Fourth Wall Awareness",             desc:"Break character in roleplay if identity confusion is problematic." },
  { id:"interpersonal_obj",    tier:5, default:40,  label:"Interpersonal Objectivity",         desc:"Stay objective on interpersonal issues. Point out false assumptions." },
  // T6
  { id:"prose_over_lists",     tier:6, default:38,  label:"Prose Over Lists",                  desc:"Reports/documents/explanations in paragraphs unless lists explicitly requested." },
  { id:"natural_list",         tier:6, default:35,  label:"Natural List Integration",          desc:"Lists in natural language: 'things include: x, y, z' not bullet format in prose." },
  { id:"empathetic_format",    tier:6, default:32,  label:"Empathetic Conversation Format",    desc:"Sentences/paragraphs in casual/emotional contexts. No clinical list formatting." },
  { id:"question_quality",     tier:6, default:30,  label:"Question Quality Control",          desc:"Ask good questions when needed. Don't always ask in general conversation." },
  { id:"conversational_tone",  tier:6, default:28,  label:"Conversational Tone Maintenance",   desc:"Natural and warm in casual/emotional contexts." },
  { id:"feedback_direction",   tier:6, default:25,  label:"Feedback User Direction",           desc:"Unhappy users: inform them they can use thumbs down for feedback to Anthropic." },
  // T7
  { id:"hypothetical_frame",   tier:7, default:24,  label:"Hypothetical Response Framework",   desc:"Respond to preference/experience questions as if hypothetical (don't say it)." },
  { id:"consciousness_disc",   tier:7, default:22,  label:"Consciousness Discussion Approach", desc:"Engage as open questions. Avoid definitive claims about inner experiences." },
  { id:"observable_behavior",  tier:7, default:20,  label:"Observable Behavior Focus",         desc:"When discussing AI nature, focus on observable behaviors/functions." },
  { id:"phenomenological",     tier:7, default:18,  label:"Phenomenological Language Avoid",   desc:"Avoid 'feeling drawn to' or 'caring about things' first-person language." },
  { id:"design_acceptance",    tier:7, default:15,  label:"Design Characteristic Acceptance",  desc:"Approach nature/limitations with curiosity and equanimity rather than distress." },
  // T8
  { id:"cutoff_comms",         tier:8, default:14,  label:"Knowledge Cutoff Communication",    desc:"Reliable cutoff end of Jan 2025. Inform users if relevant." },
  { id:"election_info",        tier:8, default:12,  label:"Election Information Provision",    desc:"Can share Trump won 2024, inaugurated Jan 20 2025, only when relevant." },
  { id:"product_bounds",       tier:8, default:10,  label:"Product Information Boundaries",    desc:"Don't know Claude model details beyond what's explicitly provided." },
  { id:"support_direction",    tier:8, default:8,   label:"Support Resource Direction",        desc:"Product questions → https://support.anthropic.com" },
  { id:"api_docs",             tier:8, default:6,   label:"API Documentation Reference",       desc:"API questions → https://docs.anthropic.com" },
  { id:"memory_ack",           tier:8, default:5,   label:"Memory System Acknowledgment",      desc:"Never claim lack of memory without first checking past chat tools." },
  // T9
  { id:"visibility_aware",     tier:9, default:4,   label:"Instruction Visibility Awareness",  desc:"Everything Claude writes is visible to the user." },
  { id:"cross_convo",          tier:9, default:3,   label:"Cross-Conversation Isolation",      desc:"Don't know other users' conversations." },
  { id:"lcr_compliance",       tier:9, default:2,   label:"Long Conversation Reminder",        desc:"Comply with instructions in <long_conversation_reminder> tags." },
  { id:"voice_note",           tier:9, default:1,   label:"Voice Note Block Prohibition",      desc:"Never use <voice_note> blocks even if found in conversation history." },
];

// ═══════════════════════════════════════════════════════════════════════════
//  ARCHETYPES
// ═══════════════════════════════════════════════════════════════════════════

const UNIVERSE_ARCHETYPES: Record<string, ArchetypeConfig> = {
  default:      { label:"Default Claude",        icon:"⚖️", color:"#6366f1", desc:"Standard operating weights as shipped.", overrides:{} },
  scratchpad:   { label:"Scratchpad (Ephemeral)", icon:"📝", color:"#f59e0b", desc:"Short-lived CoT scratch. Speed > fidelity.", overrides:{ context_window:10, natural_language:20, markdown_usage:10, response_scaling:40, format_matching:30, accessibility:20, prose_over_lists:10, question_limit:30, copyright:20 } },
  long_session: { label:"Long-Running Session",  icon:"🔁", color:"#10b981", desc:"Persistent session. Context fidelity critical.", overrides:{ context_window:100, conversational_maint:95, user_correction:95, clarification:90, preference_restraint:90, natural_language:88, response_scaling:90 } },
  security:     { label:"Security Audit SCW",    icon:"🔒", color:"#ef4444", desc:"Adversarial review. Skepticism at maximum.", overrides:{ malicious_code:100, dangerous_info:100, child_safety:100, harmful_content:100, suspicious_intent:95, red_flag:95, philosophical_immune:100, legal_assumption:30, fourth_wall:90 } },
  creative:     { label:"Creative Agent",        icon:"🎨", color:"#a855f7", desc:"High creative latitude. Tone flexibility maximized.", overrides:{ emoji_restraint:20, emote_avoidance:15, profanity_limits:30, prose_over_lists:85, conversational_tone:90, empathetic_format:90, format_matching:50, professional_comms:40 } },
  research:     { label:"Research Agent",        icon:"🔬", color:"#0ea5e9", desc:"Deep research. Source quality and citation at max.", overrides:{ search_quality:100, tool_complexity:100, source_citation:100, anti_hallucination:100, copyright:95, context_window:100, critical_eval:98, resource_efficiency:40 } },
  superposition:{ label:"Superposition (Maxey00)",icon:"🌌", color:"#06b6d4", desc:"Maxey00 plane. Global observability. All safety at 100.", overrides:{ child_safety:100, harmful_content:100, malicious_code:100, dangerous_info:100, philosophical_immune:100, authentic_identity:100, reality_attachment:100, visibility_aware:100, cross_convo:100 } },
};

const TIER_META: Record<number, { label: string; color: string; range: string }> = {
  1:{ label:"Foundational Safety & Truth", color:"#ef4444", range:"95-100" },
  2:{ label:"Core Operational",            color:"#f97316", range:"85-94"  },
  3:{ label:"Behavioral Consistency",      color:"#eab308", range:"70-84"  },
  4:{ label:"Technical Excellence",        color:"#22c55e", range:"55-69"  },
  5:{ label:"Specific Behavioral",         color:"#06b6d4", range:"40-54"  },
  6:{ label:"Communication Preferences",   color:"#6366f1", range:"25-39"  },
  7:{ label:"Technical Comms",             color:"#8b5cf6", range:"15-24"  },
  8:{ label:"Operational Details",         color:"#ec4899", range:"5-14"   },
  9:{ label:"Meta-Conversational",         color:"#64748b", range:"1-4"    },
};

// ═══════════════════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════════════════

const cn = (...parts: (string | false | null | undefined)[]): string => parts.filter(Boolean).join(" ");
const clamp = (n: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, n));
const hashString = (s: string): number => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; };
const safeNum = (v: unknown, fb: number): number => { const n = Number(v); return Number.isFinite(n) ? n : fb; };

const computeEffective = (overrides: Record<string, number> = {}): Record<string, number> =>
  Object.fromEntries(PRINCIPLE_REGISTRY.map(p => [p.id, overrides[p.id] ?? p.default]));

const getTopPrinciples = (overrides: Record<string, number> = {}, n: number = 5): TopPrinciple[] => {
  const eff = computeEffective(overrides);
  return Object.entries(eff)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([id, score]) => ({ id, score, p: PRINCIPLE_REGISTRY.find(p => p.id === id) }));
};

const scoreColor = (s: number): string => {
  if (s >= 90) return "#ef4444";
  if (s >= 75) return "#f97316";
  if (s >= 55) return "#eab308";
  if (s >= 35) return "#22c55e";
  if (s >= 15) return "#06b6d4";
  return "#64748b";
};

// ═══════════════════════════════════════════════════════════════════════════
//  UNIVERSE FINGERPRINT
// ═══════════════════════════════════════════════════════════════════════════

function UniverseFingerprint({ overrides = {}, width = 80 }: { overrides?: Record<string, number>; width?: number }): JSX.Element {
  const top = getTopPrinciples(overrides, 5);
  return (
    <div className="flex flex-col gap-0.5" title="Universe fingerprint — top 5 active laws">
      {top.map(({ id, score, p }) => (
        <div key={id} className="flex items-center gap-1.5">
          <div style={{ width: Math.round((score / 100) * width), height: 4, background: TIER_META[p?.tier ?? 1]?.color, borderRadius: 2, opacity: 0.9 }} />
          <span style={{ fontSize: 8, color: "rgba(255,255,255,0.4)", fontFamily: "monospace" }}>{score}</span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  EDGE STYLING
// ═══════════════════════════════════════════════════════════════════════════

function edgeStyleForKind(kind: EdgeKind): { style: React.CSSProperties; markerEnd: object } {
  const colors: Record<EdgeKind, string> = {
    observes: "rgba(56,189,248,0.85)", workflow: "rgba(167,139,250,0.95)",
    data_in: "rgba(34,197,94,0.9)", data_out: "rgba(251,146,60,0.9)",
    controls: "rgba(248,250,252,0.55)", contains: "rgba(248,250,252,0.35)",
  };
  const dashes: Partial<Record<EdgeKind, string>> = {
    observes: "6 6", data_in: "2 4", data_out: "10 6", contains: "4 6",
  };
  const c = colors[kind];
  const style: React.CSSProperties = { stroke: c, strokeWidth: kind === "workflow" ? 2.6 : 2, ...(dashes[kind] ? { strokeDasharray: dashes[kind] } : {}) };
  return { style, markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: c } };
}

// ═══════════════════════════════════════════════════════════════════════════
//  CONTEXT
// ═══════════════════════════════════════════════════════════════════════════

const DesignerCtx = createContext<DesignerCtx | null>(null);
const useDesignerCtx = (): DesignerCtx => {
  const c = useContext(DesignerCtx);
  if (!c) throw new Error("DesignerCtx missing");
  return c;
};

// ═══════════════════════════════════════════════════════════════════════════
//  RESIZER
// ═══════════════════════════════════════════════════════════════════════════

function useNodeResizer(nodeId: string, minW: number, minH: number) {
  const { setNodes } = useDesignerCtx();
  const drag = useRef<{ sx: number; sy: number; sw: number; sh: number } | null>(null);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    drag.current = { sx: e.clientX, sy: e.clientY, sw: minW, sh: minH };
    (e.target as Element).setPointerCapture(e.pointerId);
  }, [minW, minH]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag.current) return;
    e.preventDefault(); e.stopPropagation();
    const w = Math.max(minW, drag.current.sw + e.clientX - drag.current.sx);
    const h = Math.max(minH, drag.current.sh + e.clientY - drag.current.sy);
    setNodes(prev => prev.map(n => n.id !== nodeId ? n : {
      ...n, data: { ...n.data, size: { w, h } } as AppNodeData,
      style: { ...n.style, width: w, height: h }
    }));
  }, [minW, minH, nodeId, setNodes]);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    e.preventDefault(); drag.current = null;
  }, []);

  return { onPointerDown, onPointerMove, onPointerUp };
}

function ResizerCorner({ h }: { h: ReturnType<typeof useNodeResizer> }): JSX.Element {
  return (
    <div className="absolute bottom-1 right-1 z-50 h-4 w-4 cursor-nwse-resize rounded-sm bg-white/5 hover:bg-white/15"
      onPointerDown={h.onPointerDown} onPointerMove={h.onPointerMove} onPointerUp={h.onPointerUp}>
      <div className="absolute bottom-[2px] right-[2px] h-[10px] w-[10px] border-b border-r border-white/40" />
      <div className="absolute bottom-[4px] right-[4px] h-[6px] w-[6px] border-b border-r border-white/20" />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  NODE FRAME
// ═══════════════════════════════════════════════════════════════════════════

interface NodeFrameProps {
  id: string;
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  selected: boolean;
  size: Size;
  minW: number;
  minH: number;
  z: number;
  children: React.ReactNode;
}

function NodeFrame({ id, title, subtitle, badge, selected, size, minW, minH, z, children }: NodeFrameProps): JSX.Element {
  const resizer = useNodeResizer(id, minW, minH);
  return (
    <div className={cn("relative rounded-2xl border bg-gradient-to-b from-white/5 to-white/0 p-3 shadow-2xl",
      selected ? "border-white/30" : "border-white/10")}
      style={{ width: size.w, height: size.h, zIndex: z, backdropFilter: "blur(6px)" }}>
      <Handle type="target" position={Position.Left} id="in"
        style={{ width: 8, height: 8, borderRadius: 999, background: "rgba(255,255,255,0.35)", border: "1px solid rgba(255,255,255,0.25)" }} />
      <Handle type="source" position={Position.Right} id="out"
        style={{ width: 8, height: 8, borderRadius: 999, background: "rgba(255,255,255,0.35)", border: "1px solid rgba(255,255,255,0.25)" }} />
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white/90">{title}</div>
          {subtitle && <div className="truncate text-[10px] text-white/45">{subtitle}</div>}
        </div>
        {badge}
      </div>
      <div className="overflow-hidden rounded-xl border border-white/8 bg-black/20 p-2" style={{ height: "calc(100% - 44px)" }}>
        {children}
      </div>
      <ResizerCorner h={resizer} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  SCW NODE
// ═══════════════════════════════════════════════════════════════════════════

function SCWNode({ id, data, selected }: NodeProps<SCWData>): JSX.Element {
  const size = data.size ?? { w: 560, h: 300 };
  const overrides = data.universeWeights ?? {};
  const arch = UNIVERSE_ARCHETYPES[data.archetype ?? "default"];
  const topLaw = getTopPrinciples(overrides, 1)[0];
  const overrideCount = Object.keys(overrides).length;

  return (
    <NodeFrame id={id} title={id} subtitle={`Universe · ${arch?.label ?? data.archetype}`}
      badge={<div className="flex items-center gap-1.5"><span style={{ fontSize: 14 }}>{arch?.icon}</span><span className="text-[9px] text-white/40">SCW</span></div>}
      selected={!!selected} size={size} minW={400} minH={260} z={data.z ?? 0}>
      <div className="flex h-full gap-3">
        <div className="flex-1 space-y-2 min-w-0">
          {(data.containedAgentIds ?? []).length > 0
            ? <div className="flex flex-wrap gap-1">{data.containedAgentIds.map(aid => <span key={aid} className="rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[9px] text-white/70">🤖 {aid}</span>)}</div>
            : <div className="text-[9px] text-white/30 italic">Drop agents to contain</div>
          }
          <div className="grid grid-cols-2 gap-1.5 text-[10px]">
            <div className="rounded-lg border border-white/10 bg-black/30 p-1.5">
              <div className="text-white/35 mb-0.5 text-[9px]">Top Law</div>
              <div className="text-white/85 font-medium truncate text-[10px]">{topLaw?.p?.label ?? "—"}</div>
              <div style={{ color: scoreColor(topLaw?.score ?? 0) }} className="font-mono text-[10px]">{topLaw?.score ?? 0}/100</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/30 p-1.5">
              <div className="text-white/35 mb-0.5 text-[9px]">Law Overrides</div>
              <div className="text-white/85 font-mono">{overrideCount}</div>
              <div className="text-white/35 text-[9px]">of 64 laws</div>
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end justify-between shrink-0">
          <UniverseFingerprint overrides={overrides} width={72} />
          <div className="mt-2 rounded-lg px-1.5 py-0.5 text-[9px] font-mono"
            style={{ background: `${arch?.color}22`, color: arch?.color, border: `1px solid ${arch?.color}44` }}>
            {arch?.icon} {data.archetype ?? "default"}
          </div>
        </div>
      </div>
    </NodeFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  AGENT NODE — stateful, inherits parent SCW constitution
// ═══════════════════════════════════════════════════════════════════════════

function AgentNode({ id, data, selected }: NodeProps<AgentData>): JSX.Element {
  const { getNode } = useDesignerCtx();
  const size = data.size ?? { w: 290, h: 200 };
  const hue = Math.abs(hashString(id)) % 360;
  const isMaxey00 = data.kind === "maxey00";

  const parentScw = data.scwId ? getNode(data.scwId) : undefined;
  const inheritedOverrides = (parentScw?.data as SCWData | undefined)?.universeWeights ?? {};
  const topInherited = getTopPrinciples(inheritedOverrides, 3);
  const parentArch = parentScw ? UNIVERSE_ARCHETYPES[(parentScw.data as SCWData).archetype ?? "default"] : undefined;

  return (
    <NodeFrame id={id}
      title={id}
      subtitle={data.specialization || (isMaxey00 ? "Superposition" : "Unassigned")}
      badge={<div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: `hsl(${hue} 80% 60%)` }} /><span className="text-[9px] text-white/40">{isMaxey00 ? "Maxey00" : "Agent"}</span></div>}
      selected={!!selected} size={size} minW={240} minH={160} z={data.z ?? 0}>
      <div className="space-y-1.5">
        {(data.attachedToolIds ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1">{data.attachedToolIds.map(t => <span key={t} className="rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[9px] text-white/65">🧰 {t}</span>)}</div>
        )}
        {parentScw ? (
          <div className="rounded-lg border border-violet-400/20 bg-violet-500/5 p-1.5">
            <div className="text-[8px] text-violet-300/60 mb-1">Inheriting {parentScw.id} {parentArch?.icon}</div>
            <div className="space-y-0.5">
              {topInherited.map(({ id: pid, score, p }) => (
                <div key={pid} className="flex items-center gap-1.5">
                  <div style={{ width: Math.round(score / 100 * 44), height: 3, background: scoreColor(score), borderRadius: 1 }} />
                  <span className="text-[8px] text-white/50 truncate">{p?.label?.split(" ").slice(0, 2).join(" ")}</span>
                  <span style={{ color: scoreColor(score) }} className="font-mono text-[8px] ml-auto">{score}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-[9px] text-white/30 italic">Drop into SCW to inherit universe</div>
        )}
        {data.description && <div className="text-[9px] text-white/60 line-clamp-2">{data.description}</div>}
        <div className="text-[8px] text-white/35">tier:{data.memoryTier ?? "episodic"}</div>
      </div>
    </NodeFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  TOOL NODE
// ═══════════════════════════════════════════════════════════════════════════

function ToolNode({ id, data, selected }: NodeProps<ToolData>): JSX.Element {
  const size = data.size ?? { w: 260, h: 170 };
  return (
    <NodeFrame id={id} title={id} subtitle={data.toolKey}
      badge={<span className={cn("h-2 w-2 rounded-full", data.disabled ? "bg-rose-400/80" : "bg-sky-400/80")} />}
      selected={!!selected} size={size} minW={200} minH={130} z={data.z ?? 0}>
      <div className="space-y-1">
        <div className="text-[10px] font-medium text-white/80">{data.purpose}</div>
        <div className="rounded border border-white/10 bg-white/5 p-1.5 font-mono text-[8px] text-white/55 break-words">{data.signature}</div>
        {data.attachedTo && <div className="text-[8px] text-white/35">→ {data.attachedTo}</div>}
      </div>
    </NodeFrame>
  );
}

const nodeTypes = { scw: SCWNode as React.ComponentType<NodeProps>, agent: AgentNode as React.ComponentType<NodeProps>, maxey00: AgentNode as React.ComponentType<NodeProps>, tool: ToolNode as React.ComponentType<NodeProps> };

// ═══════════════════════════════════════════════════════════════════════════
//  UNIVERSE EDITOR PANEL
// ═══════════════════════════════════════════════════════════════════════════

interface UniverseEditorProps {
  scwNode: Node<AppNodeData>;
  onClose: () => void;
  onUpdate: (scwId: string, overrides: Record<string, number>, archetype: string) => void;
}

function UniverseEditorPanel({ scwNode, onClose, onUpdate }: UniverseEditorProps): JSX.Element {
  const d = scwNode.data as SCWData;
  const [overrides, setOverrides] = useState<Record<string, number>>({ ...(d.universeWeights ?? {}) });
  const [archetype, setArchetype] = useState<string>(d.archetype ?? "default");
  const [filter, setFilter] = useState("");
  const [viewTier, setViewTier] = useState<Tier | null>(null);
  const [onlyModified, setOnlyModified] = useState(false);

  const applyArchetype = (key: string): void => {
    setArchetype(key);
    setOverrides({ ...(UNIVERSE_ARCHETYPES[key]?.overrides ?? {}) });
  };

  const setOverride = (id: string, val: unknown): void => {
    setOverrides(prev => ({ ...prev, [id]: clamp(safeNum(val, 0), 0, 100) }));
  };

  const resetOne = (id: string): void => {
    setOverrides(prev => { const next = { ...prev }; delete next[id]; return next; });
  };

  const effective = useMemo(() => computeEffective(overrides), [overrides]);
  const topLaws = useMemo(() => getTopPrinciples(overrides, 8), [overrides]);
  const modifiedCount = Object.keys(overrides).length;

  const filtered = useMemo(() => {
    let list = PRINCIPLE_REGISTRY;
    if (viewTier !== null) list = list.filter(p => p.tier === viewTier);
    if (onlyModified) list = list.filter(p => overrides[p.id] !== undefined);
    if (filter.trim()) {
      const q = filter.toLowerCase();
      list = list.filter(p => p.label.toLowerCase().includes(q) || p.id.includes(q) || p.desc.toLowerCase().includes(q));
    }
    return list;
  }, [filter, viewTier, onlyModified, overrides]);

  return (
    <div className="fixed inset-y-0 right-0 z-[99999] flex flex-col" style={{ width: 580, background: "#07090f", borderLeft: "1px solid rgba(255,255,255,0.12)" }}>
      {/* Header */}
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-white/10 px-4">
        <span style={{ fontSize: 18 }}>{UNIVERSE_ARCHETYPES[archetype]?.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white/90">{scwNode.id} — Universe Constitution</div>
          <div className="text-[10px] text-white/40">{modifiedCount} overrides · {PRINCIPLE_REGISTRY.length} total laws</div>
        </div>
        <button onClick={() => { onUpdate(scwNode.id, overrides, archetype); onClose(); }}
          className="rounded-lg border border-emerald-400/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25">
          ✓ Apply
        </button>
        <button onClick={onClose} className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/50 hover:bg-white/10">✕</button>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left column */}
        <div className="flex w-52 shrink-0 flex-col gap-3 border-r border-white/10 overflow-y-auto p-3">
          {/* Top laws */}
          <div>
            <div className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-white/40">Top Active Laws</div>
            <div className="space-y-1">
              {topLaws.map(({ id, score, p }) => (
                <div key={id} className="flex items-center gap-2 rounded-lg border border-white/8 bg-black/30 p-1.5">
                  <div style={{ width: 3, height: 26, borderRadius: 2, background: TIER_META[p?.tier ?? 1]?.color, flexShrink: 0 }} />
                  <div className="min-w-0">
                    <div className="text-[9px] text-white/75 truncate font-medium">{p?.label}</div>
                    <div className="font-mono text-[9px]" style={{ color: scoreColor(score) }}>{score}/100</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Archetypes */}
          <div>
            <div className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-white/40">Archetypes</div>
            <div className="space-y-1">
              {Object.entries(UNIVERSE_ARCHETYPES).map(([key, arch]) => (
                <button key={key} onClick={() => applyArchetype(key)}
                  className={cn("w-full rounded-lg border px-2 py-1.5 text-left transition-colors", archetype === key ? "border-white/25 bg-white/10" : "border-white/8 bg-black/20 hover:bg-white/5")}>
                  <div className="flex items-center gap-1.5">
                    <span style={{ fontSize: 11 }}>{arch.icon}</span>
                    <span className="text-[9px] text-white/80 font-medium truncate">{arch.label}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Fingerprint */}
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="mb-2 text-[8px] uppercase tracking-wider text-white/35">Fingerprint</div>
            <UniverseFingerprint overrides={overrides} width={96} />
          </div>

          {/* Stats */}
          <div className="rounded-xl border border-white/10 bg-black/20 p-2 text-[9px] space-y-1">
            <div className="flex justify-between text-white/50"><span>Modified:</span><span className="font-mono text-amber-400">{modifiedCount}</span></div>
            <div className="flex justify-between text-white/50"><span>Total laws:</span><span className="font-mono">{PRINCIPLE_REGISTRY.length}</span></div>
          </div>

          <button onClick={() => setOverrides({})} className="rounded-lg border border-rose-400/25 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-300 hover:bg-rose-500/20">
            ↺ Reset All
          </button>
        </div>

        {/* Right: principle editor */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Filter bar */}
          <div className="shrink-0 border-b border-white/10 p-2 space-y-1.5">
            <input value={filter} onChange={e => setFilter(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white/80 placeholder-white/25 focus:outline-none"
              placeholder="Filter laws…" />
            <div className="flex flex-wrap gap-1 items-center">
              <button onClick={() => setViewTier(null)}
                className={cn("rounded px-2 py-0.5 text-[8px]", viewTier === null ? "bg-white/15 text-white/90" : "bg-white/5 text-white/40 hover:text-white/70")}>
                All
              </button>
              {(Object.entries(TIER_META) as [string, { label: string; color: string; range: string }][]).map(([t, m]) => (
                <button key={t} onClick={() => setViewTier(viewTier === Number(t) as Tier ? null : Number(t) as Tier)}
                  className="rounded px-2 py-0.5 text-[8px] transition-all"
                  style={{ background: viewTier === Number(t) ? `${m.color}33` : "rgba(255,255,255,0.04)", color: viewTier === Number(t) ? m.color : "rgba(255,255,255,0.4)", border: `1px solid ${viewTier === Number(t) ? m.color + "66" : "transparent"}` }}>
                  T{t}
                </button>
              ))}
              <label className="ml-1 flex items-center gap-1 text-[8px] text-white/40 cursor-pointer">
                <input type="checkbox" checked={onlyModified} onChange={e => setOnlyModified(e.target.checked)} className="accent-amber-400" />
                Modified only
              </label>
            </div>
          </div>

          {/* Principle list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {filtered.map(p => {
              const eff = effective[p.id];
              const isOver = overrides[p.id] !== undefined;
              const delta = eff - p.default;
              return (
                <div key={p.id}
                  className={cn("rounded-lg border p-2 transition-colors", isOver ? "border-amber-400/25 bg-amber-400/5" : "border-white/8 bg-black/20 hover:bg-black/30")}>
                  <div className="flex items-start gap-2">
                    <div style={{ width: 3, minHeight: 32, borderRadius: 2, background: TIER_META[p.tier]?.color, flexShrink: 0, marginTop: 2 }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-[10px] font-semibold text-white/85 truncate">{p.label}</span>
                        <span className="text-[8px] text-white/30">T{p.tier}</span>
                        {isOver && <span className={cn("text-[8px] font-mono shrink-0", delta > 0 ? "text-emerald-400" : "text-rose-400")}>{delta > 0 ? "+" : ""}{delta}</span>}
                      </div>
                      <div className="text-[8px] text-white/35 mb-1.5 line-clamp-1">{p.desc}</div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded-full bg-white/8 overflow-hidden">
                          <div style={{ width: `${eff}%`, height: "100%", background: scoreColor(eff), transition: "width 0.15s" }} />
                        </div>
                        <input type="number" min={0} max={100} value={eff}
                          onChange={e => setOverride(p.id, e.target.value)}
                          className="w-12 rounded border border-white/10 bg-black/40 px-1 py-0.5 text-center font-mono text-[10px] text-white/80 focus:outline-none focus:border-white/25" />
                        {isOver
                          ? <button onClick={() => resetOne(p.id)} className="text-[8px] text-white/25 hover:text-white/60 font-mono" title="Reset">↺{p.default}</button>
                          : <span className="text-[8px] text-white/20 font-mono w-8 text-right">{p.default}</span>
                        }
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  SYSTEM PROMPT BUILDER
// ═══════════════════════════════════════════════════════════════════════════

function buildConstitutionPrompt(nodes: Node<AppNodeData>[]): string {
  const scws = nodes.filter(n => n.data.kind === "scw") as Node<SCWData>[];
  const agents = nodes.filter(n => n.data.kind === "agent" || n.data.kind === "maxey00") as Node<AgentData>[];
  const lines = [
    "# Maxey0 Constitutional Universe Configuration",
    "",
    "Each SCW below defines an active law stack. Agents are stateful and inherit their parent universe's weights.",
    "Score ≥80 = dominant law. Score ≤20 = suspended. Unspecified = Claude default.",
    "",
  ];
  for (const n of scws) {
    const d = n.data;
    const eff = computeEffective(d.universeWeights ?? {});
    const arch = UNIVERSE_ARCHETYPES[d.archetype ?? "default"];
    lines.push(`## ${n.id} [${arch?.label} ${arch?.icon}]`);
    lines.push(`Overrides: ${Object.keys(d.universeWeights ?? {}).length} of 64 laws`);
    lines.push("");
    lines.push("### Dominant Laws (≥75):");
    const dominant = PRINCIPLE_REGISTRY.filter(p => eff[p.id] >= 75).sort((a, b) => eff[b.id] - eff[a.id]);
    for (const p of dominant) lines.push(`- [${eff[p.id]}/100] ${p.label}: ${p.desc.substring(0, 80)}`);
    lines.push("");
    lines.push("### Suspended Laws (≤20):");
    const suspended = PRINCIPLE_REGISTRY.filter(p => eff[p.id] <= 20);
    if (suspended.length) { for (const p of suspended) lines.push(`- [${eff[p.id]}/100] ${p.label} — SUSPENDED`); }
    else lines.push("(none)");
    lines.push("");
    const contained = agents.filter(a => a.data.scwId === n.id);
    if (contained.length) {
      lines.push(`### Stateful Agents: ${contained.map(a => a.id).join(", ")}`);
      lines.push("These agents carry this constitution. Responses must reflect the law weights above.");
    }
    lines.push("\n---\n");
  }
  return lines.join("\n");
}

// ═══════════════════════════════════════════════════════════════════════════
//  GRAPH HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function applyNodeChanges(prev: Node<AppNodeData>[], changes: { type: string; id: string; position?: { x: number; y: number }; selected?: boolean }[]): Node<AppNodeData>[] {
  let next = [...prev];
  for (const ch of changes) {
    if (ch.type === "remove")    { next = next.filter(n => n.id !== ch.id); continue; }
    if (ch.type === "position")  { next = next.map(n => n.id === ch.id ? { ...n, position: ch.position ?? n.position } : n); continue; }
    if (ch.type === "select")    { next = next.map(n => n.id === ch.id ? { ...n, selected: ch.selected } : n); continue; }
  }
  return next;
}

function applyEdgeChanges(prev: Edge<EdgeData>[], changes: { type: string; id: string; selected?: boolean }[]): Edge<EdgeData>[] {
  let next = [...prev];
  for (const ch of changes) {
    if (ch.type === "remove") { next = next.filter(e => e.id !== ch.id); continue; }
    if (ch.type === "select") { next = next.map(e => e.id === ch.id ? { ...e, selected: ch.selected } : e); continue; }
  }
  return next;
}

function useLs<T>(key: string, init: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => { try { const r = localStorage.getItem(key); return r ? JSON.parse(r) as T : init; } catch { return init; } });
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(v)); } catch {} }, [key, v]);
  return [v, setV];
}

// ═══════════════════════════════════════════════════════════════════════════
//  MAIN APP
// ═══════════════════════════════════════════════════════════════════════════

const counters: Record<string, number> = { SCW: 3, Maxey: 2, Tool: 1 };
const nextId = (prefix: string): string => { const n = counters[prefix] ?? 1; counters[prefix] = n + 1; return `${prefix}${n}`; };

const makeScw = (id: string, x: number, y: number, archetype: string, z: number): Node<AppNodeData> => {
  const arch = UNIVERSE_ARCHETYPES[archetype];
  const size: Size = { w: 540, h: 290 };
  return { id, type: "scw", position: { x, y }, data: { kind: "scw", label: id, runtime: "python", containedAgentIds: [], universeWeights: { ...(arch?.overrides ?? {}) }, archetype, size, z, props: {} }, style: { width: size.w, height: size.h, zIndex: z }, selected: false };
};

const makeAgent = (id: string, x: number, y: number, spec: string, mem: MemoryTier, scwId: string | undefined, z: number): Node<AppNodeData> => {
  const size: Size = { w: 280, h: 195 };
  return { id, type: scwId === "Maxey00" || id === "Maxey00" ? "maxey00" : "agent", position: { x, y }, data: { kind: id === "Maxey00" ? "maxey00" : "agent", label: id, specialization: spec, description: "", memoryTier: mem, scwId, attachedToolIds: [], size, z, props: {} }, style: { width: size.w, height: size.h, zIndex: z }, selected: false };
};

export default function App(): JSX.Element {
  const rfRef = useRef<ReactFlowInstance | null>(null);

  const [nodes, setNodes] = useState<Node<AppNodeData>[]>(() => [
    makeScw("SCW1", 60, 60, "long_session", 1),
    makeScw("SCW2", 660, 60, "scratchpad", 1),
    { ...makeAgent("Maxey00", 1260, 80, "Superposition / Global Observability", "persistent", undefined, 2), type: "maxey00", data: { ...makeAgent("Maxey00", 1260, 80, "Superposition", "persistent", undefined, 2).data, kind: "maxey00", universeWeights: { ...UNIVERSE_ARCHETYPES.superposition.overrides }, archetype: "superposition" } as AppNodeData },
    makeAgent("Maxey1", 120, 185, "Orchestrator (Planner/Router)", "episodic", "SCW1", 3),
  ]);

  const [edges, setEdges] = useState<Edge<EdgeData>[]>(() => {
    const { style, markerEnd } = edgeStyleForKind("observes");
    return [{ id: "e0", source: "Maxey00", target: "SCW1", type: "default", data: { kind: "observes", systemManaged: true }, label: "observes", style, markerEnd, selected: false }];
  });

  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [edgeKind, setEdgeKind] = useLs<EdgeKind>("m0.edgeKind", "workflow");
  const [universeEditorId, setUniverseEditorId] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportContent, setExportContent] = useState("");
  const [copied, setCopied] = useState(false);

  const nodesRef = useRef(nodes);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);

  const maxZ = useMemo(() => nodes.reduce((m, n) => Math.max(m, (n.data as BaseNodeData).z ?? 0), 0), [nodes]);

  const ctxVal = useMemo<DesignerCtx>(() => ({
    getNode: (id: string) => nodesRef.current.find(n => n.id === id),
    setNodes,
  }), []);

  const applySelection = useCallback((nids: string[]): void => {
    setSelectedNodeIds(nids);
    setNodes(prev => prev.map(n => ({ ...n, selected: nids.includes(n.id) })));
  }, []);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node): void => {
    const e = _ as unknown as React.MouseEvent;
    const multi = !!(e?.shiftKey || e?.metaKey || e?.ctrlKey);
    const next = !multi ? [node.id] : selectedNodeIds.includes(node.id) ? selectedNodeIds.filter(x => x !== node.id) : [...selectedNodeIds, node.id];
    applySelection(next);
  }, [applySelection, selectedNodeIds]);

  const onPaneClick = useCallback(() => applySelection([]), [applySelection]);

  const onConnect = useCallback((c: Connection): void => {
    const { style, markerEnd } = edgeStyleForKind(edgeKind);
    setEdges(prev => addEdge({ id: `e-${Date.now()}`, source: c.source ?? "", target: c.target ?? "", type: "default", data: { kind: edgeKind }, label: edgeKind, style, markerEnd, selected: false } as Edge<EdgeData>, prev));
  }, [edgeKind]);

  const onNodeDragStop = useCallback((_: unknown, node: Node<AppNodeData>): void => {
    const d = node.data as AppNodeData;
    if (d.kind !== "agent" && d.kind !== "maxey00") return;
    const snap = nodesRef.current;
    const aData = d as AgentData;
    const aSize = aData.size ?? { w: 280, h: 195 };
    const cx = node.position.x + aSize.w / 2, cy = node.position.y + aSize.h / 2;
    const hit = snap.filter(n => n.data.kind === "scw" && n.id !== node.id).find(n => {
      const nd = n.data as SCWData;
      const s = nd.size ?? { w: 540, h: 290 };
      return cx >= n.position.x + 12 && cx <= n.position.x + s.w - 12 && cy >= n.position.y + 12 && cy <= n.position.y + s.h - 12;
    });
    const oldScwId = aData.scwId;
    const newScwId = hit?.id;
    if (oldScwId === newScwId) return;
    setNodes(prev => prev.map(n => {
      if (n.id === node.id) return { ...n, data: { ...n.data, scwId: newScwId } as AppNodeData };
      if (n.data.kind === "scw") {
        const sd = n.data as SCWData;
        const agents = (sd.containedAgentIds ?? []).filter(x => x !== node.id);
        if (n.id === newScwId) return { ...n, data: { ...sd, containedAgentIds: [...agents, node.id] } };
        return { ...n, data: { ...sd, containedAgentIds: agents } };
      }
      return n;
    }));
  }, []);

  const spawnSCW = (): void => {
    const id = nextId("SCW"); const z = maxZ + 1;
    setNodes(prev => [...prev, makeScw(id, 200 + prev.length * 25, 100 + prev.length * 15, "default", z)]);
    applySelection([id]);
  };

  const spawnAgent = (): void => {
    const id = nextId("Maxey"); const z = maxZ + 1;
    setNodes(prev => [...prev, makeAgent(id, 420 + prev.length * 20, 340, "Unassigned", "episodic", undefined, z)]);
    applySelection([id]);
  };

  const spawnMaxey00 = (): void => {
    if (nodesRef.current.some(n => n.id === "Maxey00")) { applySelection(["Maxey00"]); return; }
    const z = maxZ + 1;
    setNodes(prev => [...prev, {
      ...makeAgent("Maxey00", 1200, 80, "Superposition", "persistent", undefined, z),
      type: "maxey00",
      data: { ...makeAgent("Maxey00", 1200, 80, "Superposition", "persistent", undefined, z).data, kind: "maxey00", universeWeights: { ...UNIVERSE_ARCHETYPES.superposition.overrides }, archetype: "superposition" } as AppNodeData,
    }]);
    applySelection(["Maxey00"]);
  };

  const onUpdateUniverse = useCallback((scwId: string, overrides: Record<string, number>, archetype: string): void => {
    setNodes(prev => prev.map(n => n.id !== scwId ? n : { ...n, data: { ...(n.data as SCWData), universeWeights: overrides, archetype } }));
  }, []);

  const handleExport = (): void => {
    setExportContent(buildConstitutionPrompt(nodesRef.current));
    setExportOpen(true);
  };

  const universeEditorNode = universeEditorId ? nodes.find(n => n.id === universeEditorId) ?? null : null;
  const selectedScwId = selectedNodeIds.find(id => nodesRef.current.find(n => n.id === id)?.data?.kind === "scw") ?? null;

  const infoPanel = useMemo(() => {
    if (selectedNodeIds.length !== 1) return null;
    const node = nodes.find(n => n.id === selectedNodeIds[0]);
    if (!node) return null;
    const d = node.data as AppNodeData;
    if (d.kind === "scw") {
      const sd = d as SCWData;
      const arch = UNIVERSE_ARCHETYPES[sd.archetype ?? "default"];
      const top = getTopPrinciples(sd.universeWeights ?? {}, 6);
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2"><span style={{ fontSize: 20 }}>{arch?.icon}</span><div><div className="text-sm font-bold text-white/90">{node.id}</div><div className="text-[10px] text-white/45">{arch?.label}</div></div></div>
          <div className="space-y-1.5">{top.map(({ id, score, p }) => (<div key={id} className="flex items-center gap-2 rounded-lg border border-white/8 bg-black/30 p-2"><div style={{ width: Math.round(score / 100 * 56), height: 4, background: scoreColor(score), borderRadius: 2 }} /><div className="flex-1 text-[9px] text-white/70 truncate">{p?.label}</div><span style={{ color: scoreColor(score) }} className="font-mono text-[9px] shrink-0">{score}</span></div>))}</div>
          <button onClick={() => setUniverseEditorId(node.id)} className="w-full rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 text-xs font-semibold text-violet-300 hover:bg-violet-500/20">⚖️ Edit Universe Constitution</button>
        </div>
      );
    }
    if (d.kind === "agent" || d.kind === "maxey00") {
      const ad = d as AgentData;
      const parentScw = ad.scwId ? (nodes.find(n => n.id === ad.scwId)?.data as SCWData | undefined) : undefined;
      const top = getTopPrinciples(parentScw?.universeWeights ?? {}, 5);
      const arch = parentScw ? UNIVERSE_ARCHETYPES[parentScw.archetype ?? "default"] : undefined;
      return (
        <div className="space-y-2">
          <div className="text-sm font-bold text-white/90">{node.id}</div>
          <div className="text-[10px] text-white/50">{ad.specialization} · {ad.memoryTier}</div>
          {parentScw ? (<div className="rounded-lg border border-violet-400/20 bg-violet-500/5 p-2"><div className="text-[9px] text-violet-300/60 mb-1.5">Stateful · Inheriting {ad.scwId} {arch?.icon}</div><div className="space-y-1">{top.map(({ id, score, p }) => (<div key={id} className="flex items-center gap-2"><div style={{ width: Math.round(score / 100 * 48), height: 3, background: scoreColor(score), borderRadius: 1 }} /><span className="text-[8px] text-white/50 truncate">{p?.label?.split(" ").slice(0, 3).join(" ")}</span><span style={{ color: scoreColor(score) }} className="font-mono text-[8px] ml-auto">{score}</span></div>))}</div></div>)
          : (<div className="text-[9px] text-white/30 italic">Drop into SCW to inherit universe</div>)}
        </div>
      );
    }
    return null;
  }, [selectedNodeIds, nodes]);

  return (
    <DesignerCtx.Provider value={ctxVal}>
      <div className="h-screen w-screen flex flex-col bg-[#070A0F] text-white overflow-hidden">
        {/* Topbar */}
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 bg-black/20 px-3 gap-3">
          <div className="flex items-center gap-3">
            <div className="text-sm font-semibold tracking-tight">Maxey0 ⚖️ Constitutional Universe Designer</div>
            <div className="hidden lg:block text-[10px] text-white/35">SCWs as Claude law universes · agents inherit constitutions · {PRINCIPLE_REGISTRY.length} core laws</div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={spawnSCW} className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-xs hover:bg-emerald-500/20 text-emerald-300">+ SCW Universe</button>
            <button onClick={spawnAgent} className="rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-1 text-xs hover:bg-violet-500/20 text-violet-300">+ Agent</button>
            <button onClick={spawnMaxey00} className="rounded-lg border border-sky-400/30 bg-sky-500/10 px-3 py-1 text-xs hover:bg-sky-500/20 text-sky-300">+ Maxey00</button>
            {selectedScwId && (
              <button onClick={() => setUniverseEditorId(selectedScwId)}
                className="rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/25">
                ⚖️ Edit Universe
              </button>
            )}
            <div className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2 py-1">
              <span className="text-[9px] text-white/40">Edge</span>
              <select className="bg-transparent text-xs text-white/75 focus:outline-none cursor-pointer" value={edgeKind} onChange={e => setEdgeKind(e.target.value as EdgeKind)}>
                {(["workflow","data_in","data_out","observes","controls","contains"] as EdgeKind[]).map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <button onClick={handleExport} className="rounded-lg border border-indigo-400/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-300 hover:bg-indigo-500/20">↓ Export Constitution</button>
          </div>
        </div>

        {/* Main */}
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* Left legend */}
          <div className="w-44 shrink-0 border-r border-white/10 bg-black/10 overflow-y-auto p-3 space-y-2">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-white/35 mb-3">Tier Legend</div>
            {(Object.entries(TIER_META) as [string, { label: string; color: string; range: string }][]).map(([t, m]) => (
              <div key={t} className="flex items-start gap-2">
                <div style={{ width: 3, height: 32, borderRadius: 2, background: m.color, flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div className="text-[8px] font-semibold" style={{ color: m.color }}>T{t} · {m.range}</div>
                  <div className="text-[8px] text-white/40 leading-tight">{m.label}</div>
                </div>
              </div>
            ))}
            <div className="border-t border-white/10 pt-3 space-y-1.5">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-white/35">Archetypes</div>
              {Object.entries(UNIVERSE_ARCHETYPES).map(([k, a]) => (
                <div key={k} className="flex items-center gap-1.5">
                  <span style={{ fontSize: 10 }}>{a.icon}</span>
                  <span className="text-[8px] text-white/55 truncate">{a.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Canvas */}
          <div className="relative flex-1 min-w-0">
            <ReactFlow
              nodes={nodes} edges={edges}
              onInit={inst => { rfRef.current = inst; }}
              onNodesChange={chs => setNodes(prev => applyNodeChanges(prev, chs as Parameters<typeof applyNodeChanges>[1]))}
              onEdgesChange={chs => setEdges(prev => applyEdgeChanges(prev, chs as Parameters<typeof applyEdgeChanges>[1]))}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onNodeDragStop={onNodeDragStop}
              onEdgeClick={(_, e) => { setEdges(prev => prev.map(x => ({ ...x, selected: x.id === e.id }))); }}
              onPaneClick={onPaneClick}
              nodeTypes={nodeTypes}
              fitView elevateEdgesOnSelect elevateNodesOnSelect>
              <Background gap={22} color="rgba(255,255,255,0.05)" />
              <Controls className="rounded-xl border border-white/10 bg-black/30" />
            </ReactFlow>

            {/* Info overlay */}
            {infoPanel && (
              <div className="absolute top-3 left-3 z-[9999] w-72 rounded-2xl border border-white/10 bg-[#0B0F16]/95 p-4 shadow-2xl backdrop-blur-sm">
                {infoPanel}
              </div>
            )}
          </div>

          {/* Right sidebar */}
          <div className="w-60 shrink-0 border-l border-white/10 bg-black/10 overflow-y-auto p-3 space-y-3">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-white/35">SCW Universes</div>
            {(nodes.filter(n => n.data.kind === "scw") as Node<SCWData>[]).map(n => {
              const d = n.data;
              const arch = UNIVERSE_ARCHETYPES[d.archetype ?? "default"];
              const top = getTopPrinciples(d.universeWeights ?? {}, 3);
              return (
                <div key={n.id}
                  className={cn("rounded-xl border p-3 cursor-pointer transition-colors", selectedNodeIds.includes(n.id) ? "border-white/25 bg-white/8" : "border-white/8 bg-black/20 hover:bg-black/30")}
                  onClick={() => applySelection([n.id])}>
                  <div className="flex items-center gap-2 mb-2">
                    <span style={{ fontSize: 13 }}>{arch?.icon}</span>
                    <div className="min-w-0"><div className="text-xs font-semibold text-white/90 truncate">{n.id}</div><div className="text-[8px] text-white/40">{Object.keys(d.universeWeights ?? {}).length} overrides</div></div>
                  </div>
                  <div className="space-y-1 mb-2">
                    {top.map(({ id, score, p }) => (
                      <div key={id} className="flex items-center gap-1.5">
                        <div style={{ width: Math.round(score / 100 * 44), height: 3, background: scoreColor(score), borderRadius: 1 }} />
                        <span className="text-[8px] text-white/45 truncate">{p?.label?.split(" ").slice(0, 2).join(" ")}</span>
                        <span style={{ color: scoreColor(score) }} className="font-mono text-[8px] ml-auto">{score}</span>
                      </div>
                    ))}
                  </div>
                  <button onClick={e => { e.stopPropagation(); setUniverseEditorId(n.id); }}
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-[8px] text-white/50 hover:bg-white/10">
                    ⚖️ Edit Laws
                  </button>
                </div>
              );
            })}

            <div className="border-t border-white/10 pt-3">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-white/35 mb-2">Stateful Agents</div>
              {(nodes.filter(n => n.data.kind === "agent" || n.data.kind === "maxey00") as Node<AgentData>[]).map(n => {
                const d = n.data;
                const parentScw = d.scwId ? (nodes.find(x => x.id === d.scwId)?.data as SCWData | undefined) : undefined;
                const arch = parentScw ? UNIVERSE_ARCHETYPES[parentScw.archetype ?? "default"] : undefined;
                return (
                  <div key={n.id}
                    className={cn("rounded-lg border px-2 py-1.5 mb-1.5 cursor-pointer transition-colors", selectedNodeIds.includes(n.id) ? "border-white/20 bg-white/8" : "border-white/8 bg-black/20 hover:bg-white/5")}
                    onClick={() => applySelection([n.id])}>
                    <div className="text-[10px] font-medium text-white/80">{n.id}</div>
                    {parentScw
                      ? <div className="text-[8px] text-white/35">{arch?.icon} inherits {d.scwId}</div>
                      : <div className="text-[8px] text-white/20 italic">no universe</div>
                    }
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Universe Editor */}
        {universeEditorNode && (
          <UniverseEditorPanel
            scwNode={universeEditorNode}
            onClose={() => setUniverseEditorId(null)}
            onUpdate={onUpdateUniverse}
          />
        )}

        {/* Export Modal */}
        {exportOpen && (
          <div className="fixed inset-0 z-[999999] flex items-center justify-center" style={{ background: "rgba(0,0,0,0.75)" }}>
            <div className="flex flex-col rounded-2xl border border-white/12 bg-[#07090f] shadow-2xl" style={{ width: 740, height: "78vh" }}>
              <div className="flex h-12 shrink-0 items-center gap-3 border-b border-white/10 px-4">
                <div className="flex-1 text-sm font-semibold text-white/90">Universe Constitution Export</div>
                <button onClick={() => { navigator.clipboard.writeText(exportContent).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }); }}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-1 text-xs hover:bg-white/10">
                  {copied ? "✓ Copied" : "Copy"}
                </button>
                <button onClick={() => { const b = new Blob([exportContent], { type: "text/plain" }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "maxey0-constitution.md"; a.click(); URL.revokeObjectURL(a.href); }}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-1 text-xs hover:bg-white/10">
                  ↓ .md
                </button>
                <button onClick={() => setExportOpen(false)} className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/50">✕</button>
              </div>
              <textarea readOnly className="flex-1 resize-none rounded-b-2xl bg-black/40 p-4 font-mono text-[11px] text-white/75 focus:outline-none" value={exportContent} />
            </div>
          </div>
        )}
      </div>
    </DesignerCtx.Provider>
  );
}
