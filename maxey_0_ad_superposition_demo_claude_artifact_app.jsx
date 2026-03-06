import React, { useMemo, useState, useEffect } from "react";
import { create } from "zustand";
import { v4 as uuidv4 } from "uuid";
import { motion } from "framer-motion";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Save, Rocket, Eye, Gauge, Database, Target, Layers, DollarSign, Calendar, LayoutDashboard, UploadCloud, Box, GitBranchPlus } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

// ------------------------------------------------------------
// MOCK DATA + HELPERS (No pseudocode — executable TS/React)
// ------------------------------------------------------------

// Generate ~750+ mock Maxey agents (industry / channel anchors)
const INDUSTRIES = [
  "Automotive","Beauty","B2B SaaS","Consumer Apps","CPG","Education","Entertainment","Financial Services","Gaming","Healthcare","Hospitality","Home Services","Industrial","Legal","Logistics","Media","Nonprofit","Real Estate","Retail","Sports","Travel","Telecom","Energy","Insurance","Government","Agriculture","Aerospace","Fashion","Food & Beverage","Pharma",
];

const CHANNELS = [
  "Search","Social","Display","Video","Audio","Email","Affiliate","Influencer","In‑App","Out‑of‑Home","AR/VR",
];

const makeAgents = (count = 780) => {
  const agents: { id: string; name: string; kind: string; industry: string; channel: string }[] = [];
  for (let i = 0; i < count; i++) {
    const industry = INDUSTRIES[i % INDUSTRIES.length];
    const channel = CHANNELS[i % CHANNELS.length];
    agents.push({
      id: `Maxey${i + 1}`,
      name: `Maxey Agent ${i + 1}`,
      kind: i % 7 === 0 ? "Planner" : i % 11 === 0 ? "Creative" : "Channel",
      industry,
      channel,
    });
  }
  return agents;
};

const ALL_AGENTS = makeAgents(780);

// Memory tiers (buckets)
export type MemoryTier = "Scratchpad (L1)" | "Episodic (L2)" | "Persistent (L3)" | "Permanent (L4)";

const MEMORY_TIERS: { id: MemoryTier; description: string }[] = [
  {
    id: "Scratchpad (L1)",
    description:
      "Ultra-short lived working memory used for immediate ad attention boosts, micro-bursts, and exploration taps.",
  },
  {
    id: "Episodic (L2)",
    description:
      "Per-session memory: campaign windows, sponsored SCWs, thread-scoped ad recall, and session-bound targeting.",
  },
  {
    id: "Persistent (L3)",
    description:
      "Long-lived memory: brand anchors, industry affinities, frequency pacing, and optimization priors across sessions.",
  },
  {
    id: "Permanent (L4)",
    description:
      "Immutable model prior hooks (rare): reserved for system policies and safety constraints; ads normally avoid L4.",
  },
];

// Map duration to memory bucket recommendation
const bucketForDuration = (days: number): MemoryTier => {
  if (days <= 2) return "Scratchpad (L1)";
  if (days <= 30) return "Episodic (L2)";
  if (days <= 365) return "Persistent (L3)";
  return "Permanent (L4)"; // discouraged for ads, but shown for completeness
};

// Simulate attention allocation spectrum from budget
const attentionSpectrum = (budgetK: number) => {
  // Normalize into a 0..1 magnitude and propose a spectrum across tiers
  const mag = Math.min(1, Math.max(0, budgetK / 100)); // 100k caps demo
  return [
    { tier: "L1", mag: Math.min(1, 0.4 + mag * 0.3) },
    { tier: "L2", mag: Math.min(1, 0.35 + mag * 0.45) },
    { tier: "L3", mag: Math.min(1, 0.2 + mag * 0.55) },
  ];
};

// ------------------------------------------------------------
// GLOBAL STORE (syncs across all pages/tabs)
// ------------------------------------------------------------

type Segment = { id: string; label: string; type: "industry" | "channel" | "agent" };

type Campaign = {
  id: string;
  name: string;
  advertiser: string;
  durationDays: number;
  budgetK: number; // thousands USD
  bucket: MemoryTier;
  segments: Segment[];
  targets: string[]; // persona / task / agent ids / latent tags
  scwSponsored: boolean;
  scwName?: string;
  notes?: string;
};

type Store = {
  campaign: Campaign;
  set<K extends keyof Campaign>(key: K, value: Campaign[K]): void;
  addSegment: (s: Segment) => void;
  removeSegment: (id: string) => void;
  addTarget: (t: string) => void;
  removeTarget: (t: string) => void;
  reset: () => void;
};

const useCampaign = create<Store>((set, get) => ({
  campaign: {
    id: uuidv4(),
    name: "Untitled Superposition Ad Campaign",
    advertiser: "",
    durationDays: 14,
    budgetK: 25,
    bucket: bucketForDuration(14),
    segments: [],
    targets: [],
    scwSponsored: false,
    scwName: "",
    notes: "",
  },
  set: (key, value) => set((s) => ({ campaign: { ...s.campaign, [key]: value } })),
  addSegment: (seg) => set((s) => ({
    campaign: {
      ...s.campaign,
      segments: s.campaign.segments.find((x) => x.id === seg.id) ? s.campaign.segments : [...s.campaign.segments, seg],
    },
  })),
  removeSegment: (id) => set((s) => ({
    campaign: { ...s.campaign, segments: s.campaign.segments.filter((x) => x.id !== id) },
  })),
  addTarget: (t) => set((s) => ({
    campaign: { ...s.campaign, targets: s.campaign.targets.includes(t) ? s.campaign.targets : [...s.campaign.targets, t] },
  })),
  removeTarget: (t) => set((s) => ({
    campaign: { ...s.campaign, targets: s.campaign.targets.filter((x) => x !== t) },
  })),
  reset: () => set({
    campaign: {
      id: uuidv4(),
      name: "Untitled Superposition Ad Campaign",
      advertiser: "",
      durationDays: 14,
      budgetK: 25,
      bucket: bucketForDuration(14),
      segments: [],
      targets: [],
      scwSponsored: false,
      scwName: "",
      notes: "",
    },
  }),
}));

// ------------------------------------------------------------
// UI SUBCOMPONENTS
// ------------------------------------------------------------

const MemoryBucketCard: React.FC<{ tier: MemoryTier; active?: boolean; description: string }> = ({ tier, active, description }) => (
  <Card className={`transition-all ${active ? "ring-2 ring-primary shadow-lg" : "opacity-80"}`}>
    <CardHeader>
      <CardTitle className="flex items-center gap-2 text-lg">
        <Database className="h-5 w-5" /> {tier}
      </CardTitle>
      <CardDescription>{description}</CardDescription>
    </CardHeader>
  </Card>
);

const BudgetAttentionChart: React.FC<{ budgetK: number }> = ({ budgetK }) => {
  const data = useMemo(() => attentionSpectrum(budgetK).map((d) => ({ bucket: d.tier, attention: Math.round(d.mag * 100) })), [budgetK]);
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <BarChart data={data}>
          <XAxis dataKey="bucket" />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Bar dataKey="attention" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

const IndustryChannelPicker: React.FC = () => {
  const { addSegment, removeSegment, campaign } = useCampaign();
  const [mode, setMode] = useState<"industry" | "channel" | "agent">("industry");
  const [search, setSearch] = useState("");

  const options = useMemo(() => {
    if (mode === "industry") return Array.from(new Set(ALL_AGENTS.map((a) => a.industry)));
    if (mode === "channel") return Array.from(new Set(ALL_AGENTS.map((a) => a.channel)));
    return ALL_AGENTS.map((a) => a.id);
  }, [mode]);

  const filtered = useMemo(() => options.filter((o) => o.toLowerCase().includes(search.toLowerCase())).slice(0, 50), [options, search]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Layers className="h-5 w-5"/> Segmentation</CardTitle>
        <CardDescription>Select industries, channels, or specific Maxey agents (750+ lattice) to bias ad delivery.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Label className="min-w-24">Mode</Label>
          <Select value={mode} onValueChange={(v: any) => setMode(v)}>
            <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="industry">Industry</SelectItem>
              <SelectItem value="channel">Channel</SelectItem>
              <SelectItem value="agent">Agent (ID)</SelectItem>
            </SelectContent>
          </Select>
          <Input placeholder={`Search ${mode}…`} value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-sm"/>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-64 overflow-auto rounded-lg border p-2">
          {filtered.map((opt) => (
            <button
              key={opt}
              onClick={() =>
                addSegment({ id: `${mode}:${opt}`, label: opt, type: mode })
              }
              className="text-left rounded-xl border px-3 py-2 hover:bg-muted transition"
            >
              {opt}
            </button>
          ))}
        </div>
        <Separator />
        <div className="space-y-2">
          <Label>Selected segments</Label>
          <div className="flex flex-wrap gap-2">
            {campaign.segments.map((s) => (
              <Badge key={s.id} variant="secondary" className="text-sm">
                {s.type}:{" "}{s.label}
                <button className="ml-2 opacity-70 hover:opacity-100" onClick={() => removeSegment(s.id)}>✕</button>
              </Badge>
            ))}
            {campaign.segments.length === 0 && (
              <div className="text-sm text-muted-foreground">No segments chosen yet.</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

const TargetingBuilder: React.FC = () => {
  const { campaign, addTarget, removeTarget } = useCampaign();
  const [value, setValue] = useState("");
  const presets = ["persona:researcher","persona:developer","task:pricing","task:integration","latent:observability","latent:superposition","agent:Maxey42","region:legal"];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Target className="h-5 w-5"/> Targeting</CardTitle>
        <CardDescription>Attach latent-space targets that activate once a user navigates into matching regions via queries, variables, or agent flows.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Input placeholder="Add target token (e.g., persona:analyst, latent:finance)" value={value} onChange={(e) => setValue(e.target.value)} />
          <Button onClick={() => { if (value.trim()) { addTarget(value.trim()); setValue(""); } }}>Add</Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {presets.map((t) => (
            <Button key={t} variant="outline" size="sm" onClick={() => addTarget(t)}>{t}</Button>
          ))}
        </div>
        <Separator />
        <div className="flex flex-wrap gap-2">
          {campaign.targets.map((t) => (
            <Badge key={t} className="text-sm" variant="secondary">
              {t}
              <button className="ml-2 opacity-70 hover:opacity-100" onClick={() => removeTarget(t)}>✕</button>
            </Badge>
          ))}
          {campaign.targets.length === 0 && <div className="text-sm text-muted-foreground">No targets yet.</div>}
        </div>
      </CardContent>
    </Card>
  );
};

const SCWSponsorship: React.FC = () => {
  const { campaign, set } = useCampaign();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><LayoutDashboard className="h-5 w-5"/> Sponsored Structured Context Window (SCW)</CardTitle>
        <CardDescription>Optional: create a named SCW for this session/thread. Think *“segment brought to you by &lt;Advertiser&gt;”*.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch
            checked={campaign.scwSponsored}
            onCheckedChange={(v) => set("scwSponsored", v)}
          />
          <Label>Sponsor a SCW for this campaign</Label>
        </div>
        {campaign.scwSponsored && (
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <Label>SCW Name</Label>
              <Input value={campaign.scwName}
                onChange={(e) => set("scwName", e.target.value)}
                placeholder="e.g., Observatory • Sponsored by Acme" />
            </div>
            <div>
              <Label>Notes / Disclosure</Label>
              <Textarea value={campaign.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Disclosure text, brand safety tags, creative guidance…"/>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ------------------------------------------------------------
// MAIN PAGES
// ------------------------------------------------------------

const Overview: React.FC = () => {
  const { campaign, set } = useCampaign();
  const bucket = useMemo(() => bucketForDuration(campaign.durationDays), [campaign.durationDays]);
  useEffect(() => set("bucket", bucket), [bucket, set]);

  return (
    <div className="grid xl:grid-cols-3 gap-6">
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Gauge className="h-5 w-5"/> Campaign Controls</CardTitle>
          <CardDescription>Set core parameters: duration (maps to memory tier), budget (attention magnitude), and metadata.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <Label className="flex items-center gap-2"><Calendar className="h-4 w-4"/> Duration (days)</Label>
              <div className="flex items-center gap-3">
                <Slider value={[campaign.durationDays]} min={1} max={400} step={1}
                        onValueChange={([v]) => set("durationDays", v)} className="w-full"/>
                <Input type="number" value={campaign.durationDays} onChange={(e) => set("durationDays", Number(e.target.value||1))} className="w-24"/>
              </div>
            </div>
            <div className="space-y-3">
              <Label className="flex items-center gap-2"><DollarSign className="h-4 w-4"/> Budget (thousands USD)</Label>
              <div className="flex items-center gap-3">
                <Slider value={[campaign.budgetK]} min={1} max={200} step={1}
                        onValueChange={([v]) => set("budgetK", v)} className="w-full"/>
                <Input type="number" value={campaign.budgetK} onChange={(e) => set("budgetK", Number(e.target.value||1))} className="w-24"/>
              </div>
            </div>
            <div className="space-y-3">
              <Label>Campaign Name</Label>
              <Input value={campaign.name} onChange={(e) => set("name", e.target.value)} placeholder="Q4 Launch – Superposition Reach"/>
            </div>
            <div className="space-y-3">
              <Label>Advertiser</Label>
              <Input value={campaign.advertiser} onChange={(e) => set("advertiser", e.target.value)} placeholder="Acme Co."/>
            </div>
          </div>
          <Separator />
          <div className="grid md:grid-cols-3 gap-4">
            {MEMORY_TIERS.map((t) => (
              <MemoryBucketCard key={t.id} tier={t.id} description={t.description} active={t.id === campaign.bucket} />
            ))}
          </div>
          <Separator />
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Eye className="h-5 w-5"/> Attention Spectrum</CardTitle>
                <CardDescription>Budget drives embedded attention weights across memory tiers.</CardDescription>
              </CardHeader>
              <CardContent>
                <BudgetAttentionChart budgetK={campaign.budgetK} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Box className="h-5 w-5"/> Current Plan Snapshot</CardTitle>
                <CardDescription>Derived storage + delivery plan for Maxey0 latent injection.</CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-muted rounded-xl p-3 overflow-auto">
{JSON.stringify({
  id: campaign.id,
  name: campaign.name,
  advertiser: campaign.advertiser,
  durationDays: campaign.durationDays,
  bucket: campaign.bucket,
  budgetK: campaign.budgetK,
  attention: attentionSpectrum(campaign.budgetK),
}, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>
      <div className="space-y-6">
        <IndustryChannelPicker />
        <SCWSponsorship />
      </div>
    </div>
  );
};

const Targeting: React.FC = () => (
  <div className="grid lg:grid-cols-3 gap-6">
    <div className="lg:col-span-2">
      <TargetingBuilder />
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><GitBranchPlus className="h-5 w-5"/> Latent Region Guide</CardTitle>
        <CardDescription>Reference of common latent tags aligning to Maxey agents.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div>• <b>latent:superposition</b> → Maxey00/Maxey0 root-pair observer regions.</div>
        <div>• <b>latent:observability</b> → monitoring, triangulation, LDF axes, auditing zones.</div>
        <div>• <b>persona:developer</b> → tool-use, code, integration anchors across 750+ agents.</div>
        <div>• <b>persona:researcher</b> → retrieval/analysis clusters, hypothesis scaffolds.</div>
        <div>• <b>task:pricing</b> → finance, forecasting, procurement subgraphs.</div>
      </CardContent>
    </Card>
  </div>
);

const PreviewAndLaunch: React.FC = () => {
  const { campaign, reset } = useCampaign();
  const [submitting, setSubmitting] = useState(false);

  const payload = useMemo(() => ({
    campaign,
    plan: {
      tier: campaign.bucket,
      attention: attentionSpectrum(campaign.budgetK),
      segments: campaign.segments,
      targets: campaign.targets,
      scw: campaign.scwSponsored ? { name: campaign.scwName, notes: campaign.notes } : null,
    },
  }), [campaign]);

  const simulateCommit = async () => {
    setSubmitting(true);
    // Simulate MCP client/server call into Maxey0 (demo only)
    await new Promise((r) => setTimeout(r, 900));
    setSubmitting(false);
    toast.success("Committed plan to Maxey0 latent space (demo)");
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><UploadCloud className="h-5 w-5"/> Plan Preview (JSON)</CardTitle>
          <CardDescription>What will be sent to Maxey0 MCP for latent memory injection and attention scheduling.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="text-xs bg-muted rounded-xl p-3 overflow-auto">
{JSON.stringify(payload, null, 2)}
          </pre>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Rocket className="h-5 w-5"/> Simulated Outcomes</CardTitle>
          <CardDescription>Projected allocation across agent lattice & memory tiers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <Label>Memory Tier Allocation</Label>
            <BudgetAttentionChart budgetK={campaign.budgetK} />
          </div>
          <div>
            <Label>Nearest Industry Anchors (by selection)</Label>
            <div className="flex flex-wrap gap-2">
              {campaign.segments.filter(s=>s.type!=="agent").slice(0,8).map((s) => (
                <Badge key={s.id} variant="outline">{s.label}</Badge>
              ))}
              {campaign.segments.filter(s=>s.type!=="agent").length===0 && (
                <div className="text-sm text-muted-foreground">No segments selected</div>
              )}
            </div>
          </div>
          <div>
            <Label>Activated Targets</Label>
            <div className="flex flex-wrap gap-2">
              {campaign.targets.slice(0,12).map((t) => (
                <Badge key={t} variant="secondary">{t}</Badge>
              ))}
              {campaign.targets.length===0 && <div className="text-sm text-muted-foreground">No targets</div>}
            </div>
          </div>
          <div className="flex gap-3">
            <Button disabled={submitting} onClick={simulateCommit}>
              <Save className="h-4 w-4 mr-2"/>{submitting?"Committing…":"Commit to Maxey0"}
            </Button>
            <Button variant="outline" onClick={reset}>Reset</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ------------------------------------------------------------
// ROOT APP
// ------------------------------------------------------------

export default function AdvertiserSuperpositionDemo() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="p-6 md:p-10 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight flex items-center gap-3">
            <LayoutDashboard className="h-7 w-7"/> Maxey0 • Ad Superposition Demo
          </h1>
          <p className="text-muted-foreground max-w-3xl mt-1">
            A Claude Artifact app that lets advertisers inject memories into Maxey0’s latent space to generate product-aligned ads.
            Configure duration, budget→attention, segmentation across 750+ Maxey agents (industry/channel anchors), targeting triggers,
            and optional sponsored SCWs. Everything syncs live across tabs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge>Root Pair: Maxey0 ↔ Maxey00</Badge>
          <Badge variant="outline">Agents: 750+</Badge>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-3 w-full md:w-auto">
          <TabsTrigger value="overview" className="flex items-center gap-2"><LayoutDashboard className="h-4 w-4"/> Overview</TabsTrigger>
          <TabsTrigger value="targeting" className="flex items-center gap-2"><Target className="h-4 w-4"/> Targeting</TabsTrigger>
          <TabsTrigger value="launch" className="flex items-center gap-2"><Rocket className="h-4 w-4"/> Preview & Launch</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-6">
          <Overview />
        </TabsContent>
        <TabsContent value="targeting" className="mt-6">
          <Targeting />
        </TabsContent>
        <TabsContent value="launch" className="mt-6">
          <PreviewAndLaunch />
        </TabsContent>
      </Tabs>

      <footer className="pt-4 text-xs text-muted-foreground">
        Built for demo parity with Google Ads primitives: campaigns, budgets, segments, targets, placements (SCW). This demo maps
        to Maxey0 memory tiers (L1–L4) and uses attention spectra to schedule latent injections.
      </footer>
    </motion.div>
  );
}
