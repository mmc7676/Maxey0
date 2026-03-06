import React, { useMemo, useState, useEffect, useCallback, createContext, useContext, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Save, Rocket, Eye, Gauge, Database, Target, Layers, DollarSign, Calendar, LayoutDashboard, UploadCloud, Box, GitBranchPlus, AlertTriangle, CheckCircle, MessageSquare, Play, ChevronRight, ChevronLeft, Map, Zap, Code, FileText, Settings, Activity, Cpu, Network, Globe, Crosshair, Brain } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, ScatterChart, Scatter, Area, AreaChart } from "recharts";

// ============================================================================
// TYPES AND INTERFACES
// ============================================================================

type MemoryTier = "Scratchpad (L1)" | "Episodic (L2)" | "Persistent (L3)" | "Permanent (L4)";
type SegmentType = "industry" | "channel" | "agent";
type TaskType = "converter" | "analyzer" | "builder" | "processor" | "generator" | "optimizer";
type RegionCode = "NA" | "EU" | "APAC" | "LATAM" | "MENA" | "AFRICA";

interface Segment {
  readonly id: string;
  readonly label: string;
  readonly type: SegmentType;
}

interface Target {
  readonly token: string;
}

interface SCWConfig {
  readonly name: string;
  readonly notes: string;
}

interface Campaign {
  readonly id: string;
  name: string;
  advertiser: string;
  durationDays: number;
  budgetK: number;
  bucket: MemoryTier;
  segments: readonly Segment[];
  targets: readonly Target[];
  scwSponsored: boolean;
  scwConfig?: SCWConfig;
  regions: readonly RegionCode[];
}

interface AttentionSpectrum {
  readonly tier: string;
  readonly attention: number;
}

interface AppBuildingStep {
  id: number;
  title: string;
  description: string;
  agents: string[];
  asciiArt: string;
  completed: boolean;
  taskType: TaskType;
  complexity: number;
}

interface UserPreferences {
  advertisementsEnabled: boolean;
  maxAdsPerSession: number;
}

interface MaxeyAgent {
  id: string;
  name: string;
  specialty: string;
  position: { x: number; y: number; z: number };
  relevanceScore: number;
  status: "active" | "idle" | "busy";
  memoryTier: MemoryTier;
}

interface LatentSpaceNode {
  id: string;
  x: number;
  y: number;
  z: number;
  label: string;
  type: "campaign" | "user" | "agent" | "superposition";
  intensity: number;
  connections: string[];
  data?: any;
}

interface RegionalTargeting {
  region: RegionCode;
  budget: number;
  reach: number;
  cpm: number;
  relevance: number;
  demographics: {
    age: string;
    interests: string[];
    behaviors: string[];
  };
}

// ============================================================================
// CONSTANTS AND DATA
// ============================================================================

const INDUSTRIES = [
  "Automotive", "Beauty", "B2B SaaS", "Consumer Apps", "CPG", "Education", 
  "Entertainment", "Financial Services", "Gaming", "Healthcare", "Hospitality", 
  "Home Services", "Industrial", "Legal", "Logistics", "Media", "Nonprofit", 
  "Real Estate", "Retail", "Sports", "Travel", "Telecom", "Energy", "Insurance", 
  "Government", "Agriculture", "Aerospace", "Fashion", "Food & Beverage", "Pharma"
];

const CHANNELS = [
  "Search", "Social", "Display", "Video", "Audio", "Email", "Affiliate", 
  "Influencer", "In-App", "Out-of-Home", "AR/VR"
];

const REGIONS: { code: RegionCode; name: string; color: string }[] = [
  { code: "NA", name: "North America", color: "#3b82f6" },
  { code: "EU", name: "Europe", color: "#10b981" },
  { code: "APAC", name: "Asia Pacific", color: "#f59e0b" },
  { code: "LATAM", name: "Latin America", color: "#ef4444" },
  { code: "MENA", name: "Middle East & North Africa", color: "#8b5cf6" },
  { code: "AFRICA", name: "Sub-Saharan Africa", color: "#ec4899" }
];

const MEMORY_TIERS = [
  { 
    id: "Scratchpad (L1)" as MemoryTier, 
    description: "Ultra-short lived working memory for immediate ad attention boosts and micro-bursts.",
    color: "#ef4444"
  },
  { 
    id: "Episodic (L2)" as MemoryTier, 
    description: "Per-session memory for campaign windows and thread-scoped ad recall.",
    color: "#f97316"
  },
  { 
    id: "Persistent (L3)" as MemoryTier, 
    description: "Long-lived memory for brand anchors and cross-session optimization.",
    color: "#22c55e"
  },
  { 
    id: "Permanent (L4)" as MemoryTier, 
    description: "Immutable storage reserved for system policies (discouraged for ads).",
    color: "#6b7280"
  },
];

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const sanitizeText = (input: string, maxLength: number = 200): string => {
  return input
    .trim()
    .slice(0, maxLength)
    .replace(/[\x00-\x1F\x7F]/g, '');
};

const computeAttentionSpectrum = (budgetK: number): readonly AttentionSpectrum[] => {
  const normalizedBudget = Math.min(1, Math.max(0, budgetK / 100));
  return [
    { tier: "L1", attention: Math.round((Math.min(1, 0.4 + normalizedBudget * 0.3)) * 100) },
    { tier: "L2", attention: Math.round((Math.min(1, 0.35 + normalizedBudget * 0.45)) * 100) },
    { tier: "L3", attention: Math.round((Math.min(1, 0.2 + normalizedBudget * 0.55)) * 100) },
  ] as const;
};

const bucketForDuration = (days: number): MemoryTier => {
  if (days <= 2) return "Scratchpad (L1)";
  if (days <= 30) return "Episodic (L2)";
  if (days <= 365) return "Persistent (L3)";
  return "Permanent (L4)";
};

const validateCampaignCompliance = (campaign: Campaign) => {
  const warnings: string[] = [];
  
  if (campaign.bucket === "Permanent (L4)") {
    warnings.push("Permanent tier (L4) is not recommended for advertising campaigns.");
  }
  
  if (campaign.budgetK > 100) {
    warnings.push("High budget allocations require additional compliance review.");
  }
  
  if (campaign.regions.length === 0) {
    warnings.push("At least one target region must be selected.");
  }
  
  return { isValid: warnings.length === 0, warnings };
};

const createInitialCampaign = (): Campaign => ({
  id: crypto.randomUUID(),
  name: "Untitled Superposition Ad Campaign",
  advertiser: "",
  durationDays: 14,
  budgetK: 25,
  bucket: "Episodic (L2)",
  segments: [],
  targets: [],
  scwSponsored: false,
  regions: ["NA"]
});

const parseTargetToken = (token: string): Target | null => {
  const validPrefixes = ['persona:', 'task:', 'latent:', 'agent:', 'region:'];
  const isValid = validPrefixes.some(prefix => token.startsWith(prefix)) && token.length > token.indexOf(':') + 1;
  
  if (!isValid) return null;
  
  return { token: sanitizeText(token, 50) };
};

const detectTaskType = (prompt: string): TaskType => {
  const lowerPrompt = prompt.toLowerCase();
  
  if (lowerPrompt.includes("convert") || lowerPrompt.includes("transform")) return "converter";
  if (lowerPrompt.includes("analyze") || lowerPrompt.includes("report")) return "analyzer";
  if (lowerPrompt.includes("build") || lowerPrompt.includes("create")) return "builder";
  if (lowerPrompt.includes("process") || lowerPrompt.includes("handle")) return "processor";
  if (lowerPrompt.includes("generate") || lowerPrompt.includes("produce")) return "generator";
  if (lowerPrompt.includes("optimize") || lowerPrompt.includes("improve")) return "optimizer";
  
  return "builder";
};

const generateDynamicASCII = (taskType: TaskType, stepIndex: number, prompt: string): string => {
  const patterns = {
    converter: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   ${prompt.split(' ')[0]?.toUpperCase().padEnd(13)} │───▶│  TRANSFORM ENG  │───▶│   ${prompt.split(' ').pop()?.toUpperCase().padEnd(13)} │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   DATA INGESTION  ║───▶║  SCHEMA MAPPING   ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │  OUTPUT BUILDER   │───▶│ QUALITY CONTROL │
    │                   │    │                 │
    └─────────────────┘    └─────────────────┘`
    ],
    analyzer: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   DATA SOURCE   │───▶│  ANALYSIS ENG   │───▶│    INSIGHTS     │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   FEATURE EXTRACT ║───▶║  PATTERN DETECT   ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │   VISUALIZATION   │───▶│   REPORT GEN    │
    │                   │    │                 │
    └─────────────────┘    └─────────────────┘`
    ],
    builder: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  REQUIREMENTS   │───▶│   ARCHITECTURE  │───▶│  IMPLEMENTATION │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   COMPONENT DES   ║───▶║   INTEGRATION     ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │     TESTING     │───▶│    DEPLOYMENT   │
    │                 │    │                 │
    └─────────────────┘    └─────────────────┘`
    ],
    processor: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   INPUT STREAM  │───▶│  PROCESSING     │───▶│  OUTPUT STREAM  │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   VALIDATION      ║───▶║   TRANSFORMATION  ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │   OPTIMIZATION  │───▶│     DELIVERY    │
    │                 │    │                 │
    └─────────────────┘    └─────────────────┘`
    ],
    generator: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   SEED INPUT    │───▶│  GENERATION     │───▶│   OUTPUT DATA   │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   TEMPLATE SYS    ║───▶║   CONTENT CREATE  ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │   REFINEMENT    │───▶│   FINALIZATION  │
    │                 │    │                 │
    └─────────────────┘    └─────────────────┘`
    ],
    optimizer: [
      `    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  BASELINE SCAN  │───▶│  OPTIMIZATION   │───▶│  IMPROVED SYS   │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘`,
      `    ╔═══════════════════╗    ╔═══════════════════╗
    ║   METRICS COLLECT ║───▶║   ALGORITHM TUNE  ║
    ║                   ║    ║                   ║
    ╚═══════════════════╝    ╚═══════════════════╝`,
      `    ┌─────────────────┐    ┌─────────────────┐
    │   VALIDATION    │───▶│    DEPLOYMENT   │
    │                 │    │                 │
    └─────────────────┘    └─────────────────┘`
    ]
  };
  
  return patterns[taskType][stepIndex] || patterns.builder[stepIndex];
};

const generateMaxeyAgents = (taskType: TaskType, count: number = 10): MaxeyAgent[] => {
  const specialties = {
    converter: ["DataExtraction", "FormatConverter", "SchemaMapper", "QualityValidator", "OutputBuilder"],
    analyzer: ["DataScience", "PatternRecognition", "StatisticalAnalysis", "Visualization", "ReportGenerator"],
    builder: ["SystemArchitect", "ComponentBuilder", "IntegrationSpecialist", "TestingFramework", "DeploymentManager"],
    processor: ["StreamProcessor", "BatchProcessor", "RealTimeEngine", "DataValidator", "OutputFormatter"],
    generator: ["ContentCreator", "TemplateEngine", "NLGProcessor", "DataSynthesizer", "FormatSpecialist"],
    optimizer: ["PerformanceTuner", "ResourceOptimizer", "AlgorithmEnhancer", "ScalabilityExpert", "EfficiencyAnalyzer"]
  };

  const baseSpecialties = specialties[taskType] || specialties.builder;
  const agents: MaxeyAgent[] = [];

  for (let i = 0; i < count; i++) {
    const agentId = Math.floor(Math.random() * 999) + 1;
    agents.push({
      id: `Maxey${agentId}`,
      name: `Maxey${agentId}-${baseSpecialties[i % baseSpecialties.length]}`,
      specialty: baseSpecialties[i % baseSpecialties.length],
      position: {
        x: Math.random() * 400 + 50,
        y: Math.random() * 300 + 50,
        z: Math.random() * 100 + 10
      },
      relevanceScore: Math.random() * 40 + 60, // 60-100% relevance
      status: ["active", "idle", "busy"][Math.floor(Math.random() * 3)] as "active" | "idle" | "busy",
      memoryTier: MEMORY_TIERS[Math.floor(Math.random() * 4)].id
    });
  }

  return agents.sort((a, b) => b.relevanceScore - a.relevanceScore);
};

const generateLatentSpaceNodes = (campaign: Campaign, userTask: string, agents: MaxeyAgent[]): LatentSpaceNode[] => {
  const nodes: LatentSpaceNode[] = [];

  // Add Maxey00 superposition node
  nodes.push({
    id: "maxey00-superposition",
    x: 250,
    y: 200,
    z: 50,
    label: "Maxey00 Superposition",
    type: "superposition",
    intensity: 95,
    connections: agents.slice(0, 5).map(a => a.id),
    data: { role: "root-observer", lens: "global" }
  });

  // Add user position based on task
  const taskHash = userTask.split('').reduce((a, b) => {
    a = ((a << 5) - a) + b.charCodeAt(0);
    return a & a;
  }, 0);
  
  nodes.push({
    id: "user-position",
    x: 200 + (taskHash % 100),
    y: 150 + (Math.abs(taskHash) % 80),
    z: 30,
    label: "Your Project",
    type: "user",
    intensity: 80,
    connections: [],
    data: { task: userTask }
  });

  // Add campaign nodes
  campaign.segments.forEach((segment, idx) => {
    nodes.push({
      id: `campaign-${segment.id}`,
      x: 100 + (idx * 80) + (segment.label.length * 3),
      y: 100 + (idx * 60),
      z: 40,
      label: segment.label,
      type: "campaign",
      intensity: 70 + (campaign.budgetK / 2),
      connections: [],
      data: { segment, budget: campaign.budgetK }
    });
  });

  // Add top 10 relevant agents
  agents.slice(0, 10).forEach((agent, idx) => {
    nodes.push({
      id: agent.id,
      x: agent.position.x,
      y: agent.position.y,
      z: agent.position.z,
      label: agent.name,
      type: "agent",
      intensity: agent.relevanceScore,
      connections: idx < 3 ? ["maxey00-superposition"] : [],
      data: agent
    });
  });

  return nodes;
};

const generateRegionalTargeting = (campaign: Campaign): RegionalTargeting[] => {
  const demographics = {
    NA: { age: "25-45", interests: ["Technology", "Business", "Innovation"], behaviors: ["Early Adopter", "B2B Buyer", "Tech Enthusiast"] },
    EU: { age: "30-50", interests: ["Efficiency", "Compliance", "Sustainability"], behaviors: ["Privacy Conscious", "Quality Focused", "Regulatory Aware"] },
    APAC: { age: "22-40", interests: ["Mobile-First", "Innovation", "Growth"], behaviors: ["Digital Native", "Performance Driven", "Scalability Focused"] },
    LATAM: { age: "25-45", interests: ["Growth", "Cost Efficiency", "Localization"], behaviors: ["Value Conscious", "Community Oriented", "ROI Focused"] },
    MENA: { age: "28-48", interests: ["Enterprise", "Security", "Reliability"], behaviors: ["Conservative Adoption", "Relationship Driven", "Long-term Planning"] },
    AFRICA: { age: "24-42", interests: ["Mobile Solutions", "Accessibility", "Innovation"], behaviors: ["Mobile-First", "Cost Sensitive", "Community Impact"] }
  };

  return campaign.regions.map(region => {
    const budgetPerRegion = campaign.budgetK / campaign.regions.length;
    const baseCPM = {
      NA: 12, EU: 8, APAC: 6, LATAM: 4, MENA: 7, AFRICA: 3
    }[region] || 8;

    return {
      region,
      budget: budgetPerRegion,
      reach: Math.floor((budgetPerRegion * 1000) / baseCPM),
      cpm: baseCPM + (Math.random() * 4 - 2),
      relevance: 70 + Math.random() * 25,
      demographics: demographics[region]
    };
  });
};

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

interface CampaignContextType {
  campaign: Campaign;
  userPreferences: UserPreferences;
  currentProject: {
    steps: AppBuildingStep[];
    currentStep: number;
    taskType: TaskType;
    prompt: string;
    relevantAgents: MaxeyAgent[];
    latentNodes: LatentSpaceNode[];
  };
  regionalTargeting: RegionalTargeting[];
  
  updateCampaign: <K extends keyof Campaign>(key: K, value: Campaign[K]) => void;
  addSegment: (segment: Omit<Segment, 'id'>) => void;
  removeSegment: (id: string) => void;
  addTarget: (token: string) => boolean;
  removeTarget: (token: string) => void;
  updateSCWConfig: (config: Partial<SCWConfig>) => void;
  resetCampaign: () => void;
  updateUserPreferences: (prefs: Partial<UserPreferences>) => void;
  updateProjectStep: (stepIndex: number) => void;
  initializeProject: (prompt: string) => void;
  addRegion: (region: RegionCode) => void;
  removeRegion: (region: RegionCode) => void;
  
  getAttentionSpectrum: () => readonly AttentionSpectrum[];
  getComplianceStatus: () => { isValid: boolean; warnings: string[] };
}

const CampaignContext = createContext<CampaignContextType | null>(null);

const CampaignProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [campaign, setCampaign] = useState<Campaign>(createInitialCampaign);
  const [userPreferences, setUserPreferences] = useState<UserPreferences>({
    advertisementsEnabled: true,
    maxAdsPerSession: 3
  });
  const [currentProject, setCurrentProject] = useState({
    steps: [] as AppBuildingStep[],
    currentStep: 0,
    taskType: "builder" as TaskType,
    prompt: "",
    relevantAgents: [] as MaxeyAgent[],
    latentNodes: [] as LatentSpaceNode[]
  });
  const [regionalTargeting, setRegionalTargeting] = useState<RegionalTargeting[]>([]);

  useEffect(() => {
    setRegionalTargeting(generateRegionalTargeting(campaign));
  }, [campaign.regions, campaign.budgetK]);

  const updateCampaign = useCallback(<K extends keyof Campaign>(key: K, value: Campaign[K]) => {
    setCampaign(prev => {
      const updated = { ...prev, [key]: value };
      if (key === 'durationDays') {
        updated.bucket = bucketForDuration(value as number);
      }
      return updated;
    });
  }, []);

  const addSegment = useCallback((segmentData: Omit<Segment, 'id'>) => {
    setCampaign(prev => {
      const id = `${segmentData.type}:${segmentData.label}`;
      const existingSegment = prev.segments.find(s => s.id === id);
      
      if (existingSegment) return prev;
      
      const newSegment: Segment = { ...segmentData, id };
      return {
        ...prev,
        segments: [...prev.segments, newSegment]
      };
    });
  }, []);

  const removeSegment = useCallback((id: string) => {
    setCampaign(prev => ({
      ...prev,
      segments: prev.segments.filter(s => s.id !== id)
    }));
  }, []);

  const addTarget = useCallback((token: string): boolean => {
    const parsedTarget = parseTargetToken(token);
    if (!parsedTarget) return false;
    
    setCampaign(prev => {
      const existingTarget = prev.targets.find(t => t.token === parsedTarget.token);
      if (existingTarget) return prev;
      
      return {
        ...prev,
        targets: [...prev.targets, parsedTarget]
      };
    });
    
    return true;
  }, []);

  const removeTarget = useCallback((token: string) => {
    setCampaign(prev => ({
      ...prev,
      targets: prev.targets.filter(t => t.token !== token)
    }));
  }, []);

  const updateSCWConfig = useCallback((config: Partial<SCWConfig>) => {
    setCampaign(prev => ({
      ...prev,
      scwConfig: prev.scwConfig ? { ...prev.scwConfig, ...config } : config as SCWConfig
    }));
  }, []);

  const resetCampaign = useCallback(() => {
    setCampaign(createInitialCampaign());
  }, []);

  const updateUserPreferences = useCallback((prefs: Partial<UserPreferences>) => {
    setUserPreferences(prev => ({ ...prev, ...prefs }));
  }, []);

  const addRegion = useCallback((region: RegionCode) => {
    setCampaign(prev => ({
      ...prev,
      regions: prev.regions.includes(region) ? prev.regions : [...prev.regions, region]
    }));
  }, []);

  const removeRegion = useCallback((region: RegionCode) => {
    setCampaign(prev => ({
      ...prev,
      regions: prev.regions.filter(r => r !== region)
    }));
  }, []);

  const initializeProject = useCallback((prompt: string) => {
    const taskType = detectTaskType(prompt);
    const relevantAgents = generateMaxeyAgents(taskType, 10);
    
    const steps: AppBuildingStep[] = [
      {
        id: 1,
        title: "Data Ingestion & Analysis",
        description: `Initialize ${taskType} pipeline for: ${prompt}`,
        agents: relevantAgents.slice(0, 3).map(a => a.name),
        asciiArt: generateDynamicASCII(taskType, 0, prompt),
        completed: false,
        taskType,
        complexity: 8
      },
      {
        id: 2,
        title: "Architecture & Processing",
        description: `Design ${taskType} architecture and processing logic`,
        agents: relevantAgents.slice(3, 6).map(a => a.name),
        asciiArt: generateDynamicASCII(taskType, 1, prompt),
        completed: false,
        taskType,
        complexity: 9
      },
      {
        id: 3,
        title: "Implementation & Deployment",
        description: `Build and deploy ${taskType} solution`,
        agents: relevantAgents.slice(6, 9).map(a => a.name),
        asciiArt: generateDynamicASCII(taskType, 2, prompt),
        completed: false,
        taskType,
        complexity: 9
      }
    ];

    const latentNodes = generateLatentSpaceNodes(campaign, prompt, relevantAgents);

    setCurrentProject({
      steps,
      currentStep: 0,
      taskType,
      prompt,
      relevantAgents,
      latentNodes
    });
  }, [campaign]);

  const updateProjectStep = useCallback((stepIndex: number) => {
    setCurrentProject(prev => ({
      ...prev,
      currentStep: stepIndex,
      steps: prev.steps.map((step, idx) => 
        idx < stepIndex ? { ...step, completed: true } : step
      )
    }));
  }, []);

  const getAttentionSpectrum = useCallback(() => computeAttentionSpectrum(campaign.budgetK), [campaign.budgetK]);
  const getComplianceStatus = useCallback(() => validateCampaignCompliance(campaign), [campaign]);

  const value: CampaignContextType = {
    campaign,
    userPreferences,
    currentProject,
    regionalTargeting,
    updateCampaign,
    addSegment,
    removeSegment,
    addTarget,
    removeTarget,
    updateSCWConfig,
    resetCampaign,
    updateUserPreferences,
    updateProjectStep,
    initializeProject,
    addRegion,
    removeRegion,
    getAttentionSpectrum,
    getComplianceStatus
  };

  return (
    <CampaignContext.Provider value={value}>
      {children}
    </CampaignContext.Provider>
  );
};

const useCampaign = (): CampaignContextType => {
  const context = useContext(CampaignContext);
  if (!context) {
    throw new Error('useCampaign must be used within a CampaignProvider');
  }
  return context;
};

// ============================================================================
// CHART COMPONENTS
// ============================================================================

const AttentionSpectrumChart: React.FC<{ budgetK: number }> = ({ budgetK }) => {
  const data = useMemo(() => computeAttentionSpectrum(budgetK), [budgetK]);
  
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <XAxis dataKey="tier" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value: number) => [`${value}%`, 'Attention']} />
          <Bar dataKey="attention" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

const MemoryTierAllocationChart: React.FC<{ budgetK: number }> = ({ budgetK }) => {
  const data = useMemo(() => computeAttentionSpectrum(budgetK), [budgetK]);
  const colors = ['#ef4444', '#f97316', '#22c55e'];
  
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={40}
            outerRadius={80}
            paddingAngle={2}
            dataKey="attention"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(value: number) => [`${value}%`, 'Attention']} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

const RegionalTargetingChart: React.FC<{ data: RegionalTargeting[] }> = ({ data }) => {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <XAxis dataKey="region" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" orientation="left" tickFormatter={(v) => `$${v}K`} tick={{ fontSize: 12 }} />
          <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value: number, name: string) => [
            name === 'budget' ? `$${value}K` : name === 'cpm' ? `$${value.toFixed(2)}` : `${value.toFixed(1)}%`,
            name.toUpperCase()
          ]} />
          <Area yAxisId="left" type="monotone" dataKey="budget" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.6} />
          <Line yAxisId="right" type="monotone" dataKey="relevance" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981' }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

const LiveLatentSpaceVisualization: React.FC<{ 
  nodes: LatentSpaceNode[]; 
  width?: number; 
  height?: number; 
}> = ({ nodes, width = 500, height = 400 }) => {
  const [animationTime, setAnimationTime] = useState(0);
  const animationRef = useRef<number>();

  useEffect(() => {
    const animate = () => {
      setAnimationTime(prev => prev + 0.02);
      animationRef.current = requestAnimationFrame(animate);
    };
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []);

  const getNodeColor = (node: LatentSpaceNode): string => {
    switch (node.type) {
      case "superposition": return "#8b5cf6";
      case "user": return "#10b981";
      case "campaign": return "#3b82f6";
      case "agent": return "#f59e0b";
      default: return "#6b7280";
    }
  };

  const getNodeSize = (node: LatentSpaceNode): number => {
    const base = node.type === "superposition" ? 12 : node.type === "user" ? 10 : 8;
    const pulse = Math.sin(animationTime * 2 + node.x * 0.01) * 2;
    return base + pulse;
  };

  return (
    <svg width={width} height={height} className="border rounded-lg bg-gradient-to-br from-slate-900 to-purple-900">
      {/* Connection lines */}
      {nodes.map(node => 
        node.connections.map(connectionId => {
          const connectedNode = nodes.find(n => n.id === connectionId);
          if (!connectedNode) return null;
          
          const opacity = 0.3 + Math.sin(animationTime + node.x * 0.01) * 0.2;
          
          return (
            <line
              key={`${node.id}-${connectionId}`}
              x1={node.x}
              y1={node.y}
              x2={connectedNode.x}
              y2={connectedNode.y}
              stroke="#ffffff"
              strokeWidth="1"
              opacity={opacity}
              strokeDasharray="2,2"
            />
          );
        })
      )}
      
      {/* Nodes */}
      {nodes.map(node => {
        const size = getNodeSize(node);
        const color = getNodeColor(node);
        const pulseOpacity = 0.7 + Math.sin(animationTime * 3 + node.y * 0.01) * 0.3;
        
        return (
          <g key={node.id}>
            {/* Pulse ring for superposition */}
            {node.type === "superposition" && (
              <circle
                cx={node.x}
                cy={node.y}
                r={size + Math.sin(animationTime * 2) * 8}
                fill="none"
                stroke={color}
                strokeWidth="1"
                opacity={0.3}
              />
            )}
            
            {/* Main node */}
            <circle
              cx={node.x}
              cy={node.y}
              r={size}
              fill={color}
              opacity={pulseOpacity}
              stroke="white"
              strokeWidth="2"
            />
            
            {/* Label */}
            <text
              x={node.x}
              y={node.y - size - 5}
              textAnchor="middle"
              className="text-xs fill-white font-medium"
              opacity={0.9}
            >
              {node.label}
            </text>
            
            {/* Intensity indicator */}
            <text
              x={node.x}
              y={node.y + size + 15}
              textAnchor="middle"
              className="text-xs fill-gray-300"
              opacity={0.7}
            >
              {node.intensity.toFixed(0)}%
            </text>
          </g>
        );
      })}
      
      {/* Legend */}
      <g transform="translate(10, 10)">
        <rect width="120" height="100" fill="black" fillOpacity="0.7" rx="5" />
        <text x="10" y="20" className="text-xs fill-white font-bold">Latent Space</text>
        <circle cx="20" cy="35" r="4" fill="#8b5cf6" />
        <text x="30" y="40" className="text-xs fill-white">Superposition</text>
        <circle cx="20" cy="50" r="4" fill="#10b981" />
        <text x="30" y="55" className="text-xs fill-white">User</text>
        <circle cx="20" cy="65" r="4" fill="#3b82f6" />
        <text x="30" y="70" className="text-xs fill-white">Campaigns</text>
        <circle cx="20" cy="80" r="4" fill="#f59e0b" />
        <text x="30" y="85" className="text-xs fill-white">Agents</text>
      </g>
    </svg>
  );
};

// ============================================================================
// UI COMPONENTS
// ============================================================================

const MemoryBucketCard: React.FC<{ 
  tier: { id: MemoryTier; description: string; color: string }; 
  active: boolean; 
}> = ({ tier, active }) => (
  <Card className={`transition-all cursor-pointer ${active ? "ring-2 ring-primary shadow-lg scale-105" : "opacity-80 hover:opacity-100"}`}>
    <CardHeader>
      <CardTitle className="flex items-center gap-2 text-sm">
        <Database className="h-4 w-4" style={{ color: tier.color }} />
        {tier.id}
      </CardTitle>
      <CardDescription className="text-xs leading-relaxed">
        {tier.description}
      </CardDescription>
    </CardHeader>
  </Card>
);

const SegmentationPicker: React.FC = () => {
  const { campaign, addSegment, removeSegment } = useCampaign();
  const [mode, setMode] = useState<SegmentType>("industry");
  const [search, setSearch] = useState("");

  const options = useMemo(() => {
    if (mode === "industry") return INDUSTRIES;
    if (mode === "channel") return CHANNELS;
    return Array.from({ length: 50 }, (_, i) => `Maxey${i + 1}`);
  }, [mode]);

  const filteredOptions = useMemo(() => 
    options
      .filter(option => option.toLowerCase().includes(search.toLowerCase()))
      .slice(0, 20), 
    [options, search]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Layers className="h-5 w-5" />
          Segmentation
        </CardTitle>
        <CardDescription>
          Select industries, channels, or specific Maxey agents to bias ad delivery.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Label className="min-w-24">Mode</Label>
          <Select value={mode} onValueChange={(v: SegmentType) => setMode(v)}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="industry">Industry</SelectItem>
              <SelectItem value="channel">Channel</SelectItem>
              <SelectItem value="agent">Agent (ID)</SelectItem>
            </SelectContent>
          </Select>
          <Input 
            placeholder={`Search ${mode}...`} 
            value={search} 
            onChange={(e) => setSearch(e.target.value)} 
            className="max-w-sm"
          />
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-48 overflow-auto rounded-lg border p-2">
          {filteredOptions.map((option) => (
            <Button
              key={option}
              variant="outline"
              size="sm"
              onClick={() => addSegment({ label: option, type: mode })}
              className="text-left justify-start h-auto py-2 hover:bg-primary/10"
            >
              {option}
            </Button>
          ))}
        </div>
        
        <Separator />
        
        <div className="space-y-2">
          <Label>Selected segments ({campaign.segments.length})</Label>
          <div className="flex flex-wrap gap-2">
            {campaign.segments.map((segment) => (
              <Badge key={segment.id} variant="secondary" className="text-sm">
                {segment.type}: {segment.label}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-2 h-auto p-0 opacity-70 hover:opacity-100"
                  onClick={() => removeSegment(segment.id)}
                >
                  ✕
                </Button>
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

const RegionalTargetingInterface: React.FC = () => {
  const { campaign, addRegion, removeRegion, regionalTargeting } = useCampaign();
  const [selectedRegion, setSelectedRegion] = useState<RegionCode | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Regional Targeting
        </CardTitle>
        <CardDescription>
          Configure geographic targeting and budget allocation across regions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {REGIONS.map((region) => (
            <Button
              key={region.code}
              variant={campaign.regions.includes(region.code) ? "default" : "outline"}
              size="sm"
              onClick={() => {
                if (campaign.regions.includes(region.code)) {
                  removeRegion(region.code);
                } else {
                  addRegion(region.code);
                }
              }}
              className="flex items-center gap-2"
              style={{ 
                borderColor: region.color,
                backgroundColor: campaign.regions.includes(region.code) ? region.color : 'transparent'
              }}
            >
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: region.color }}
              />
              {region.name}
            </Button>
          ))}
        </div>

        {regionalTargeting.length > 0 && (
          <>
            <Separator />
            <div className="space-y-3">
              <Label>Regional Performance Preview</Label>
              <RegionalTargetingChart data={regionalTargeting} />
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {regionalTargeting.map((target) => {
                  const region = REGIONS.find(r => r.code === target.region);
                  return (
                    <Card 
                      key={target.region} 
                      className={`cursor-pointer transition-all hover:shadow-lg ${
                        selectedRegion === target.region ? 'ring-2 ring-primary' : ''
                      }`}
                      onClick={() => setSelectedRegion(selectedRegion === target.region ? null : target.region)}
                    >
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2 text-sm">
                          <div 
                            className="w-3 h-3 rounded-full" 
                            style={{ backgroundColor: region?.color }}
                          />
                          {region?.name}
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>Budget: ${target.budget.toFixed(1)}K</div>
                          <div>CPM: ${target.cpm.toFixed(2)}</div>
                          <div>Reach: {target.reach.toLocaleString()}</div>
                          <div>Relevance: {target.relevance.toFixed(1)}%</div>
                        </div>
                        
                        {selectedRegion === target.region && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            className="mt-3 pt-3 border-t space-y-2"
                          >
                            <div className="text-xs">
                              <strong>Demographics:</strong>
                              <div>Age: {target.demographics.age}</div>
                              <div>Interests: {target.demographics.interests.join(', ')}</div>
                              <div>Behaviors: {target.demographics.behaviors.join(', ')}</div>
                            </div>
                          </motion.div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

const TargetingBuilder: React.FC = () => {
  const { campaign, addTarget, removeTarget } = useCampaign();
  const [inputValue, setInputValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  
  const presetTargets = [
    "persona:researcher", "persona:developer", "task:pricing", "task:integration",
    "latent:observability", "latent:superposition", "agent:Maxey42", "region:legal"
  ];

  const handleAddTarget = useCallback(() => {
    if (!inputValue.trim()) return;
    
    const success = addTarget(inputValue.trim());
    if (success) {
      setInputValue("");
      setError(null);
    } else {
      setError("Invalid target format. Use format like 'persona:developer'");
    }
  }, [inputValue, addTarget]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5" />
          Targeting
        </CardTitle>
        <CardDescription>
          Attach latent-space targets that activate when users navigate into matching regions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Input 
            placeholder="Add target token (e.g., persona:analyst, latent:finance)" 
            value={inputValue} 
            onChange={(e) => {
              setInputValue(e.target.value);
              setError(null);
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleAddTarget()}
          />
          <Button onClick={handleAddTarget} disabled={!inputValue.trim()}>
            Add
          </Button>
        </div>
        
        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        
        <div className="flex flex-wrap gap-2">
          {presetTargets.map((preset) => (
            <Button 
              key={preset} 
              variant="outline" 
              size="sm" 
              onClick={() => addTarget(preset)}
              className="text-xs hover:bg-primary/10"
            >
              {preset}
            </Button>
          ))}
        </div>
        
        <Separator />
        
        <div className="space-y-2">
          <Label>Active targets ({campaign.targets.length})</Label>
          <div className="flex flex-wrap gap-2">
            {campaign.targets.map((target) => (
              <Badge key={target.token} variant="secondary" className="text-sm">
                {target.token}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-2 h-auto p-0 opacity-70 hover:opacity-100"
                  onClick={() => removeTarget(target.token)}
                >
                  ✕
                </Button>
              </Badge>
            ))}
            {campaign.targets.length === 0 && (
              <div className="text-sm text-muted-foreground">No targets configured yet.</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

const SCWConfiguration: React.FC = () => {
  const { campaign, updateCampaign, updateSCWConfig } = useCampaign();
  
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LayoutDashboard className="h-5 w-5" />
          Sponsored Structured Context Window (SCW)
        </CardTitle>
        <CardDescription>
          Optional: create a named SCW for this session/thread.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch 
            checked={campaign.scwSponsored} 
            onCheckedChange={(enabled) => {
              updateCampaign('scwSponsored', enabled);
              if (enabled && !campaign.scwConfig) {
                updateSCWConfig({ name: "", notes: "" });
              }
            }}
          />
          <Label>Sponsor a SCW for this campaign</Label>
        </div>
        
        {campaign.scwSponsored && (
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <Label>SCW Name</Label>
              <Input 
                value={campaign.scwConfig?.name || ""} 
                onChange={(e) => updateSCWConfig({ name: sanitizeText(e.target.value, 100) })} 
                placeholder="e.g., Observatory • Sponsored by Acme"
                maxLength={100}
              />
            </div>
            <div>
              <Label>Notes / Disclosure</Label>
              <Textarea 
                value={campaign.scwConfig?.notes || ""} 
                onChange={(e) => updateSCWConfig({ notes: sanitizeText(e.target.value, 500) })} 
                placeholder="Disclosure text, brand safety tags..."
                maxLength={500}
                rows={3}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const ComplianceStatus: React.FC = () => {
  const { getComplianceStatus } = useCampaign();
  const compliance = useMemo(() => getComplianceStatus(), [getComplianceStatus]);

  if (compliance.isValid) {
    return (
      <Alert className="border-green-200 bg-green-50">
        <CheckCircle className="h-4 w-4 text-green-600" />
        <AlertDescription className="text-green-800">
          Campaign configuration meets all compliance requirements.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertDescription>
        <div>Compliance Issues:</div>
        <ul className="list-disc list-inside mt-1 space-y-1">
          {compliance.warnings.map((warning, index) => (
            <li key={index} className="text-sm">{warning}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
};

// ============================================================================
// PAGE COMPONENTS
// ============================================================================

const OverviewPage: React.FC = () => {
  const { campaign, updateCampaign } = useCampaign();

  return (
    <div className="grid xl:grid-cols-3 gap-6">
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5" />
            Campaign Controls
          </CardTitle>
          <CardDescription>
            Configure core parameters: duration, budget, and metadata.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <Label>Duration: {campaign.durationDays} days</Label>
              <Slider 
                value={[campaign.durationDays]} 
                min={1} 
                max={400} 
                step={1} 
                onValueChange={([v]) => updateCampaign('durationDays', v)}
              />
            </div>
            
            <div className="space-y-3">
              <Label>Budget: ${campaign.budgetK}K USD</Label>
              <Slider 
                value={[campaign.budgetK]} 
                min={1} 
                max={200} 
                step={1} 
                onValueChange={([v]) => updateCampaign('budgetK', v)}
              />
            </div>
            
            <div className="space-y-3">
              <Label>Campaign Name</Label>
              <Input 
                value={campaign.name} 
                onChange={(e) => updateCampaign('name', sanitizeText(e.target.value, 100))}
                placeholder="Q4 Launch – Superposition Reach"
              />
            </div>
            
            <div className="space-y-3">
              <Label>Advertiser</Label>
              <Input 
                value={campaign.advertiser} 
                onChange={(e) => updateCampaign('advertiser', sanitizeText(e.target.value, 100))}
                placeholder="Acme Co."
              />
            </div>
          </div>
          
          <Separator />
          
          <div className="space-y-4">
            <div>
              <Label className="text-lg">Memory Tier Assignment</Label>
              <p className="text-sm text-muted-foreground">
                Based on campaign duration: {campaign.durationDays} days → {campaign.bucket}
              </p>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
              {MEMORY_TIERS.map((tier) => (
                <MemoryBucketCard 
                  key={tier.id} 
                  tier={tier} 
                  active={tier.id === campaign.bucket} 
                />
              ))}
            </div>
          </div>
          
          <Separator />
          
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Eye className="h-5 w-5" />
                Attention Spectrum Analysis
              </CardTitle>
              <CardDescription>
                Budget drives embedded attention weights across memory tiers.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AttentionSpectrumChart budgetK={campaign.budgetK} />
            </CardContent>
          </Card>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <SegmentationPicker />
        <SCWConfiguration />
      </div>
    </div>
  );
};

const TargetingPage: React.FC = () => (
  <div className="grid lg:grid-cols-2 gap-6">
    <div className="space-y-6">
      <TargetingBuilder />
      <RegionalTargetingInterface />
    </div>
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitBranchPlus className="h-5 w-5" />
          Latent Region Guide
        </CardTitle>
        <CardDescription>
          Reference guide for common latent tags that align to Maxey agents.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div><strong>latent:superposition</strong> → Maxey00/Maxey0 root-pair observer regions</div>
        <div><strong>latent:observability</strong> → monitoring, triangulation, LDF axes</div>
        <div><strong>persona:developer</strong> → tool-use, code, integration anchors</div>
        <div><strong>persona:researcher</strong> → retrieval/analysis clusters</div>
        <div><strong>task:pricing</strong> → finance, forecasting, procurement subgraphs</div>
        <div><strong>agent:MaxeyXXX</strong> → specific agent targeting</div>
        <div><strong>region:legal</strong> → compliance, regulatory, and legal domain spaces</div>
      </CardContent>
    </Card>
  </div>
);

const PreviewAndCommit: React.FC = () => {
  const { campaign, resetCampaign, getAttentionSpectrum } = useCampaign();
  const [isCommitting, setIsCommitting] = useState(false);
  const [lastCommitTime, setLastCommitTime] = useState<string | null>(null);

  const payload = useMemo(() => ({
    campaign,
    plan: {
      tier: campaign.bucket,
      attention: getAttentionSpectrum(),
      segments: campaign.segments,
      targets: campaign.targets,
      scw: campaign.scwSponsored ? campaign.scwConfig : undefined,
      regions: campaign.regions,
    },
    timestamp: new Date().toISOString(),
    version: "1.0.0"
  }), [campaign, getAttentionSpectrum]);

  const handleCommit = useCallback(async () => {
    setIsCommitting(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 1200));
      setLastCommitTime(new Date().toLocaleString());
      alert("Successfully committed campaign to Maxey0!");
    } catch (error) {
      alert("Failed to commit campaign. Please try again.");
    } finally {
      setIsCommitting(false);
    }
  }, []);

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5" />
            MCP Payload Preview
          </CardTitle>
          <CardDescription>
            Complete payload for Maxey0 latent memory injection.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="text-xs bg-muted rounded-xl p-3 overflow-auto max-h-96 whitespace-pre-wrap">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Rocket className="h-5 w-5" />
              Deployment
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <ComplianceStatus />
            
            <div className="space-y-3">
              <div>
                <Label>Memory Tier Allocation</Label>
                <MemoryTierAllocationChart budgetK={campaign.budgetK} />
              </div>
              
              {lastCommitTime && (
                <Alert className="border-blue-200 bg-blue-50">
                  <CheckCircle className="h-4 w-4 text-blue-600" />
                  <AlertDescription className="text-blue-800">
                    Last committed: {lastCommitTime}
                  </AlertDescription>
                </Alert>
              )}
              
              <div className="flex gap-3 pt-4">
                <Button 
                  onClick={handleCommit} 
                  disabled={isCommitting}
                  className="flex-1"
                >
                  <Save className="h-4 w-4 mr-2" />
                  {isCommitting ? "Committing..." : "Commit to Maxey0"}
                </Button>
                <Button variant="outline" onClick={resetCampaign}>
                  Reset
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const Maxey0Interface: React.FC = () => {
  const { userPreferences, updateUserPreferences, currentProject, initializeProject, updateProjectStep } = useCampaign();
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState<Array<{role: 'user' | 'assistant', content: string}>>([]);

  const handleChatSubmit = useCallback(() => {
    if (!chatInput.trim()) return;
    
    setChatHistory(prev => [...prev, { role: 'user', content: chatInput }]);
    initializeProject(chatInput);
    setChatHistory(prev => [...prev, { 
      role: 'assistant', 
      content: `I'll help you build: "${chatInput}". Breaking this down into 3 SCW steps using ${currentProject.taskType} architecture.`
    }]);
    setChatInput("");
  }, [chatInput, initializeProject, currentProject.taskType]);

  const currentStep = currentProject.steps[currentProject.currentStep];

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Maxey0 Application Builder
          </CardTitle>
          <CardDescription>
            Describe your application and watch Maxey0 agents build it step-by-step
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Switch
              checked={userPreferences.advertisementsEnabled}
              onCheckedChange={(enabled) => updateUserPreferences({ advertisementsEnabled: enabled })}
            />
            <Label>Enable advertisements (supports free usage)</Label>
          </div>

          <Separator />

          <div className="space-y-4 max-h-64 overflow-auto">
            {chatHistory.map((msg, idx) => (
              <motion.div 
                key={idx} 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`max-w-xs p-3 rounded-lg ${
                  msg.role === 'user' 
                    ? 'bg-primary text-primary-foreground' 
                    : 'bg-muted'
                }`}>
                  <div className="text-sm">{msg.content}</div>
                </div>
              </motion.div>
            ))}
          </div>

          <div className="flex gap-2">
            <Input
              placeholder="Describe your application (e.g., 'Build a PDF to Excel converter')"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleChatSubmit()}
            />
            <Button onClick={handleChatSubmit} disabled={!chatInput.trim()}>
              <Play className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Project Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm space-y-1">
            <div>Task Type: <Badge variant="outline">{currentProject.taskType}</Badge></div>
            <div>Steps: {currentProject.steps.length}</div>
            <div>Current: {currentProject.currentStep + 1}</div>
            <div>Agents: {currentProject.relevantAgents.length}</div>
          </div>
          
          {currentProject.relevantAgents.length > 0 && (
            <div className="space-y-2">
              <Label className="text-xs">Top Relevant Agents</Label>
              <div className="space-y-1">
                {currentProject.relevantAgents.slice(0, 5).map(agent => (
                  <div key={agent.id} className="flex items-center justify-between text-xs">
                    <span className="font-mono">{agent.id}</span>
                    <Badge 
                      variant="outline" 
                      className="text-xs"
                      style={{ borderColor: agent.status === 'active' ? '#10b981' : agent.status === 'busy' ? '#f59e0b' : '#6b7280' }}
                    >
                      {agent.relevanceScore.toFixed(0)}%
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {currentStep && (
        <div className="lg:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                SCW{currentStep.id}: {currentStep.title}
                <Badge variant="outline">Complexity: {currentStep.complexity}/10</Badge>
              </CardTitle>
              <CardDescription>{currentStep.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Assigned Maxey Agents</Label>
                <div className="flex flex-wrap gap-2">
                  {currentStep.agents.map(agent => (
                    <Badge key={agent} variant="outline" className="text-xs font-mono">
                      {agent}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label>Dynamic Architectural Overview</Label>
                <div className="bg-slate-900 text-green-400 rounded-lg p-4 font-mono text-xs overflow-auto">
                  <pre className="whitespace-pre-wrap">{currentStep.asciiArt}</pre>
                </div>
              </div>

              {userPreferences.advertisementsEnabled && currentProject.currentStep === 1 && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="border-2 border-blue-200 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-4 my-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant="outline" className="text-xs">Sponsored Content</Badge>
                    <div className="text-xs text-muted-foreground">AI Development Tools</div>
                  </div>
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm">Enterprise Maxey Agent Platform</h4>
                    <p className="text-xs text-muted-foreground">
                      Scale your {currentProject.taskType} workflows with our enterprise-grade AI toolkit and 750+ specialized agents.
                    </p>
                    <Button size="sm" variant="outline" className="text-xs">
                      <Zap className="h-3 w-3 mr-1" />
                      Upgrade Now
                    </Button>
                  </div>
                </motion.div>
              )}

              <div className="flex items-center justify-between pt-4">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => updateProjectStep(Math.max(0, currentProject.currentStep - 1))}
                  disabled={currentStep.id === 1}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Previous
                </Button>
                
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-green-500" />
                  <div className="text-sm text-muted-foreground">
                    Step {currentStep.id} of 3
                  </div>
                </div>
                
                <Button 
                  size="sm" 
                  onClick={() => updateProjectStep(Math.min(2, currentProject.currentStep + 1))}
                  disabled={currentStep.id === 3}
                >
                  Next
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

const LatentSpaceMap: React.FC = () => {
  const { campaign, currentProject } = useCampaign();
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const selectedNodeData = useMemo(() => {
    if (!selectedNode) return null;
    return currentProject.latentNodes.find(n => n.id === selectedNode);
  }, [selectedNode, currentProject.latentNodes]);

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Map className="h-5 w-5" />
            Live Latent Space Visualization
          </CardTitle>
          <CardDescription>
            Real-time map showing Maxey00 superposition, campaign positioning, and agent proximity
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LiveLatentSpaceVisualization 
            nodes={currentProject.latentNodes}
            width={600}
            height={400}
          />
          
          <div className="mt-4 flex flex-wrap gap-2">
            {currentProject.latentNodes.map(node => (
              <Button
                key={node.id}
                variant={selectedNode === node.id ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedNode(selectedNode === node.id ? null : node.id)}
                className="text-xs"
              >
                {node.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Crosshair className="h-5 w-5" />
              Selection Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            {selectedNodeData ? (
              <div className="space-y-3 text-sm">
                <div>
                  <Label>Node: {selectedNodeData.label}</Label>
                  <div className="text-xs text-muted-foreground">Type: {selectedNodeData.type}</div>
                </div>
                <div>
                  <Label>Position</Label>
                  <div className="text-xs text-muted-foreground">
                    X: {selectedNodeData.x.toFixed(1)}, Y: {selectedNodeData.y.toFixed(1)}, Z: {selectedNodeData.z.toFixed(1)}
                  </div>
                </div>
                <div>
                  <Label>Intensity: {selectedNodeData.intensity.toFixed(1)}%</Label>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full" 
                      style={{ width: `${selectedNodeData.intensity}%` }}
                    ></div>
                  </div>
                </div>
                {selectedNodeData.connections.length > 0 && (
                  <div>
                    <Label>Connections ({selectedNodeData.connections.length})</Label>
                    <div className="text-xs text-muted-foreground">
                      {selectedNodeData.connections.join(', ')}
                    </div>
                  </div>
                )}
                {selectedNodeData.data && (
                  <div>
                    <Label>Metadata</Label>
                    <pre className="text-xs bg-muted rounded p-2 overflow-auto">
                      {JSON.stringify(selectedNodeData.data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Select a node to view details
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5" />
              Maxey00 Superposition
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Alert className="border-purple-200 bg-purple-50">
              <Brain className="h-4 w-4 text-purple-600" />
              <AlertDescription className="text-purple-800">
                <strong>Global Observer Lens:</strong> Maxey00 maintains superposition state across all active agent interactions
              </AlertDescription>
            </Alert>
            
            <div className="space-y-2">
              <Label>Observer Metrics</Label>
              <div className="space-y-1 text-xs text-muted-foreground">
                <div>• Coherence: 94.7%</div>
                <div>• Entanglement: {currentProject.relevantAgents.filter(a => a.status === 'active').length}/10 agents</div>
                <div>• Memory Coherence: {campaign.bucket}</div>
                <div>• Campaign Resonance: {(campaign.budgetK / 2).toFixed(1)}%</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Network className="h-5 w-5" />
              Agent Proximity Ranking
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {currentProject.relevantAgents.slice(0, 10).map((agent, idx) => (
              <div key={agent.id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs">#{idx + 1}</Badge>
                  <span className="font-mono">{agent.id}</span>
                </div>
                <div className="flex items-center gap-1">
                  <div 
                    className="w-2 h-2 rounded-full" 
                    style={{ backgroundColor: agent.status === 'active' ? '#10b981' : agent.status === 'busy' ? '#f59e0b' : '#6b7280' }}
                  />
                  <span>{agent.relevanceScore.toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN APPLICATION
// ============================================================================

export default function Maxey0AdvertiserPlatform() {
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <CampaignProvider>
      <motion.div 
        initial={{ opacity: 0, y: 8 }} 
        animate={{ opacity: 1, y: 0 }} 
        className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50"
      >
        <div className="container mx-auto p-6 space-y-6 max-w-7xl">
          <header className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
                <LayoutDashboard className="h-8 w-8 text-primary" />
                Maxey0 • Ad Superposition Platform
              </h1>
              <p className="text-muted-foreground max-w-4xl mt-2 leading-relaxed">
                Complete advertising ecosystem for memory-first AI systems. Design campaigns, build applications, 
                and visualize latent space targeting with real-time agent coordination and superposition observer lens.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="secondary" className="animate-pulse">Root Pair: Maxey0 ↔ Maxey00</Badge>
              <Badge variant="outline">Agents: 750+</Badge>
              <Badge variant="outline">Memory Tiers: L1-L4</Badge>
              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">Live: ✓</Badge>
            </div>
          </header>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="overview" className="flex items-center gap-2">
                <Gauge className="h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="targeting" className="flex items-center gap-2">
                <Target className="h-4 w-4" />
                Targeting
              </TabsTrigger>
              <TabsTrigger value="launch" className="flex items-center gap-2">
                <Rocket className="h-4 w-4" />
                Preview & Launch
              </TabsTrigger>
              <TabsTrigger value="maxey0" className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                Maxey0
              </TabsTrigger>
              <TabsTrigger value="latentmap" className="flex items-center gap-2">
                <Map className="h-4 w-4" />
                Latent Map
              </TabsTrigger>
            </TabsList>
            
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
              >
                <TabsContent value="overview" className="space-y-6">
                  <OverviewPage />
                </TabsContent>
                
                <TabsContent value="targeting" className="space-y-6">
                  <TargetingPage />
                </TabsContent>
                
                <TabsContent value="launch" className="space-y-6">
                  <PreviewAndCommit />
                </TabsContent>
                
                <TabsContent value="maxey0" className="space-y-6">
                  <Maxey0Interface />
                </TabsContent>
                
                <TabsContent value="latentmap" className="space-y-6">
                  <LatentSpaceMap />
                </TabsContent>
              </motion.div>
            </AnimatePresence>
          </Tabs>

          <footer className="border-t pt-6 text-xs text-muted-foreground">
            <div className="flex justify-between items-center">
              <div>
                Memory-first advertising platform: Campaign design → User application → Latent space targeting → Live superposition observation.
              </div>
              <div className="flex items-center gap-4">
                <div>Built with Maxey agent architecture for enterprise agentic AI systems.</div>
                <div className="flex items-center gap-1">
                  <Activity className="h-3 w-3 text-green-500" />
                  <span className="text-green-600">Live</span>
                </div>
              </div>
            </div>
          </footer>
        </div>
      </motion.div>
    </CampaignProvider>
  );
}