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
import { Shield, Lock, Eye, EyeOff, Database, Target, Layers, DollarSign, Settings, LayoutDashboard, Box, AlertTriangle, CheckCircle, MessageSquare, ChevronRight, Map, Code, FileText, Activity, Cpu, Network, Brain, Zap, Filter, Users, Globe, Building, TrendingUp, BarChart3, Download, Upload, RefreshCw, Circle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ScatterChart, Scatter, ZAxis } from "recharts";

// ============================================================================
// TYPES AND INTERFACES
// ============================================================================

type MemoryTier = "Scratchpad (L1)" | "Episodic (L2)" | "Persistent (L3)" | "Permanent (L4)";
type PrivacyLevel = "minimal" | "balanced" | "strict" | "custom";
type AdCategory = "technology" | "business" | "education" | "lifestyle" | "none";
type SCWGateType = "allow" | "block" | "review" | "contextual";

interface SCWPrivacyGate {
  id: string;
  name: string;
  gateType: SCWGateType;
  allowedCategories: AdCategory[];
  blockedTopics: string[];
  maxAdsPerSession: number;
  requireRelevanceScore: number;
  memoryTierAccess: MemoryTier[];
  dataSharing: {
    conversationContext: boolean;
    userPreferences: boolean;
    behavioralData: boolean;
    demographicData: boolean;
  };
}

interface UserAdProfile {
  privacyLevel: PrivacyLevel;
  interests: string[];
  blockedBrands: string[];
  allowedCategories: AdCategory[];
  scwGates: SCWPrivacyGate[];
  sessionLimits: {
    maxAdsPerHour: number;
    maxAdsPerDay: number;
    minRelevanceThreshold: number;
  };
  dataControls: {
    shareConversationTopics: boolean;
    shareSearchHistory: boolean;
    shareInteractionPatterns: boolean;
    allowPersonalization: boolean;
  };
}

interface AdCampaign {
  id: string;
  advertiser: string;
  category: AdCategory;
  relevanceScore: number;
  targetTopics: string[];
  respectedPrivacyGates: string[];
  memoryTierPlacement: MemoryTier;
  isContextual: boolean;
  brandSafetyScore: number;
}

interface LatentSpaceVector {
  id: string;
  x: number;
  y: number;
  z: number;
  label: string;
  type: "user-boundary" | "ad-campaign" | "scw-gate" | "privacy-zone";
  intensity: number;
  privacyLevel: number;
}

interface SCWContainer {
  id: string;
  name: string;
  purpose: string;
  privacyBoundary: {
    allowedMemoryTiers: MemoryTier[];
    isolationLevel: "strict" | "moderate" | "open";
    adExposure: "none" | "contextual" | "full";
  };
  activeGates: string[];
  encryptedData: boolean;
}

interface AdvertiserView {
  aggregateTopics: string[];
  anonymizedInterests: string[];
  contextualSignals: string[];
  privacyCompliantTargets: string[];
  cannotAccess: string[];
}

// ============================================================================
// CONSTANTS AND DATA
// ============================================================================

const PRIVACY_LEVELS = [
  { 
    id: "minimal" as PrivacyLevel, 
    name: "Minimal Privacy",
    description: "Maximum ad personalization, shares behavioral data",
    color: "#ef4444"
  },
  { 
    id: "balanced" as PrivacyLevel, 
    name: "Balanced",
    description: "Contextual targeting only, limited data sharing",
    color: "#f59e0b"
  },
  { 
    id: "strict" as PrivacyLevel, 
    name: "Strict Privacy",
    description: "No personalization, minimal ads, no data sharing",
    color: "#10b981"
  },
  { 
    id: "custom" as PrivacyLevel, 
    name: "Custom Controls",
    description: "Granular SCW-level privacy configuration",
    color: "#3b82f6"
  }
];

const AD_CATEGORIES: { id: AdCategory; label: string; icon: string }[] = [
  { id: "technology", label: "Technology & Software", icon: "💻" },
  { id: "business", label: "Business & Enterprise", icon: "🏢" },
  { id: "education", label: "Education & Learning", icon: "📚" },
  { id: "lifestyle", label: "Lifestyle & Productivity", icon: "🎯" },
  { id: "none", label: "No Advertisements", icon: "🚫" }
];

const MEMORY_TIERS_CONFIG = [
  { 
    id: "Scratchpad (L1)" as MemoryTier, 
    description: "Temporary working memory - ads cleared after session",
    color: "#ef4444",
    privacyRisk: "Low"
  },
  { 
    id: "Episodic (L2)" as MemoryTier, 
    description: "Session memory - ads persist within conversation thread",
    color: "#f97316",
    privacyRisk: "Medium"
  },
  { 
    id: "Persistent (L3)" as MemoryTier, 
    description: "Long-term memory - ads may influence future sessions",
    color: "#22c55e",
    privacyRisk: "High"
  },
  { 
    id: "Permanent (L4)" as MemoryTier, 
    description: "Immutable storage - NOT recommended for advertising",
    color: "#6b7280",
    privacyRisk: "Critical"
  }
];

const DEFAULT_PRIVACY_GATES: Omit<SCWPrivacyGate, 'id'>[] = [
  {
    name: "Work Conversations",
    gateType: "block",
    allowedCategories: ["business", "technology"],
    blockedTopics: ["personal finance", "health", "relationships"],
    maxAdsPerSession: 1,
    requireRelevanceScore: 90,
    memoryTierAccess: ["Scratchpad (L1)"],
    dataSharing: {
      conversationContext: false,
      userPreferences: false,
      behavioralData: false,
      demographicData: false
    }
  },
  {
    name: "Learning Sessions",
    gateType: "contextual",
    allowedCategories: ["education", "technology"],
    blockedTopics: ["politics", "controversial"],
    maxAdsPerSession: 2,
    requireRelevanceScore: 85,
    memoryTierAccess: ["Scratchpad (L1)", "Episodic (L2)"],
    dataSharing: {
      conversationContext: true,
      userPreferences: false,
      behavioralData: false,
      demographicData: false
    }
  },
  {
    name: "General Browsing",
    gateType: "allow",
    allowedCategories: ["technology", "business", "education", "lifestyle"],
    blockedTopics: [],
    maxAdsPerSession: 3,
    requireRelevanceScore: 75,
    memoryTierAccess: ["Scratchpad (L1)", "Episodic (L2)"],
    dataSharing: {
      conversationContext: true,
      userPreferences: true,
      behavioralData: false,
      demographicData: false
    }
  }
];

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const createDefaultUserProfile = (): UserAdProfile => ({
  privacyLevel: "balanced",
  interests: [],
  blockedBrands: [],
  allowedCategories: ["technology", "education"],
  scwGates: DEFAULT_PRIVACY_GATES.map(gate => ({
    ...gate,
    id: crypto.randomUUID()
  })),
  sessionLimits: {
    maxAdsPerHour: 5,
    maxAdsPerDay: 20,
    minRelevanceThreshold: 75
  },
  dataControls: {
    shareConversationTopics: true,
    shareSearchHistory: false,
    shareInteractionPatterns: false,
    allowPersonalization: true
  }
});

const calculatePrivacyScore = (profile: UserAdProfile): number => {
  let score = 0;
  
  // Privacy level base score
  const levelScores = { minimal: 0, balanced: 40, strict: 80, custom: 50 };
  score += levelScores[profile.privacyLevel];
  
  // Data controls
  if (!profile.dataControls.shareConversationTopics) score += 5;
  if (!profile.dataControls.shareSearchHistory) score += 5;
  if (!profile.dataControls.shareInteractionPatterns) score += 5;
  if (!profile.dataControls.allowPersonalization) score += 5;
  
  // SCW gates
  const strictGates = profile.scwGates.filter(g => g.gateType === "block").length;
  score += strictGates * 2;
  
  return Math.min(100, score);
};

const generateAdvertiserView = (profile: UserAdProfile): AdvertiserView => {
  const canShareTopics = profile.dataControls.shareConversationTopics;
  const canSharePreferences = profile.dataControls.allowPersonalization;
  
  return {
    aggregateTopics: canShareTopics ? ["AI", "productivity", "technology"] : [],
    anonymizedInterests: canSharePreferences ? profile.interests.slice(0, 3) : [],
    contextualSignals: ["current_conversation_topic", "session_intent"],
    privacyCompliantTargets: profile.allowedCategories.filter(c => c !== "none"),
    cannotAccess: [
      "conversation_history",
      "user_identity",
      "personal_data",
      "cross_session_behavior",
      "demographic_information"
    ]
  };
};

const generateLatentSpaceVectors = (profile: UserAdProfile): LatentSpaceVector[] => {
  const vectors: LatentSpaceVector[] = [];
  
  // User privacy boundary
  vectors.push({
    id: "user-privacy-boundary",
    x: 250,
    y: 250,
    z: 50,
    label: "Your Privacy Boundary",
    type: "user-boundary",
    intensity: calculatePrivacyScore(profile),
    privacyLevel: calculatePrivacyScore(profile)
  });
  
  // SCW gates
  profile.scwGates.forEach((gate, idx) => {
    const angle = (idx / profile.scwGates.length) * 2 * Math.PI;
    const radius = 150;
    vectors.push({
      id: gate.id,
      x: 250 + radius * Math.cos(angle),
      y: 250 + radius * Math.sin(angle),
      z: 40,
      label: gate.name,
      type: "scw-gate",
      intensity: gate.requireRelevanceScore,
      privacyLevel: gate.gateType === "block" ? 95 : gate.gateType === "review" ? 75 : 50
    });
  });
  
  // Privacy zones
  const privacyZones = [
    { label: "Strict Zone", level: 90, offset: 0 },
    { label: "Balanced Zone", level: 60, offset: 120 },
    { label: "Open Zone", level: 30, offset: 240 }
  ];
  
  privacyZones.forEach(zone => {
    const angle = (zone.offset / 360) * 2 * Math.PI;
    vectors.push({
      id: `privacy-${zone.label}`,
      x: 250 + 100 * Math.cos(angle),
      y: 250 + 100 * Math.sin(angle),
      z: 30,
      label: zone.label,
      type: "privacy-zone",
      intensity: zone.level,
      privacyLevel: zone.level
    });
  });
  
  // Ad campaigns (respectful of boundaries)
  const campaigns = [
    { label: "Tech SaaS", category: "technology", respect: 85 },
    { label: "EdTech", category: "education", respect: 90 },
    { label: "Enterprise", category: "business", respect: 80 }
  ];
  
  campaigns.forEach((campaign, idx) => {
    if (profile.allowedCategories.includes(campaign.category as AdCategory)) {
      const angle = (idx / campaigns.length) * 2 * Math.PI;
      const radius = 200;
      vectors.push({
        id: `campaign-${campaign.label}`,
        x: 250 + radius * Math.cos(angle),
        y: 250 + radius * Math.sin(angle),
        z: 35,
        label: campaign.label,
        type: "ad-campaign",
        intensity: campaign.respect,
        privacyLevel: campaign.respect
      });
    }
  });
  
  return vectors;
};

const generateSCWContainers = (profile: UserAdProfile): SCWContainer[] => {
  return profile.scwGates.map(gate => ({
    id: gate.id,
    name: gate.name,
    purpose: `Privacy-gated conversation container with ${gate.gateType} policy`,
    privacyBoundary: {
      allowedMemoryTiers: gate.memoryTierAccess,
      isolationLevel: gate.gateType === "block" ? "strict" : gate.gateType === "review" ? "moderate" : "open",
      adExposure: gate.gateType === "block" ? "none" : gate.gateType === "contextual" ? "contextual" : "full"
    },
    activeGates: [gate.id],
    encryptedData: !gate.dataSharing.conversationContext
  }));
};

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

interface AppContextType {
  userProfile: UserAdProfile;
  latentVectors: LatentSpaceVector[];
  scwContainers: SCWContainer[];
  advertiserView: AdvertiserView;
  privacyScore: number;
  
  updatePrivacyLevel: (level: PrivacyLevel) => void;
  updateDataControl: (key: keyof UserAdProfile['dataControls'], value: boolean) => void;
  updateSessionLimit: (key: keyof UserAdProfile['sessionLimits'], value: number) => void;
  addInterest: (interest: string) => void;
  removeInterest: (interest: string) => void;
  toggleCategory: (category: AdCategory) => void;
  addBlockedBrand: (brand: string) => void;
  removeBlockedBrand: (brand: string) => void;
  updateGate: (gateId: string, updates: Partial<SCWPrivacyGate>) => void;
  createNewGate: () => void;
  deleteGate: (gateId: string) => void;
  exportProfile: () => string;
  importProfile: (json: string) => boolean;
  resetToDefaults: () => void;
}

const AppContext = createContext<AppContextType | null>(null);

const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [userProfile, setUserProfile] = useState<UserAdProfile>(createDefaultUserProfile);
  const [latentVectors, setLatentVectors] = useState<LatentSpaceVector[]>([]);
  const [scwContainers, setScwContainers] = useState<SCWContainer[]>([]);
  const [advertiserView, setAdvertiserView] = useState<AdvertiserView>({
    aggregateTopics: [],
    anonymizedInterests: [],
    contextualSignals: [],
    privacyCompliantTargets: [],
    cannotAccess: []
  });
  const [privacyScore, setPrivacyScore] = useState(0);
  
  useEffect(() => {
    setLatentVectors(generateLatentSpaceVectors(userProfile));
    setScwContainers(generateSCWContainers(userProfile));
    setAdvertiserView(generateAdvertiserView(userProfile));
    setPrivacyScore(calculatePrivacyScore(userProfile));
  }, [userProfile]);
  
  const updatePrivacyLevel = useCallback((level: PrivacyLevel) => {
    setUserProfile(prev => {
      const updated = { ...prev, privacyLevel: level };
      
      // Apply privacy level presets
      if (level === "strict") {
        updated.dataControls = {
          shareConversationTopics: false,
          shareSearchHistory: false,
          shareInteractionPatterns: false,
          allowPersonalization: false
        };
        updated.sessionLimits.maxAdsPerHour = 2;
        updated.sessionLimits.maxAdsPerDay = 5;
        updated.sessionLimits.minRelevanceThreshold = 90;
      } else if (level === "minimal") {
        updated.dataControls = {
          shareConversationTopics: true,
          shareSearchHistory: true,
          shareInteractionPatterns: true,
          allowPersonalization: true
        };
        updated.sessionLimits.maxAdsPerHour = 10;
        updated.sessionLimits.maxAdsPerDay = 50;
        updated.sessionLimits.minRelevanceThreshold = 60;
      }
      
      return updated;
    });
  }, []);
  
  const updateDataControl = useCallback((key: keyof UserAdProfile['dataControls'], value: boolean) => {
    setUserProfile(prev => ({
      ...prev,
      dataControls: { ...prev.dataControls, [key]: value }
    }));
  }, []);
  
  const updateSessionLimit = useCallback((key: keyof UserAdProfile['sessionLimits'], value: number) => {
    setUserProfile(prev => ({
      ...prev,
      sessionLimits: { ...prev.sessionLimits, [key]: value }
    }));
  }, []);
  
  const addInterest = useCallback((interest: string) => {
    setUserProfile(prev => ({
      ...prev,
      interests: [...prev.interests, interest.trim()].slice(0, 20)
    }));
  }, []);
  
  const removeInterest = useCallback((interest: string) => {
    setUserProfile(prev => ({
      ...prev,
      interests: prev.interests.filter(i => i !== interest)
    }));
  }, []);
  
  const toggleCategory = useCallback((category: AdCategory) => {
    setUserProfile(prev => {
      const allowed = prev.allowedCategories.includes(category);
      return {
        ...prev,
        allowedCategories: allowed
          ? prev.allowedCategories.filter(c => c !== category)
          : [...prev.allowedCategories, category]
      };
    });
  }, []);
  
  const addBlockedBrand = useCallback((brand: string) => {
    setUserProfile(prev => ({
      ...prev,
      blockedBrands: [...prev.blockedBrands, brand.trim()].slice(0, 50)
    }));
  }, []);
  
  const removeBlockedBrand = useCallback((brand: string) => {
    setUserProfile(prev => ({
      ...prev,
      blockedBrands: prev.blockedBrands.filter(b => b !== brand)
    }));
  }, []);
  
  const updateGate = useCallback((gateId: string, updates: Partial<SCWPrivacyGate>) => {
    setUserProfile(prev => ({
      ...prev,
      scwGates: prev.scwGates.map(gate =>
        gate.id === gateId ? { ...gate, ...updates } : gate
      )
    }));
  }, []);
  
  const createNewGate = useCallback(() => {
    const newGate: SCWPrivacyGate = {
      id: crypto.randomUUID(),
      name: `Custom Gate ${userProfile.scwGates.length + 1}`,
      gateType: "contextual",
      allowedCategories: ["technology"],
      blockedTopics: [],
      maxAdsPerSession: 2,
      requireRelevanceScore: 80,
      memoryTierAccess: ["Scratchpad (L1)"],
      dataSharing: {
        conversationContext: false,
        userPreferences: false,
        behavioralData: false,
        demographicData: false
      }
    };
    
    setUserProfile(prev => ({
      ...prev,
      scwGates: [...prev.scwGates, newGate]
    }));
  }, [userProfile.scwGates.length]);
  
  const deleteGate = useCallback((gateId: string) => {
    setUserProfile(prev => ({
      ...prev,
      scwGates: prev.scwGates.filter(g => g.id !== gateId)
    }));
  }, []);
  
  const exportProfile = useCallback(() => {
    return JSON.stringify({
      version: "1.0.0",
      timestamp: new Date().toISOString(),
      profile: userProfile
    }, null, 2);
  }, [userProfile]);
  
  const importProfile = useCallback((json: string): boolean => {
    try {
      const data = JSON.parse(json);
      if (data.profile && data.version) {
        setUserProfile(data.profile);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }, []);
  
  const resetToDefaults = useCallback(() => {
    setUserProfile(createDefaultUserProfile());
  }, []);
  
  const value: AppContextType = {
    userProfile,
    latentVectors,
    scwContainers,
    advertiserView,
    privacyScore,
    updatePrivacyLevel,
    updateDataControl,
    updateSessionLimit,
    addInterest,
    removeInterest,
    toggleCategory,
    addBlockedBrand,
    removeBlockedBrand,
    updateGate,
    createNewGate,
    deleteGate,
    exportProfile,
    importProfile,
    resetToDefaults
  };
  
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

const useApp = (): AppContextType => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used within AppProvider');
  return context;
};

// ============================================================================
// VISUALIZATION COMPONENTS
// ============================================================================

const LatentSpaceVisualization: React.FC<{ vectors: LatentSpaceVector[] }> = ({ vectors }) => {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [animationTime, setAnimationTime] = useState(0);
  const animationRef = useRef<number>();

  useEffect(() => {
    const animate = () => {
      setAnimationTime(prev => prev + 0.02);
      animationRef.current = requestAnimationFrame(animate);
    };
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  const getNodeColor = (vector: LatentSpaceVector): string => {
    const privacyLevel = vector.privacyLevel;
    if (privacyLevel >= 80) return "#10b981"; // High privacy - green
    if (privacyLevel >= 60) return "#3b82f6"; // Medium privacy - blue
    if (privacyLevel >= 40) return "#f59e0b"; // Low privacy - orange
    return "#ef4444"; // Very low - red
  };

  const getNodeSize = (vector: LatentSpaceVector): number => {
    const base = vector.type === "user-boundary" ? 14 : vector.type === "scw-gate" ? 10 : 8;
    const pulse = hoveredNode === vector.id ? 4 : Math.sin(animationTime * 2 + vector.x * 0.01) * 2;
    return base + pulse;
  };

  return (
    <svg width={500} height={500} className="border-2 rounded-xl bg-gradient-to-br from-slate-950 via-purple-950 to-blue-950">
      {/* Grid background */}
      <defs>
        <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
          <path d="M 50 0 L 0 0 0 50" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="1"/>
        </pattern>
      </defs>
      <rect width="500" height="500" fill="url(#grid)" />
      
      {/* Privacy zones (circles) */}
      {vectors.filter(v => v.type === "privacy-zone").map(zone => (
        <circle
          key={zone.id}
          cx={zone.x}
          cy={zone.y}
          r={60}
          fill={getNodeColor(zone)}
          opacity={0.1}
          stroke={getNodeColor(zone)}
          strokeWidth="1"
          strokeOpacity={0.3}
        />
      ))}
      
      {/* Connection lines from user boundary to gates */}
      {(() => {
        const userBoundary = vectors.find(v => v.type === "user-boundary");
        if (!userBoundary) return null;
        
        return vectors
          .filter(v => v.type === "scw-gate")
          .map(gate => (
            <line
              key={`connection-${gate.id}`}
              x1={userBoundary.x}
              y1={userBoundary.y}
              x2={gate.x}
              y2={gate.y}
              stroke="#ffffff"
              strokeWidth="1"
              opacity={0.2 + Math.sin(animationTime + gate.x * 0.01) * 0.1}
              strokeDasharray="4,4"
            />
          ));
      })()}
      
      {/* Nodes */}
      {vectors.map(vector => {
        const size = getNodeSize(vector);
        const color = getNodeColor(vector);
        const isHovered = hoveredNode === vector.id;
        
        return (
          <g 
            key={vector.id}
            onMouseEnter={() => setHoveredNode(vector.id)}
            onMouseLeave={() => setHoveredNode(null)}
            style={{ cursor: 'pointer' }}
          >
            {/* Outer glow for user boundary */}
            {vector.type === "user-boundary" && (
              <circle
                cx={vector.x}
                cy={vector.y}
                r={size + 15 + Math.sin(animationTime * 2) * 5}
                fill="none"
                stroke={color}
                strokeWidth="2"
                opacity={0.3}
              />
            )}
            
            {/* Main node */}
            <circle
              cx={vector.x}
              cy={vector.y}
              r={size}
              fill={color}
              opacity={isHovered ? 0.9 : 0.7}
              stroke="white"
              strokeWidth={isHovered ? 3 : 2}
            />
            
            {/* Icon for node type */}
            <text
              x={vector.x}
              y={vector.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-xs font-bold fill-white"
              opacity={0.9}
            >
              {vector.type === "user-boundary" ? "🛡️" : 
               vector.type === "scw-gate" ? "🔒" :
               vector.type === "privacy-zone" ? "🌐" : "📢"}
            </text>
            
            {/* Label */}
            <text
              x={vector.x}
              y={vector.y - size - 8}
              textAnchor="middle"
              className="text-xs fill-white font-medium"
              opacity={isHovered ? 1 : 0.8}
            >
              {vector.label}
            </text>
            
            {/* Privacy level indicator */}
            {isHovered && (
              <text
                x={vector.x}
                y={vector.y + size + 15}
                textAnchor="middle"
                className="text-xs fill-green-300 font-bold"
              >
                Privacy: {vector.privacyLevel}%
              </text>
            )}
          </g>
        );
      })}
      
      {/* Legend */}
      <g transform="translate(10, 10)">
        <rect width="160" height="120" fill="black" fillOpacity="0.8" rx="8" />
        <text x="10" y="20" className="text-xs fill-white font-bold">Privacy Boundaries</text>
        
        <circle cx="20" cy="35" r="5" fill="#10b981" />
        <text x="30" y="40" className="text-xs fill-white">High Privacy (80+)</text>
        
        <circle cx="20" cy="55" r="5" fill="#3b82f6" />
        <text x="30" y="60" className="text-xs fill-white">Medium (60-79)</text>
        
        <circle cx="20" cy="75" r="5" fill="#f59e0b" />
        <text x="30" y="80" className="text-xs fill-white">Low (40-59)</text>
        
        <circle cx="20" cy="95" r="5" fill="#ef4444" />
        <text x="30" y="100" className="text-xs fill-white">Minimal (&lt;40)</text>
      </g>
    </svg>
  );
};

const PrivacyScoreGauge: React.FC<{ score: number }> = ({ score }) => {
  const getScoreColor = (score: number): string => {
    if (score >= 80) return "#10b981";
    if (score >= 60) return "#3b82f6";
    if (score >= 40) return "#f59e0b";
    return "#ef4444";
  };
  
  const getScoreLabel = (score: number): string => {
    if (score >= 80) return "Excellent Privacy";
    if (score >= 60) return "Good Privacy";
    if (score >= 40) return "Moderate Privacy";
    return "Low Privacy";
  };
  
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  
  return (
    <div className="flex flex-col items-center gap-3">
      <svg width="120" height="120" className="transform -rotate-90">
        <circle
          cx="60"
          cy="60"
          r="45"
          stroke="#e5e7eb"
          strokeWidth="10"
          fill="none"
        />
        <circle
          cx="60"
          cy="60"
          r="45"
          stroke={getScoreColor(score)}
          strokeWidth="10"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
        <text
          x="60"
          y="60"
          textAnchor="middle"
          dominantBaseline="middle"
          className="text-2xl font-bold fill-current transform rotate-90"
          style={{ transformOrigin: '60px 60px' }}
        >
          {score}
        </text>
      </svg>
      <div className="text-center">
        <div className="text-lg font-semibold" style={{ color: getScoreColor(score) }}>
          {getScoreLabel(score)}
        </div>
        <div className="text-xs text-muted-foreground">Privacy Protection Score</div>
      </div>
    </div>
  );
};

const DataSharingRadar: React.FC<{ profile: UserAdProfile }> = ({ profile }) => {
  const data = [
    { category: 'Conversation', value: profile.dataControls.shareConversationTopics ? 100 : 0 },
    { category: 'Search', value: profile.dataControls.shareSearchHistory ? 100 : 0 },
    { category: 'Interactions', value: profile.dataControls.shareInteractionPatterns ? 100 : 0 },
    { category: 'Personalization', value: profile.dataControls.allowPersonalization ? 100 : 0 }
  ];
  
  return (
    <ResponsiveContainer width="100%" height={250}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e5e7eb" />
        <PolarAngleAxis dataKey="category" tick={{ fontSize: 12 }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
        <Radar
          name="Data Sharing"
          dataKey="value"
          stroke="#3b82f6"
          fill="#3b82f6"
          fillOpacity={0.6}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
};

// ============================================================================
// PAGE COMPONENTS
// ============================================================================

const PrivacyControlsPage: React.FC = () => {
  const { 
    userProfile, 
    privacyScore,
    updatePrivacyLevel, 
    updateDataControl, 
    updateSessionLimit 
  } = useApp();
  
  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Privacy Level Configuration
          </CardTitle>
          <CardDescription>
            Choose your baseline privacy settings. These control how ChatGPT shares your data with advertisers.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4">
            {PRIVACY_LEVELS.map(level => (
              <Card 
                key={level.id}
                className={`cursor-pointer transition-all ${
                  userProfile.privacyLevel === level.id 
                    ? 'ring-2 ring-primary shadow-lg' 
                    : 'hover:shadow-md'
                }`}
                onClick={() => updatePrivacyLevel(level.id)}
              >
                <CardHeader>
                  <CardTitle className="text-sm flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full" 
                      style={{ backgroundColor: level.color }}
                    />
                    {level.name}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {level.description}
                  </CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
          
          <Separator />
          
          <div className="space-y-4">
            <Label className="text-base">Data Sharing Controls</Label>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="flex items-center justify-between p-3 border rounded-lg">
                <div className="space-y-1">
                  <Label className="text-sm">Conversation Topics</Label>
                  <div className="text-xs text-muted-foreground">
                    Share current conversation context
                  </div>
                </div>
                <Switch
                  checked={userProfile.dataControls.shareConversationTopics}
                  onCheckedChange={(v) => updateDataControl('shareConversationTopics', v)}
                />
              </div>
              
              <div className="flex items-center justify-between p-3 border rounded-lg">
                <div className="space-y-1">
                  <Label className="text-sm">Search History</Label>
                  <div className="text-xs text-muted-foreground">
                    Share past search patterns
                  </div>
                </div>
                <Switch
                  checked={userProfile.dataControls.shareSearchHistory}
                  onCheckedChange={(v) => updateDataControl('shareSearchHistory', v)}
                />
              </div>
              
              <div className="flex items-center justify-between p-3 border rounded-lg">
                <div className="space-y-1">
                  <Label className="text-sm">Interaction Patterns</Label>
                  <div className="text-xs text-muted-foreground">
                    Share behavioral data
                  </div>
                </div>
                <Switch
                  checked={userProfile.dataControls.shareInteractionPatterns}
                  onCheckedChange={(v) => updateDataControl('shareInteractionPatterns', v)}
                />
              </div>
              
              <div className="flex items-center justify-between p-3 border rounded-lg">
                <div className="space-y-1">
                  <Label className="text-sm">Allow Personalization</Label>
                  <div className="text-xs text-muted-foreground">
                    Enable targeted ads
                  </div>
                </div>
                <Switch
                  checked={userProfile.dataControls.allowPersonalization}
                  onCheckedChange={(v) => updateDataControl('allowPersonalization', v)}
                />
              </div>
            </div>
          </div>
          
          <Separator />
          
          <div className="space-y-4">
            <Label className="text-base">Session Limits</Label>
            <div className="space-y-4">
              <div>
                <Label className="text-sm">Max Ads Per Hour: {userProfile.sessionLimits.maxAdsPerHour}</Label>
                <Slider
                  value={[userProfile.sessionLimits.maxAdsPerHour]}
                  min={0}
                  max={20}
                  step={1}
                  onValueChange={([v]) => updateSessionLimit('maxAdsPerHour', v)}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label className="text-sm">Max Ads Per Day: {userProfile.sessionLimits.maxAdsPerDay}</Label>
                <Slider
                  value={[userProfile.sessionLimits.maxAdsPerDay]}
                  min={0}
                  max={100}
                  step={5}
                  onValueChange={([v]) => updateSessionLimit('maxAdsPerDay', v)}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label className="text-sm">Min Relevance Threshold: {userProfile.sessionLimits.minRelevanceThreshold}%</Label>
                <Slider
                  value={[userProfile.sessionLimits.minRelevanceThreshold]}
                  min={0}
                  max={100}
                  step={5}
                  onValueChange={([v]) => updateSessionLimit('minRelevanceThreshold', v)}
                  className="mt-2"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Privacy Score
            </CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center">
            <PrivacyScoreGauge score={privacyScore} />
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="h-4 w-4" />
              Data Sharing Radar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DataSharingRadar profile={userProfile} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const SCWGatesPage: React.FC = () => {
  const { userProfile, updateGate, createNewGate, deleteGate } = useApp();
  const [selectedGate, setSelectedGate] = useState<string | null>(null);
  
  const gate = selectedGate ? userProfile.scwGates.find(g => g.id === selectedGate) : null;
  
  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="h-5 w-5" />
            SCW Privacy Gates
          </CardTitle>
          <CardDescription>
            Create privacy containers for different conversation types. Each gate controls ad exposure independently.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Button onClick={createNewGate} className="w-full">
              <Layers className="h-4 w-4 mr-2" />
              Create New Privacy Gate
            </Button>
          </div>
          
          <div className="grid gap-3">
            {userProfile.scwGates.map(g => (
              <Card 
                key={g.id}
                className={`cursor-pointer transition-all ${
                  selectedGate === g.id ? 'ring-2 ring-primary' : 'hover:shadow-md'
                }`}
                onClick={() => setSelectedGate(g.id)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Badge variant={
                        g.gateType === "block" ? "destructive" :
                        g.gateType === "review" ? "secondary" : "default"
                      }>
                        {g.gateType}
                      </Badge>
                      {g.name}
                    </CardTitle>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteGate(g.id);
                        if (selectedGate === g.id) setSelectedGate(null);
                      }}
                    >
                      ✕
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <div>Max Ads: {g.maxAdsPerSession}/session</div>
                    <div>Relevance: {g.requireRelevanceScore}%+</div>
                    <div>Memory: {g.memoryTierAccess.length} tier(s)</div>
                    <div>Categories: {g.allowedCategories.length}</div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
      
      <div>
        {gate ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Configure: {gate.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="text-sm">Gate Name</Label>
                <Input
                  value={gate.name}
                  onChange={(e) => updateGate(gate.id, { name: e.target.value })}
                  className="mt-1"
                />
              </div>
              
              <div>
                <Label className="text-sm">Gate Type</Label>
                <Select
                  value={gate.gateType}
                  onValueChange={(v: SCWGateType) => updateGate(gate.id, { gateType: v })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow">Allow (Permissive)</SelectItem>
                    <SelectItem value="contextual">Contextual Only</SelectItem>
                    <SelectItem value="review">Review Required</SelectItem>
                    <SelectItem value="block">Block All Ads</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label className="text-sm">Max Ads Per Session: {gate.maxAdsPerSession}</Label>
                <Slider
                  value={[gate.maxAdsPerSession]}
                  min={0}
                  max={10}
                  step={1}
                  onValueChange={([v]) => updateGate(gate.id, { maxAdsPerSession: v })}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label className="text-sm">Min Relevance: {gate.requireRelevanceScore}%</Label>
                <Slider
                  value={[gate.requireRelevanceScore]}
                  min={0}
                  max={100}
                  step={5}
                  onValueChange={([v]) => updateGate(gate.id, { requireRelevanceScore: v })}
                  className="mt-2"
                />
              </div>
              
              <div className="space-y-2">
                <Label className="text-sm">Allowed Categories</Label>
                <div className="grid grid-cols-2 gap-2">
                  {AD_CATEGORIES.filter(c => c.id !== "none").map(category => (
                    <Button
                      key={category.id}
                      variant={gate.allowedCategories.includes(category.id) ? "default" : "outline"}
                      size="sm"
                      onClick={() => {
                        const allowed = gate.allowedCategories.includes(category.id);
                        updateGate(gate.id, {
                          allowedCategories: allowed
                            ? gate.allowedCategories.filter(c => c !== category.id)
                            : [...gate.allowedCategories, category.id]
                        });
                      }}
                      className="text-xs justify-start h-auto py-2"
                    >
                      {category.icon} {category.label.split(' ')[0]}
                    </Button>
                  ))}
                </div>
              </div>
              
              <Separator />
              
              <div className="space-y-2">
                <Label className="text-sm">Data Sharing (for this gate)</Label>
                <div className="space-y-2">
                  {Object.entries(gate.dataSharing).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between text-xs">
                      <span className="capitalize">{key.replace(/([A-Z])/g, ' $1')}</span>
                      <Switch
                        checked={value}
                        onCheckedChange={(v) => updateGate(gate.id, {
                          dataSharing: { ...gate.dataSharing, [key]: v }
                        })}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Select a privacy gate to configure its settings
            </AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
};

const CategoryPreferencesPage: React.FC = () => {
  const { 
    userProfile, 
    toggleCategory, 
    addInterest, 
    removeInterest,
    addBlockedBrand,
    removeBlockedBrand
  } = useApp();
  
  const [newInterest, setNewInterest] = useState("");
  const [newBrand, setNewBrand] = useState("");
  
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Ad Categories
          </CardTitle>
          <CardDescription>
            Choose which types of advertisements you're willing to see
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3">
            {AD_CATEGORIES.map(category => (
              <Card
                key={category.id}
                className={`cursor-pointer transition-all ${
                  userProfile.allowedCategories.includes(category.id)
                    ? 'ring-2 ring-primary'
                    : 'opacity-70 hover:opacity-100'
                }`}
                onClick={() => toggleCategory(category.id)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{category.icon}</span>
                    <div>
                      <CardTitle className="text-sm">{category.label}</CardTitle>
                      <CardDescription className="text-xs">
                        {userProfile.allowedCategories.includes(category.id) 
                          ? "✓ Enabled" 
                          : "Disabled"}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              Interest Topics
            </CardTitle>
            <CardDescription>
              Help advertisers show you relevant content (optional)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Add interest topic..."
                value={newInterest}
                onChange={(e) => setNewInterest(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newInterest.trim()) {
                    addInterest(newInterest);
                    setNewInterest("");
                  }
                }}
              />
              <Button
                onClick={() => {
                  if (newInterest.trim()) {
                    addInterest(newInterest);
                    setNewInterest("");
                  }
                }}
              >
                Add
              </Button>
            </div>
            
            <div className="flex flex-wrap gap-2">
              {userProfile.interests.map(interest => (
                <Badge key={interest} variant="secondary" className="text-sm">
                  {interest}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-2 h-auto p-0 hover:bg-transparent"
                    onClick={() => removeInterest(interest)}
                  >
                    ✕
                  </Button>
                </Badge>
              ))}
              {userProfile.interests.length === 0 && (
                <div className="text-sm text-muted-foreground">
                  No interests added yet
                </div>
              )}
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <EyeOff className="h-5 w-5" />
              Blocked Brands
            </CardTitle>
            <CardDescription>
              Never see ads from these advertisers
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Add brand to block..."
                value={newBrand}
                onChange={(e) => setNewBrand(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newBrand.trim()) {
                    addBlockedBrand(newBrand);
                    setNewBrand("");
                  }
                }}
              />
              <Button
                onClick={() => {
                  if (newBrand.trim()) {
                    addBlockedBrand(newBrand);
                    setNewBrand("");
                  }
                }}
              >
                Block
              </Button>
            </div>
            
            <div className="flex flex-wrap gap-2">
              {userProfile.blockedBrands.map(brand => (
                <Badge key={brand} variant="destructive" className="text-sm">
                  {brand}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-2 h-auto p-0 hover:bg-transparent"
                    onClick={() => removeBlockedBrand(brand)}
                  >
                    ✕
                  </Button>
                </Badge>
              ))}
              {userProfile.blockedBrands.length === 0 && (
                <div className="text-sm text-muted-foreground">
                  No brands blocked yet
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const AdvertiserViewPage: React.FC = () => {
  const { advertiserView, scwContainers } = useApp();
  
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            What Advertisers Can See
          </CardTitle>
          <CardDescription>
            Privacy-compliant data shared with advertising partners
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <Label className="text-sm font-semibold text-green-600">✓ Accessible Data</Label>
            <div className="mt-2 space-y-3">
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <div className="text-xs font-medium mb-1">Aggregate Topics</div>
                <div className="flex flex-wrap gap-1">
                  {advertiserView.aggregateTopics.length > 0 ? (
                    advertiserView.aggregateTopics.map(topic => (
                      <Badge key={topic} variant="outline" className="text-xs">
                        {topic}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">None shared</span>
                  )}
                </div>
              </div>
              
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <div className="text-xs font-medium mb-1">Anonymized Interests</div>
                <div className="flex flex-wrap gap-1">
                  {advertiserView.anonymizedInterests.length > 0 ? (
                    advertiserView.anonymizedInterests.map(interest => (
                      <Badge key={interest} variant="outline" className="text-xs">
                        {interest}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">None shared</span>
                  )}
                </div>
              </div>
              
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <div className="text-xs font-medium mb-1">Contextual Signals</div>
                <div className="flex flex-wrap gap-1">
                  {advertiserView.contextualSignals.map(signal => (
                    <Badge key={signal} variant="outline" className="text-xs">
                      {signal}
                    </Badge>
                  ))}
                </div>
              </div>
              
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <div className="text-xs font-medium mb-1">Privacy-Compliant Targets</div>
                <div className="flex flex-wrap gap-1">
                  {advertiserView.privacyCompliantTargets.map(target => (
                    <Badge key={target} variant="outline" className="text-xs">
                      {target}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </div>
          
          <Separator />
          
          <div>
            <Label className="text-sm font-semibold text-red-600">✗ Blocked Data</Label>
            <div className="mt-2 p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="text-xs font-medium mb-2">Advertisers CANNOT access:</div>
              <ul className="space-y-1 text-xs text-red-800">
                {advertiserView.cannotAccess.map(item => (
                  <li key={item} className="flex items-start gap-2">
                    <Lock className="h-3 w-3 mt-0.5 flex-shrink-0" />
                    <span className="capitalize">{item.replace(/_/g, ' ')}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Box className="h-5 w-5" />
              Active SCW Containers
            </CardTitle>
            <CardDescription>
              Privacy-isolated conversation containers
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {scwContainers.map(container => (
              <Card key={container.id} className="border-2">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{container.name}</CardTitle>
                    <Badge variant={
                      container.privacyBoundary.isolationLevel === "strict" ? "default" :
                      container.privacyBoundary.isolationLevel === "moderate" ? "secondary" : "outline"
                    }>
                      {container.privacyBoundary.isolationLevel}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <div className="text-xs text-muted-foreground">
                    {container.purpose}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <strong>Memory Tiers:</strong> {container.privacyBoundary.allowedMemoryTiers.length}
                    </div>
                    <div>
                      <strong>Ad Exposure:</strong> {container.privacyBoundary.adExposure}
                    </div>
                    <div className="col-span-2">
                      <strong>Encrypted:</strong> {container.encryptedData ? "Yes ✓" : "No"}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </CardContent>
        </Card>
        
        <Alert className="border-blue-200 bg-blue-50">
          <Shield className="h-4 w-4 text-blue-600" />
          <AlertDescription className="text-blue-800 text-sm">
            <strong>Privacy Guarantee:</strong> Your conversations, identity, and personal data are never 
            shared with advertisers. Only aggregated, anonymized signals are used for contextual ad targeting 
            within the boundaries you define.
          </AlertDescription>
        </Alert>
      </div>
    </div>
  );
};

const LatentSpacePage: React.FC = () => {
  const { latentVectors, scwContainers } = useApp();
  
  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Map className="h-5 w-5" />
            Latent Space Privacy Map
          </CardTitle>
          <CardDescription>
            Visualize your privacy boundaries, SCW gates, and how ads interact with your profile
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          <LatentSpaceVisualization vectors={latentVectors} />
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Brain className="h-4 w-4" />
              Memory Architecture
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {MEMORY_TIERS_CONFIG.map(tier => (
              <div key={tier.id} className="p-2 border rounded-lg">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs font-medium">{tier.id}</div>
                  <Badge 
                    variant="outline" 
                    className="text-xs"
                    style={{ 
                      borderColor: tier.privacyRisk === "Critical" ? "#ef4444" :
                                  tier.privacyRisk === "High" ? "#f59e0b" :
                                  tier.privacyRisk === "Medium" ? "#3b82f6" : "#10b981"
                    }}
                  >
                    {tier.privacyRisk}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">{tier.description}</div>
              </div>
            ))}
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Network className="h-4 w-4" />
              Privacy Boundaries
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="flex items-center justify-between p-2 bg-green-50 border border-green-200 rounded">
              <span>User Privacy Boundary</span>
              <Circle className="h-3 w-3 fill-green-500 text-green-500" />
            </div>
            <div className="flex items-center justify-between p-2 bg-blue-50 border border-blue-200 rounded">
              <span>SCW Gates ({scwContainers.length})</span>
              <Circle className="h-3 w-3 fill-blue-500 text-blue-500" />
            </div>
            <div className="flex items-center justify-between p-2 bg-purple-50 border border-purple-200 rounded">
              <span>Privacy Zones</span>
              <Circle className="h-3 w-3 fill-purple-500 text-purple-500" />
            </div>
            <div className="flex items-center justify-between p-2 bg-orange-50 border border-orange-200 rounded">
              <span>Ad Campaigns (Filtered)</span>
              <Circle className="h-3 w-3 fill-orange-500 text-orange-500" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const ExportImportPage: React.FC = () => {
  const { exportProfile, importProfile, resetToDefaults, privacyScore } = useApp();
  const [importText, setImportText] = useState("");
  const [exportedData, setExportedData] = useState("");
  const [importStatus, setImportStatus] = useState<"idle" | "success" | "error">("idle");
  
  const handleExport = () => {
    const data = exportProfile();
    setExportedData(data);
  };
  
  const handleImport = () => {
    const success = importProfile(importText);
    setImportStatus(success ? "success" : "error");
    if (success) {
      setImportText("");
      setTimeout(() => setImportStatus("idle"), 3000);
    }
  };
  
  const handleDownload = () => {
    const blob = new Blob([exportedData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `maxey0-privacy-profile-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Export Profile
          </CardTitle>
          <CardDescription>
            Download your privacy configuration to share with ChatGPT or save as backup
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert className="border-blue-200 bg-blue-50">
            <Shield className="h-4 w-4 text-blue-600" />
            <AlertDescription className="text-blue-800 text-sm">
              <strong>For ChatGPT Free Users:</strong> Export this profile and include it in your ChatGPT 
              conversation to establish privacy boundaries using Maxey0's SCW architecture.
            </AlertDescription>
          </Alert>
          
          <div className="space-y-2">
            <div className="flex gap-2">
              <Button onClick={handleExport} className="flex-1">
                <FileText className="h-4 w-4 mr-2" />
                Generate Export
              </Button>
              {exportedData && (
                <Button onClick={handleDownload} variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Download JSON
                </Button>
              )}
            </div>
            
            {exportedData && (
              <div className="space-y-2">
                <Label className="text-sm">Privacy Profile (JSON)</Label>
                <Textarea
                  value={exportedData}
                  readOnly
                  className="font-mono text-xs h-64"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(exportedData);
                  }}
                >
                  Copy to Clipboard
                </Button>
              </div>
            )}
          </div>
          
          <div className="p-4 bg-slate-50 border rounded-lg text-xs space-y-2">
            <div className="font-semibold">How to use in ChatGPT:</div>
            <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
              <li>Export your privacy profile using the button above</li>
              <li>Copy the JSON data to your clipboard</li>
              <li>In ChatGPT, paste: "Use this Maxey0 privacy profile: [paste JSON]"</li>
              <li>ChatGPT will respect your SCW privacy boundaries</li>
              <li>Screenshot this interface to include visual reference</li>
            </ol>
          </div>
        </CardContent>
      </Card>
      
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Download className="h-5 w-5" />
              Import Profile
            </CardTitle>
            <CardDescription>
              Load a previously exported privacy configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-sm">Paste Profile JSON</Label>
              <Textarea
                value={importText}
                onChange={(e) => {
                  setImportText(e.target.value);
                  setImportStatus("idle");
                }}
                placeholder='{"version":"1.0.0","timestamp":"...","profile":{...}}'
                className="font-mono text-xs h-32"
              />
            </div>
            
            <Button onClick={handleImport} disabled={!importText.trim()} className="w-full">
              <Upload className="h-4 w-4 mr-2" />
              Import Configuration
            </Button>
            
            {importStatus === "success" && (
              <Alert className="border-green-200 bg-green-50">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <AlertDescription className="text-green-800">
                  Profile imported successfully!
                </AlertDescription>
              </Alert>
            )}
            
            {importStatus === "error" && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  Invalid profile format. Please check the JSON data.
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5" />
              Reset Configuration
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Reset all privacy settings to default values
            </div>
            <Button 
              variant="destructive" 
              onClick={resetToDefaults}
              className="w-full"
            >
              Reset to Defaults
            </Button>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4" />
              Current Privacy Score
            </CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center">
            <PrivacyScoreGauge score={privacyScore} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN APPLICATION
// ============================================================================

export default function Maxey0PrivacyAdPlatform() {
  const [activeTab, setActiveTab] = useState("privacy");
  
  return (
    <AppProvider>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50"
      >
        <div className="container mx-auto p-6 space-y-6 max-w-7xl">
          <header className="space-y-3">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
                  <Shield className="h-8 w-8 text-blue-600" />
                  Maxey0 SCW Privacy Architecture
                </h1>
                <p className="text-muted-foreground max-w-4xl mt-2 leading-relaxed">
                  Privacy-first advertising for ChatGPT free users. Design your privacy boundaries using 
                  Structured Context Windows (SCWs) and export to ChatGPT for transparent, user-controlled ad experiences.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                  <Lock className="h-3 w-3 mr-1" />
                  Privacy-First
                </Badge>
                <Badge variant="outline">ChatGPT Compatible</Badge>
                <Badge variant="outline">Zero Tracking</Badge>
              </div>
            </div>
            
            <Alert className="border-purple-200 bg-purple-50">
              <Brain className="h-4 w-4 text-purple-600" />
              <AlertDescription className="text-purple-800 text-sm">
                <strong>For ChatGPT Users:</strong> Configure your privacy gates, export your profile, and 
                paste it into ChatGPT with instructions to respect your SCW boundaries. Screenshot this interface 
                to provide visual reference for your privacy architecture.
              </AlertDescription>
            </Alert>
          </header>
          
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList className="grid w-full grid-cols-6">
              <TabsTrigger value="privacy" className="flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Privacy
              </TabsTrigger>
              <TabsTrigger value="gates" className="flex items-center gap-2">
                <Lock className="h-4 w-4" />
                SCW Gates
              </TabsTrigger>
              <TabsTrigger value="categories" className="flex items-center gap-2">
                <Filter className="h-4 w-4" />
                Categories
              </TabsTrigger>
              <TabsTrigger value="advertiser" className="flex items-center gap-2">
                <Eye className="h-4 w-4" />
                Advertiser View
              </TabsTrigger>
              <TabsTrigger value="latent" className="flex items-center gap-2">
                <Map className="h-4 w-4" />
                Latent Map
              </TabsTrigger>
              <TabsTrigger value="export" className="flex items-center gap-2">
                <Download className="h-4 w-4" />
                Export/Import
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
                <TabsContent value="privacy">
                  <PrivacyControlsPage />
                </TabsContent>
                
                <TabsContent value="gates">
                  <SCWGatesPage />
                </TabsContent>
                
                <TabsContent value="categories">
                  <CategoryPreferencesPage />
                </TabsContent>
                
                <TabsContent value="advertiser">
                  <AdvertiserViewPage />
                </TabsContent>
                
                <TabsContent value="latent">
                  <LatentSpacePage />
                </TabsContent>
                
                <TabsContent value="export">
                  <ExportImportPage />
                </TabsContent>
              </motion.div>
            </AnimatePresence>
          </Tabs>
          
          <footer className="border-t pt-6 space-y-3">
            <div className="flex justify-between items-center text-xs text-muted-foreground">
              <div>
                Maxey0 SCW Architecture: Privacy-gated advertising with user-controlled boundaries and zero cross-session tracking
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1">
                  <Lock className="h-3 w-3 text-green-500" />
                  <span className="text-green-600">Privacy Protected</span>
                </div>
              </div>
            </div>
            
            <Alert className="border-slate-200 bg-slate-50">
              <Code className="h-4 w-4" />
              <AlertDescription className="text-xs text-slate-700">
                <strong>Architecture:</strong> This interface demonstrates Maxey0's Structured Context Window (SCW) 
                privacy architecture for ChatGPT advertising. Each SCW creates an isolated privacy container with 
                configurable gates that control ad exposure, data sharing, and memory tier access. Export your 
                configuration and provide it to ChatGPT to establish privacy boundaries that advertisers must respect.
              </AlertDescription>
            </Alert>
          </footer>
        </div>
      </motion.div>
    </AppProvider>
  );
}