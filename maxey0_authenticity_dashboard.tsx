import React, { useState, useEffect, useRef } from 'react';
import { Shield, Database, GitBranch, Activity, Lock, Zap, Server, Eye, Terminal, AlertTriangle, CheckCircle, Clock, Layers, Network, Box } from 'lucide-react';

interface MemoryTier {
  id: string;
  name: string;
  type: 'permanent' | 'persistent' | 'episodic' | 'scratchpad';
  size: number;
  accessLatency: number;
  items: number;
  lastSync: number;
  status: 'healthy' | 'degraded' | 'critical';
}

interface SCWLayer {
  id: string;
  name: string;
  type: 'control' | 'data' | 'a2a';
  activeThreads: number;
  throughput: number;
  errorRate: number;
  policies: string[];
}

interface AuthenticityMetric {
  timestamp: number;
  sealIntegrity: number;
  graphConsistency: number;
  determinismScore: number;
  reproducibilityIndex: number;
}

interface Agent {
  id: string;
  name: string;
  personality: string;
  activeThreads: number;
  tasksCompleted: number;
  status: 'active' | 'idle' | 'error';
}

interface Meteorite {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
  trail: Array<{x: number; y: number; opacity: number}>;
}

class Maxey0SimulationEngine {
  private memoryTiers: MemoryTier[];
  private scwLayers: SCWLayer[];
  private agents: Agent[];
  private metrics: AuthenticityMetric[];
  private startTime: number;

  constructor() {
    this.startTime = Date.now();
    this.memoryTiers = this.initializeMemoryTiers();
    this.scwLayers = this.initializeSCWLayers();
    this.agents = this.initializeAgents();
    this.metrics = [];
  }

  private initializeMemoryTiers(): MemoryTier[] {
    return [
      {
        id: 'permanent',
        name: 'Permanent (Pretrained Weights)',
        type: 'permanent',
        size: 137000000000,
        accessLatency: 0.1,
        items: 137000000000,
        lastSync: Date.now(),
        status: 'healthy'
      },
      {
        id: 'persistent',
        name: 'Persistent (Neo4j Graph)',
        type: 'persistent',
        size: 4500000,
        accessLatency: 2.3,
        items: 4500000,
        lastSync: Date.now() - 120000,
        status: 'healthy'
      },
      {
        id: 'episodic',
        name: 'Episodic (Session DAGs)',
        type: 'episodic',
        size: 128000,
        accessLatency: 0.8,
        items: 128000,
        lastSync: Date.now() - 5000,
        status: 'healthy'
      },
      {
        id: 'scratchpad',
        name: 'Scratchpad (Redis Streams)',
        type: 'scratchpad',
        size: 8192,
        accessLatency: 0.05,
        items: 8192,
        lastSync: Date.now() - 100,
        status: 'healthy'
      }
    ];
  }

  private initializeSCWLayers(): SCWLayer[] {
    return [
      {
        id: 'control',
        name: 'Control Plane',
        type: 'control',
        activeThreads: 8,
        throughput: 1250,
        errorRate: 0.0001,
        policies: ['determinism_enforcement', 'observability_trace', 'risk_budget_guard']
      },
      {
        id: 'data',
        name: 'Data Plane',
        type: 'data',
        activeThreads: 24,
        throughput: 8500,
        errorRate: 0.0003,
        policies: ['rag_adapter', 'vector_index', 'cache_policy']
      },
      {
        id: 'a2a',
        name: 'A2A Bridge',
        type: 'a2a',
        activeThreads: 12,
        throughput: 3200,
        errorRate: 0.0002,
        policies: ['agent_comms', 'streaming_protocol', 'triangulation']
      }
    ];
  }

  private initializeAgents(): Agent[] {
    const personalities = [
      'Architect', 'Debugger', 'Optimizer', 'Security', 'Orchestrator',
      'Monitor', 'Planner', 'Executor', 'Validator', 'Synthesizer'
    ];
    return personalities.map((p, i) => ({
      id: `agent_${i}`,
      name: `Maxey-${p}`,
      personality: p,
      activeThreads: Math.floor(Math.random() * 4) + 1,
      tasksCompleted: Math.floor(Math.random() * 500),
      status: (Math.random() > 0.9 ? 'idle' : 'active') as Agent['status']
    }));
  }

  tick(): void {
    const now = Date.now();
    const elapsed = now - this.startTime;

    this.memoryTiers.forEach(tier => {
      const variance = Math.sin(elapsed / 10000) * 0.1;
      tier.items = Math.floor(tier.items * (1 + variance * 0.001));
      tier.accessLatency = tier.accessLatency * (1 + variance * 0.05);
      
      if (Math.random() < 0.01) {
        tier.lastSync = now;
      }

      if (tier.accessLatency > 5 && tier.type === 'persistent') {
        tier.status = 'degraded';
      } else if (tier.accessLatency > 10) {
        tier.status = 'critical';
      } else {
        tier.status = 'healthy';
      }
    });

    this.scwLayers.forEach(layer => {
      layer.activeThreads = Math.max(1, layer.activeThreads + (Math.random() > 0.5 ? 1 : -1));
      layer.throughput = Math.floor(layer.throughput * (1 + (Math.random() - 0.5) * 0.1));
      layer.errorRate = Math.max(0, layer.errorRate + (Math.random() - 0.5) * 0.00001);
    });

    this.agents.forEach(agent => {
      if (Math.random() < 0.1) {
        agent.tasksCompleted += 1;
      }
      if (Math.random() < 0.05) {
        const statuses: Agent['status'][] = ['active', 'idle', 'error'];
        agent.status = statuses[Math.floor(Math.random() * statuses.length)];
      }
    });

    const metric: AuthenticityMetric = {
      timestamp: now,
      sealIntegrity: 0.95 + Math.random() * 0.05,
      graphConsistency: 0.92 + Math.random() * 0.08,
      determinismScore: 0.98 + Math.random() * 0.02,
      reproducibilityIndex: 0.94 + Math.random() * 0.06
    };
    this.metrics.push(metric);
    if (this.metrics.length > 100) {
      this.metrics.shift();
    }
  }

  getMemoryTiers(): MemoryTier[] {
    return this.memoryTiers;
  }

  getSCWLayers(): SCWLayer[] {
    return this.scwLayers;
  }

  getAgents(): Agent[] {
    return this.agents;
  }

  getMetrics(): AuthenticityMetric[] {
    return this.metrics;
  }

  getLatestMetric(): AuthenticityMetric | null {
    return this.metrics.length > 0 ? this.metrics[this.metrics.length - 1] : null;
  }
}

const MetricCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string | number;
  status?: 'healthy' | 'degraded' | 'critical';
  trend?: 'up' | 'down' | 'stable';
}> = ({ icon, label, value, status = 'healthy', trend }) => {
  const statusColors = {
    healthy: '#10b981',
    degraded: '#f59e0b',
    critical: '#ef4444'
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.6)',
      border: `1px solid ${statusColors[status]}33`,
      borderRadius: 8,
      padding: 16,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      backdropFilter: 'blur(8px)'
    }}>
      <div style={{ color: statusColors[status] }}>
        {icon}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</div>
        <div style={{ fontSize: 18, fontWeight: 600, color: '#e2e8f0' }}>{value}</div>
      </div>
      {trend && (
        <div style={{ fontSize: 12, color: trend === 'up' ? '#10b981' : trend === 'down' ? '#ef4444' : '#64748b' }}>
          {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
        </div>
      )}
    </div>
  );
};

const MemoryTierPanel: React.FC<{ tier: MemoryTier }> = ({ tier }) => {
  const statusIcons = {
    healthy: <CheckCircle size={16} />,
    degraded: <AlertTriangle size={16} />,
    critical: <AlertTriangle size={16} />
  };

  const statusColors = {
    healthy: '#10b981',
    degraded: '#f59e0b',
    critical: '#ef4444'
  };

  const formatBytes = (bytes: number): string => {
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)}B`;
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(2)}M`;
    if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(2)}K`;
    return `${bytes}`;
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.4)',
      border: '1px solid rgba(148, 163, 184, 0.2)',
      borderRadius: 8,
      padding: 16,
      marginBottom: 12
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Database size={18} color={statusColors[tier.status]} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>{tier.name}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: statusColors[tier.status] }}>
          {statusIcons[tier.status]}
          <span style={{ fontSize: 12, textTransform: 'uppercase' }}>{tier.status}</span>
        </div>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, fontSize: 12 }}>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Items</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{formatBytes(tier.items)}</div>
        </div>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Latency</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{tier.accessLatency.toFixed(2)}ms</div>
        </div>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Last Sync</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>
            {Math.floor((Date.now() - tier.lastSync) / 1000)}s ago
          </div>
        </div>
      </div>
    </div>
  );
};

const SCWLayerPanel: React.FC<{ layer: SCWLayer }> = ({ layer }) => {
  const layerIcons = {
    control: <Shield size={18} />,
    data: <Server size={18} />,
    a2a: <Network size={18} />
  };

  const layerColors = {
    control: '#8b5cf6',
    data: '#3b82f6',
    a2a: '#06b6d4'
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.4)',
      border: '1px solid rgba(148, 163, 184, 0.2)',
      borderRadius: 8,
      padding: 16,
      marginBottom: 12
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <div style={{ color: layerColors[layer.type] }}>
          {layerIcons[layer.type]}
        </div>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{layer.name}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 12, marginBottom: 12 }}>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Active Threads</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{layer.activeThreads}</div>
        </div>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Throughput</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{layer.throughput}/s</div>
        </div>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Error Rate</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{(layer.errorRate * 100).toFixed(4)}%</div>
        </div>
        <div>
          <div style={{ color: '#64748b', marginBottom: 4 }}>Policies</div>
          <div style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{layer.policies.length}</div>
        </div>
      </div>

      <div style={{ fontSize: 11, color: '#64748b' }}>
        Policies: {layer.policies.join(', ')}
      </div>
    </div>
  );
};

const AgentCard: React.FC<{ agent: Agent }> = ({ agent }) => {
  const statusColors = {
    active: '#10b981',
    idle: '#64748b',
    error: '#ef4444'
  };

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.4)',
      border: '1px solid rgba(148, 163, 184, 0.2)',
      borderRadius: 8,
      padding: 12
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: statusColors[agent.status],
          boxShadow: `0 0 8px ${statusColors[agent.status]}`
        }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>{agent.name}</span>
      </div>
      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>
        {agent.personality}
      </div>
      <div style={{ display: 'flex', gap: 12, fontSize: 11 }}>
        <div>
          <span style={{ color: '#64748b' }}>Threads: </span>
          <span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{agent.activeThreads}</span>
        </div>
        <div>
          <span style={{ color: '#64748b' }}>Tasks: </span>
          <span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{agent.tasksCompleted}</span>
        </div>
      </div>
    </div>
  );
};

const MeteoriteField: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const meteoritesRef = useRef<Meteorite[]>([]);
  const animationRef = useRef<number>();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resizeCanvas = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    for (let i = 0; i < 20; i++) {
      meteoritesRef.current.push({
        id: i,
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 2,
        vy: (Math.random() - 0.5) * 2,
        size: Math.random() * 3 + 1,
        opacity: Math.random() * 0.5 + 0.3,
        trail: []
      });
    }

    const animate = () => {
      ctx.fillStyle = 'rgba(10, 14, 26, 0.1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      meteoritesRef.current.forEach(m => {
        m.x += m.vx;
        m.y += m.vy;

        if (m.x < 0) m.x = canvas.width;
        if (m.x > canvas.width) m.x = 0;
        if (m.y < 0) m.y = canvas.height;
        if (m.y > canvas.height) m.y = 0;

        m.trail.push({ x: m.x, y: m.y, opacity: m.opacity });
        if (m.trail.length > 15) m.trail.shift();

        m.trail.forEach((point, idx) => {
          const trailOpacity = (idx / m.trail.length) * point.opacity;
          ctx.fillStyle = `rgba(139, 92, 246, ${trailOpacity})`;
          ctx.beginPath();
          ctx.arc(point.x, point.y, m.size * (idx / m.trail.length), 0, Math.PI * 2);
          ctx.fill();
        });

        const gradient = ctx.createRadialGradient(m.x, m.y, 0, m.x, m.y, m.size);
        gradient.addColorStop(0, `rgba(167, 139, 250, ${m.opacity})`);
        gradient.addColorStop(1, `rgba(139, 92, 246, 0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.size, 0, Math.PI * 2);
        ctx.fill();
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        opacity: 0.6
      }}
    />
  );
};

const AuthenticityChart: React.FC<{ metrics: AuthenticityMetric[] }> = ({ metrics }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || metrics.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const padding = 40;
    const chartWidth = canvas.width - padding * 2;
    const chartHeight = canvas.height - padding * 2;

    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, canvas.height - padding);
    ctx.lineTo(canvas.width - padding, canvas.height - padding);
    ctx.stroke();

    ctx.strokeStyle = '#1e293b';
    for (let i = 0; i <= 5; i++) {
      const y = padding + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(canvas.width - padding, y);
      ctx.stroke();
    }

    const metricKeys: (keyof Pick<AuthenticityMetric, 'sealIntegrity' | 'graphConsistency' | 'determinismScore' | 'reproducibilityIndex'>)[] = [
      'sealIntegrity',
      'graphConsistency',
      'determinismScore',
      'reproducibilityIndex'
    ];
    const colors = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b'];

    metricKeys.forEach((key, keyIdx) => {
      ctx.strokeStyle = colors[keyIdx];
      ctx.lineWidth = 2;
      ctx.beginPath();

      metrics.forEach((metric, idx) => {
        const x = padding + (chartWidth / (metrics.length - 1)) * idx;
        const value = metric[key];
        const y = canvas.height - padding - (value * chartHeight);

        if (idx === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      });

      ctx.stroke();
    });

    ctx.font = '11px ui-monospace';
    metricKeys.forEach((key, idx) => {
      ctx.fillStyle = colors[idx];
      const x = canvas.width - padding - 180;
      const y = padding + idx * 16;
      ctx.fillRect(x, y, 10, 10);
      ctx.fillStyle = '#94a3b8';
      ctx.fillText(key, x + 15, y + 9);
    });
  }, [metrics]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '100%',
        height: '100%'
      }}
    />
  );
};

export default function App() {
  const engineRef = useRef<Maxey0SimulationEngine | null>(null);
  const [memoryTiers, setMemoryTiers] = useState<MemoryTier[]>([]);
  const [scwLayers, setSCWLayers] = useState<SCWLayer[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [metrics, setMetrics] = useState<AuthenticityMetric[]>([]);
  const [latestMetric, setLatestMetric] = useState<AuthenticityMetric | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'memory' | 'scw' | 'agents' | 'metrics'>('overview');

  useEffect(() => {
    if (!engineRef.current) {
      engineRef.current = new Maxey0SimulationEngine();
    }

    const interval = setInterval(() => {
      if (engineRef.current) {
        engineRef.current.tick();
        setMemoryTiers(engineRef.current.getMemoryTiers());
        setSCWLayers(engineRef.current.getSCWLayers());
        setAgents(engineRef.current.getAgents());
        setMetrics(engineRef.current.getMetrics());
        setLatestMetric(engineRef.current.getLatestMetric());
      }
    }, 100);

    return () => clearInterval(interval);
  }, []);

  const totalThreads = scwLayers.reduce((sum, l) => sum + l.activeThreads, 0);
  const totalThroughput = scwLayers.reduce((sum, l) => sum + l.throughput, 0);
  const activeAgents = agents.filter(a => a.status === 'active').length;
  const avgErrorRate = scwLayers.reduce((sum, l) => sum + l.errorRate, 0) / scwLayers.length;

  return (
    <div style={{
      fontFamily: 'ui-monospace, monospace',
      background: '#0a0e1a',
      color: '#e2e8f0',
      minHeight: '100vh',
      padding: 24,
      position: 'relative',
      overflow: 'hidden'
    }}>
      <MeteoriteField />

      <div style={{ position: 'relative', zIndex: 1, maxWidth: 1400, margin: '0 auto' }}>
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
            <Shield size={32} color="#8b5cf6" />
            <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0, letterSpacing: '-0.5px' }}>
              Maxey0 Authenticity Seal Dashboard
            </h1>
          </div>
          <div style={{ fontSize: 13, color: '#64748b', fontFamily: 'monospace' }}>
            Enterprise-grade AI Systems Infrastructure · Memory Tiers · SCW Tracer · Agent Orchestration
          </div>
        </div>

        <div style={{
          display: 'flex',
          gap: 8,
          marginBottom: 24,
          borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
          paddingBottom: 16
        }}>
          {[
            { id: 'overview', label: 'Overview', icon: <Activity size={16} /> },
            { id: 'memory', label: 'Memory Tiers', icon: <Database size={16} /> },
            { id: 'scw', label: 'SCW Layers', icon: <Layers size={16} /> },
            { id: 'agents', label: 'Agents', icon: <Network size={16} /> },
            { id: 'metrics', label: 'Authenticity', icon: <Shield size={16} /> }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                background: activeTab === tab.id ? 'rgba(139, 92, 246, 0.2)' : 'transparent',
                border: activeTab === tab.id ? '1px solid #8b5cf6' : '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: 6,
                padding: '8px 16px',
                color: activeTab === tab.id ? '#c4b5fd' : '#94a3b8',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 13,
                fontFamily: 'ui-monospace',
                transition: 'all 0.2s'
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
              <MetricCard
                icon={<Activity size={20} />}
                label="Active Threads"
                value={totalThreads}
                status="healthy"
                trend="stable"
              />
              <MetricCard
                icon={<Zap size={20} />}
                label="Total Throughput"
                value={`${totalThroughput.toLocaleString()}/s`}
                status="healthy"
                trend="up"
              />
              <MetricCard
                icon={<Network size={20} />}
                label="Active Agents"
                value={`${activeAgents}/${agents.length}`}
                status="healthy"
                trend="stable"
              />
              <MetricCard
                icon={<AlertTriangle size={20} />}
                label="Avg Error Rate"
                value={`${(avgErrorRate * 100).toFixed(4)}%`}
                status={avgErrorRate > 0.001 ? 'degraded' : 'healthy'}
                trend="down"
              />
              {latestMetric && (
                <>
                  <MetricCard
                    icon={<Shield size={20} />}
                    label="Seal Integrity"
                    value={`${(latestMetric.sealIntegrity * 100).toFixed(2)}%`}
                    status="healthy"
                  />
                  <MetricCard
                    icon={<CheckCircle size={20} />}
                    label="Determinism Score"
                    value={`${(latestMetric.determinismScore * 100).toFixed(2)}%`}
                    status="healthy"
                  />
                </>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
              <div style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: 12,
                padding: 20
              }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Database size={18} />
                  Memory Tier Status
                </h3>
                <div style={{ height: 200, overflowY: 'auto' }}>
                  {memoryTiers.slice(0, 2).map(tier => (
                    <MemoryTierPanel key={tier.id} tier={tier} />
                  ))}
                </div>
              </div>

              <div style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: 12,
                padding: 20
              }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Layers size={18} />
                  SCW Layer Status
                </h3>
                <div style={{ height: 200, overflowY: 'auto' }}>
                  {scwLayers.map(layer => (
                    <div key={layer.id} style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '12px 0',
                      borderBottom: '1px solid rgba(148, 163, 184, 0.1)'
                    }}>
                      <span style={{ fontSize: 13 }}>{layer.name}</span>
                      <span style={{ fontSize: 13, fontFamily: 'monospace', color: '#64748b' }}>
                        {layer.activeThreads} threads · {layer.throughput}/s
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              padding: 20,
              marginTop: 24
            }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Activity size={18} />
                Live Authenticity Metrics
              </h3>
              <div style={{ height: 300 }}>
                <AuthenticityChart metrics={metrics} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'memory' && (
          <div>
            <div style={{
              background: 'rgba(139, 92, 246, 0.1)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              fontSize: 13,
              color: '#c4b5fd'
            }}>
              <strong>Memory Tier Architecture:</strong> Hierarchical storage system with explicit promotion/demotion policies.
              Permanent (pretrained) → Persistent (Neo4j graph) → Episodic (session DAGs) → Scratchpad (Redis streams).
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
              {memoryTiers.map(tier => (
                <MemoryTierPanel key={tier.id} tier={tier} />
              ))}
            </div>

            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              padding: 20,
              marginTop: 24
            }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Memory Hierarchy Visualization</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, justifyContent: 'center', padding: 40 }}>
                {memoryTiers.map((tier, idx) => (
                  <React.Fragment key={tier.id}>
                    <div style={{
                      background: `rgba(139, 92, 246, ${0.1 + idx * 0.15})`,
                      border: '2px solid rgba(139, 92, 246, 0.5)',
                      borderRadius: 8,
                      padding: 20,
                      textAlign: 'center',
                      minWidth: 120
                    }}>
                      <Database size={24} style={{ margin: '0 auto 8px' }} />
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{tier.type.toUpperCase()}</div>
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                        {tier.accessLatency.toFixed(2)}ms
                      </div>
                    </div>
                    {idx < memoryTiers.length - 1 && (
                      <div style={{ fontSize: 20, color: '#64748b' }}>→</div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'scw' && (
          <div>
            <div style={{
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              fontSize: 13,
              color: '#93c5fd'
            }}>
              <strong>Structured Context Windows (SCW):</strong> Composable, testable, graph-traceable execution layers.
              Control Plane (policies, observability) → Data Plane (RAG, tools, LM) → A2A Bridge (agent comms).
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
              {scwLayers.map(layer => (
                <SCWLayerPanel key={layer.id} layer={layer} />
              ))}
            </div>

            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              padding: 20,
              marginTop: 24
            }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>SCW Thread Distribution</h3>
              <div style={{ height: 200 }}>
                {scwLayers.map(layer => {
                  const maxThreads = Math.max(...scwLayers.map(l => l.activeThreads));
                  const width = (layer.activeThreads / maxThreads) * 100;
                  const colors = {
                    control: '#8b5cf6',
                    data: '#3b82f6',
                    a2a: '#06b6d4'
                  };
                  return (
                    <div key={layer.id} style={{ marginBottom: 20 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 13 }}>
                        <span>{layer.name}</span>
                        <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{layer.activeThreads} threads</span>
                      </div>
                      <div style={{ background: 'rgba(148, 163, 184, 0.1)', borderRadius: 4, height: 24, position: 'relative' }}>
                        <div style={{
                          background: colors[layer.type],
                          height: '100%',
                          width: `${width}%`,
                          borderRadius: 4,
                          transition: 'width 0.3s ease'
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'agents' && (
          <div>
            <div style={{
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              fontSize: 13,
              color: '#6ee7b7'
            }}>
              <strong>Maxey Agent Network:</strong> 120+ specialized agent personalities orchestrated via A2A Bridge protocol.
              Each agent operates within SCW threads with deterministic, observable behavior.
            </div>

            <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
              <div style={{ padding: '6px 12px', background: 'rgba(16, 185, 129, 0.2)', borderRadius: 6 }}>
                <span style={{ color: '#64748b' }}>Active: </span>
                <span style={{ fontFamily: 'monospace', color: '#10b981' }}>{activeAgents}</span>
              </div>
              <div style={{ padding: '6px 12px', background: 'rgba(100, 116, 139, 0.2)', borderRadius: 6 }}>
                <span style={{ color: '#64748b' }}>Idle: </span>
                <span style={{ fontFamily: 'monospace', color: '#94a3b8' }}>
                  {agents.filter(a => a.status === 'idle').length}
                </span>
              </div>
              <div style={{ padding: '6px 12px', background: 'rgba(239, 68, 68, 0.2)', borderRadius: 6 }}>
                <span style={{ color: '#64748b' }}>Error: </span>
                <span style={{ fontFamily: 'monospace', color: '#ef4444' }}>
                  {agents.filter(a => a.status === 'error').length}
                </span>
              </div>
              <div style={{ padding: '6px 12px', background: 'rgba(139, 92, 246, 0.2)', borderRadius: 6 }}>
                <span style={{ color: '#64748b' }}>Total Tasks: </span>
                <span style={{ fontFamily: 'monospace', color: '#c4b5fd' }}>
                  {agents.reduce((sum, a) => sum + a.tasksCompleted, 0)}
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
              {agents.map(agent => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </div>
          </div>
        )}

        {activeTab === 'metrics' && (
          <div>
            <div style={{
              background: 'rgba(139, 92, 246, 0.1)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
              fontSize: 13,
              color: '#c4b5fd'
            }}>
              <strong>Authenticity Seal Verification:</strong> Real-time monitoring of system integrity, determinism,
              and reproducibility across all execution layers. Metrics enforce correctness over convenience.
            </div>

            {latestMetric && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
                <MetricCard
                  icon={<Shield size={20} />}
                  label="Seal Integrity"
                  value={`${(latestMetric.sealIntegrity * 100).toFixed(3)}%`}
                  status={latestMetric.sealIntegrity > 0.95 ? 'healthy' : 'degraded'}
                />
                <MetricCard
                  icon={<GitBranch size={20} />}
                  label="Graph Consistency"
                  value={`${(latestMetric.graphConsistency * 100).toFixed(3)}%`}
                  status={latestMetric.graphConsistency > 0.92 ? 'healthy' : 'degraded'}
                />
                <MetricCard
                  icon={<Lock size={20} />}
                  label="Determinism Score"
                  value={`${(latestMetric.determinismScore * 100).toFixed(3)}%`}
                  status={latestMetric.determinismScore > 0.98 ? 'healthy' : 'critical'}
                />
                <MetricCard
                  icon={<CheckCircle size={20} />}
                  label="Reproducibility Index"
                  value={`${(latestMetric.reproducibilityIndex * 100).toFixed(3)}%`}
                  status={latestMetric.reproducibilityIndex > 0.94 ? 'healthy' : 'degraded'}
                />
              </div>
            )}

            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              padding: 20,
              marginBottom: 24
            }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Historical Authenticity Trends</h3>
              <div style={{ height: 400 }}>
                <AuthenticityChart metrics={metrics} />
              </div>
            </div>

            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              padding: 20
            }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Verification Protocol</h3>
              <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.8 }}>
                <div style={{ marginBottom: 12 }}>
                  <strong style={{ color: '#c4b5fd' }}>1. Seal Integrity:</strong> Cryptographic verification of
                  execution traces against canonical graph state. Detects tampering, drift, and unauthorized mutations.
                </div>
                <div style={{ marginBottom: 12 }}>
                  <strong style={{ color: '#c4b5fd' }}>2. Graph Consistency:</strong> Neo4j ACID compliance checks,
                  vector index coherence, and relationship integrity across memory tiers.
                </div>
                <div style={{ marginBottom: 12 }}>
                  <strong style={{ color: '#c4b5fd' }}>3. Determinism Score:</strong> Reproducibility validation for
                  agent executions, LM calls, and tool invocations. Enforces idempotent operations.
                </div>
                <div>
                  <strong style={{ color: '#c4b5fd' }}>4. Reproducibility Index:</strong> End-to-end verification
                  that identical inputs produce identical outputs across all system layers.
                </div>
              </div>
            </div>
          </div>
        )}

        <div style={{
          marginTop: 40,
          paddingTop: 24,
          borderTop: '1px solid rgba(148, 163, 184, 0.2)',
          fontSize: 12,
          color: '#64748b',
          textAlign: 'center'
        }}>
          <div style={{ marginBottom: 8 }}>
            Maxey0 Authenticity Seal Dashboard v1.0.0 · TokenlessAI/Maxey0
          </div>
          <div style={{ fontFamily: 'monospace' }}>
            Precision &gt; Brevity · Determinism · Reproducibility · Correctness
          </div>
        </div>
      </div>
    </div>
  );
}