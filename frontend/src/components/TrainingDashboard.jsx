/**
 * Training UI - React Frontend Components
 * 
 * Real-time monitoring, review queue management, and metrics dashboard
 * for the autonomous training agent system.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';


// ============================================================================
// API HOOKS
// ============================================================================

/**
 * Hook to fetch agent status with auto-refresh
 */
export const useAgentStatus = (refreshInterval = 5000) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/training/status');
        if (!response.ok) throw new Error('Failed to fetch status');
        const data = await response.json();
        setStatus(data);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  return { status, loading, error };
};


/**
 * Hook to fetch review queue
 */
export const useReviewQueue = (refreshInterval = 10000) => {
  const [queue, setQueue] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const [queueRes, statsRes] = await Promise.all([
          fetch('/api/training/review-queue'),
          fetch('/api/training/review-queue/stats'),
        ]);
        
        const queueData = await queueRes.json();
        const statsData = await statsRes.json();
        
        setQueue(queueData);
        setStats(statsData);
      } catch (err) {
        console.error('Error fetching queue:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchQueue();
    const interval = setInterval(fetchQueue, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  return { queue, stats, loading };
};


/**
 * Hook to fetch system state
 */
export const useSystemState = (refreshInterval = 5000) => {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchState = async () => {
      try {
        const response = await fetch('/api/training/system-state');
        if (response.ok) {
          const data = await response.json();
          setState(data);
        }
      } catch (err) {
        console.error('Error fetching system state:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  return { state, loading };
};


/**
 * Hook to fetch metrics history
 */
export const useMetricsHistory = (limit = 100) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await fetch(`/api/training/metrics/history?limit=${limit}`);
        const data = await response.json();
        setHistory(data);
      } catch (err) {
        console.error('Error fetching metrics:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [limit]);

  return { history, loading };
};


// ============================================================================
// INDICATOR COMPONENTS
// ============================================================================

/**
 * Status indicator with color coding
 */
export const StatusIndicator = ({ label, value, target, isPercentage = false }) => {
  let status = 'unknown';
  let color = 'gray';

  if (value >= target) {
    status = 'good';
    color = 'green';
  } else if (value >= target * 0.9) {
    status = 'warning';
    color = 'yellow';
  } else {
    status = 'critical';
    color = 'red';
  }

  return (
    <div className="metric-card" style={{ borderLeft: `4px solid ${color}` }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {isPercentage ? `${(value * 100).toFixed(1)}%` : value.toFixed(4)}
      </div>
      <div className="metric-target">
        Target: {isPercentage ? `${(target * 100).toFixed(1)}%` : target.toFixed(4)}
      </div>
      <div className={`metric-status status-${status}`}>
        {status.toUpperCase()}
      </div>
    </div>
  );
};


/**
 * Progress bar with target indicator
 */
export const ProgressBar = ({ current, target, label }) => {
  const percentage = Math.min((current / target) * 100, 100);
  
  return (
    <div className="progress-container">
      <div className="progress-label">
        {label}: {current} / {target}
      </div>
      <div className="progress-bar">
        <div 
          className="progress-fill"
          style={{ 
            width: `${percentage}%`,
            backgroundColor: percentage >= 100 ? '#22c55e' : '#3b82f6'
          }}
        />
      </div>
      {percentage >= 100 && <span className="progress-ready">✓ Ready for Training</span>}
    </div>
  );
};


/**
 * Gap priority badge
 */
export const GapBadge = ({ gap }) => {
  const deficit = gap.threshold - gap.current_score;
  const urgency = gap.priority;

  return (
    <div className="gap-badge">
      <div className="gap-type">{gap.gap_type}</div>
      <div className="gap-name">{gap.name}</div>
      <div className="gap-scores">
        Current: {gap.current_score.toFixed(3)} / {gap.threshold.toFixed(3)}
      </div>
      <div className="gap-urgency">
        Priority: {urgency}/10
      </div>
      <div className="gap-action">
        {gap.suggested_data_source} ({gap.estimated_documents_needed} docs)
      </div>
    </div>
  );
};


// ============================================================================
// DASHBOARD COMPONENTS
// ============================================================================

/**
 * System State Overview
 */
export const SystemStateCard = () => {
  const { state, loading } = useSystemState();

  if (loading) return <div className="card loading">Loading system state...</div>;
  if (!state) return <div className="card error">System state unavailable</div>;

  return (
    <div className="card system-state">
      <h2>System State</h2>
      
      <div className="metrics-grid">
        <StatusIndicator 
          label="Intent Stability"
          value={state.intent_stability_score}
          target={0.85}
        />
        <StatusIndicator 
          label="Provider Dependency"
          value={1 - state.provider_dependency_rate}  // Lower is better
          target={0.85}
        />
        <StatusIndicator 
          label="Retrieval Accuracy"
          value={state.retrieval_accuracy}
          target={0.80}
          isPercentage={true}
        />
        <StatusIndicator 
          label="World Model Confidence"
          value={state.world_model_confidence_avg}
          target={0.75}
        />
      </div>

      <div className="coverage-section">
        <h3>Language Coverage</h3>
        <div className="coverage-grid">
          {Object.entries(state.language_variant_scores).map(([lang, score]) => (
            <div key={lang} className="coverage-item">
              <span className="lang-code">{lang.toUpperCase()}</span>
              <div className="coverage-bar">
                <div 
                  className="coverage-fill"
                  style={{ width: `${Math.min(score * 100, 100)}%` }}
                />
              </div>
              <span className="coverage-value">{(score * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="coverage-section">
        <h3>Domain Coverage</h3>
        <div className="coverage-grid">
          {Object.entries(state.domain_coverage).map(([domain, score]) => (
            <div key={domain} className="coverage-item">
              <span className="domain-name">{domain}</span>
              <div className="coverage-bar">
                <div 
                  className="coverage-fill"
                  style={{ width: `${Math.min(score * 100, 100)}%` }}
                />
              </div>
              <span className="coverage-value">{(score * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};


/**
 * Agent Status and Control
 */
export const AgentStatusCard = () => {
  const { status, loading } = useAgentStatus();
  const [controlling, setControlling] = useState(false);

  const handleStart = async () => {
    setControlling(true);
    try {
      await fetch('/api/training/agent/start', { method: 'POST' });
    } finally {
      setControlling(false);
    }
  };

  const handleStop = async () => {
    setControlling(true);
    try {
      await fetch('/api/training/agent/stop', { method: 'POST' });
    } finally {
      setControlling(false);
    }
  };

  if (loading) return <div className="card loading">Loading agent status...</div>;

  return (
    <div className="card agent-status">
      <h2>Agent Status</h2>
      
      <div className="status-display">
        <div className={`status-indicator ${status?.is_running ? 'running' : 'stopped'}`} />
        <span className="status-text">
          {status?.is_running ? 'RUNNING' : 'STOPPED'}
        </span>
      </div>

      <div className="status-details">
        <div className="status-item">
          <span className="label">Current Cycle:</span>
          <span className="value">#{status?.current_cycle}</span>
        </div>
        <div className="status-item">
          <span className="label">Ingestion History:</span>
          <span className="value">{status?.ingestion_history_count} cycles</span>
        </div>
        <div className="status-item">
          <span className="label">Training Cycles:</span>
          <span className="value">{status?.training_cycles_count} deployments</span>
        </div>
      </div>

      {status?.current_cycle > 0 && status?.system_state && (
        <div className="quick-metrics">
          <div className="quick-metric">
            <span className="metric-label">Intent Stability</span>
            <span className="metric-value">
              {status.system_state.intent_stability_score.toFixed(4)}
            </span>
          </div>
          <div className="quick-metric">
            <span className="metric-label">SPPE Ready</span>
            <span className="metric-value">
              {status.system_state.sppe_pairs_ready}
            </span>
          </div>
          <div className="quick-metric">
            <span className="metric-label">Review Queue</span>
            <span className="metric-value">
              {status.system_state.review_queue_depth}
            </span>
          </div>
        </div>
      )}

      <div className="agent-controls">
        {!status?.is_running ? (
          <button 
            className="btn btn-success"
            onClick={handleStart}
            disabled={controlling}
          >
            {controlling ? 'Starting...' : 'Start Agent'}
          </button>
        ) : (
          <button 
            className="btn btn-danger"
            onClick={handleStop}
            disabled={controlling}
          >
            {controlling ? 'Stopping...' : 'Stop Agent'}
          </button>
        )}
      </div>
    </div>
  );
};


/**
 * Identified Gaps Display
 */
export const IdentifiedGapsCard = () => {
  const { status, loading } = useAgentStatus();

  if (loading) return <div className="card loading">Loading gaps...</div>;
  if (!status?.identified_gaps?.length) {
    return <div className="card info">No gaps identified yet</div>;
  }

  return (
    <div className="card gaps-display">
      <h2>Identified Gaps (Top Priority)</h2>
      <div className="gaps-list">
        {status.identified_gaps.map((gap, idx) => (
          <GapBadge key={idx} gap={gap} />
        ))}
      </div>
    </div>
  );
};


/**
 * Review Queue Display
 */
export const ReviewQueueCard = () => {
  const { queue, stats, loading } = useReviewQueue();
  const [selectedItem, setSelectedItem] = useState(null);

  const handleDecision = async (itemId, decision, correction = null) => {
    try {
      await fetch('/api/training/review-queue/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          review_item_id: itemId,
          decision,
          correction,
        }),
      });
      // Refresh queue
      setSelectedItem(null);
    } catch (err) {
      console.error('Error submitting decision:', err);
    }
  };

  if (loading) return <div className="card loading">Loading review queue...</div>;

  return (
    <div className="card review-queue">
      <h2>Review Queue</h2>

      {stats && (
        <div className="queue-stats">
          <div className="stat">
            <span className="stat-label">Pending:</span>
            <span className="stat-value">{stats.total_pending}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Auto-Accepted:</span>
            <span className="stat-value">{stats.auto_accepted}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Corrections:</span>
            <span className="stat-value">{stats.corrections_collected}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Avg Confidence:</span>
            <span className="stat-value">{(stats.avg_confidence * 100).toFixed(1)}%</span>
          </div>
        </div>
      )}

      {queue.length > 0 ? (
        <div className="queue-items">
          {queue.map((item) => (
            <div 
              key={item.item_id}
              className={`queue-item ${selectedItem?.item_id === item.item_id ? 'selected' : ''}`}
              onClick={() => setSelectedItem(item)}
            >
              <div className="item-header">
                <span className="item-type">[{item.item_type.toUpperCase()}]</span>
                <span className="item-confidence">
                  Confidence: {(item.confidence * 100).toFixed(1)}%
                </span>
                <span className={`item-priority priority-${item.priority}`}>
                  Priority: {item.priority}/10
                </span>
              </div>
              
              {selectedItem?.item_id === item.item_id && (
                <div className="item-details">
                  <div className="item-content">
                    {Object.entries(item.content).map(([key, value]) => (
                      <div key={key} className="content-line">
                        <span className="content-key">{key}:</span>
                        <span className="content-value">{String(value).substring(0, 100)}</span>
                      </div>
                    ))}
                  </div>
                  
                  <div className="item-actions">
                    <button 
                      className="btn btn-success"
                      onClick={() => handleDecision(item.item_id, 'accept')}
                    >
                      ✓ Accept
                    </button>
                    <button 
                      className="btn btn-danger"
                      onClick={() => handleDecision(item.item_id, 'reject')}
                    >
                      ✗ Reject
                    </button>
                    <button 
                      className="btn btn-warning"
                      onClick={() => handleDecision(item.item_id, 'correct', { note: 'correction needed' })}
                    >
                      ✎ Correct
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">No items in review queue</div>
      )}
    </div>
  );
};


/**
 * Metrics Chart
 */
export const MetricsChart = () => {
  const { history, loading } = useMetricsHistory();

  if (loading) return <div className="card loading">Loading metrics...</div>;
  if (history.length === 0) return <div className="card info">No metrics data yet</div>;

  const chartData = history.map(s => ({
    timestamp: new Date(s.timestamp).toLocaleTimeString(),
    intent_stability: s.intent_stability,
    retrieval_accuracy: s.retrieval_accuracy,
    world_model_confidence: s.world_model_confidence,
  }));

  return (
    <div className="card metrics-chart">
      <h2>Metrics Trend</h2>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line 
            type="monotone" 
            dataKey="intent_stability" 
            stroke="#8884d8"
            name="Intent Stability"
          />
          <Line 
            type="monotone" 
            dataKey="retrieval_accuracy" 
            stroke="#82ca9d"
            name="Retrieval Accuracy"
          />
          <Line 
            type="monotone" 
            dataKey="world_model_confidence" 
            stroke="#ffc658"
            name="World Model Confidence"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};


/**
 * SPPE Training Batch Progress
 */
export const SPPEBatchProgressCard = () => {
  const { status, loading } = useAgentStatus();

  if (loading || !status?.system_state) {
    return <div className="card loading">Loading batch progress...</div>;
  }

  const targetBatch = 1000; // Minimum SPPE pairs for training
  const current = status.system_state.sppe_pairs_ready;

  return (
    <div className="card sppe-batch">
      <h2>SPPE Training Batch</h2>
      <ProgressBar 
        current={current}
        target={targetBatch}
        label="SPPE Pairs Generated"
      />
      <div className="batch-info">
        <div className="info-item">
          <span className="label">Current Batch:</span>
          <span className="value">{current} / {targetBatch}</span>
        </div>
        <div className="info-item">
          <span className="label">Completion:</span>
          <span className="value">{Math.round((current / targetBatch) * 100)}%</span>
        </div>
        {current >= targetBatch && (
          <div className="info-item ready">
            <span className="ready-indicator">✓</span>
            <span className="ready-text">Ready for training</span>
          </div>
        )}
      </div>
    </div>
  );
};


/**
 * Main Training Dashboard
 */
export const TrainingDashboard = () => {
  return (
    <div className="training-dashboard">
      <header className="dashboard-header">
        <h1>🤖 Autonomous Training Agent Dashboard</h1>
        <p>Real-time monitoring and management</p>
      </header>

      <div className="dashboard-grid">
        <div className="grid-item full-width">
          <AgentStatusCard />
        </div>

        <div className="grid-item">
          <SystemStateCard />
        </div>

        <div className="grid-item">
          <SPPEBatchProgressCard />
        </div>

        <div className="grid-item">
          <IdentifiedGapsCard />
        </div>

        <div className="grid-item full-width">
          <ReviewQueueCard />
        </div>

        <div className="grid-item full-width">
          <MetricsChart />
        </div>
      </div>
    </div>
  );
};


export default TrainingDashboard;
