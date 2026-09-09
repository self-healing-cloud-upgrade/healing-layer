import { useState, useEffect } from 'react';
import { timeAgo } from '../designSystem';

export default function ReportPortal() {
  const [activeTab, setActiveTab] = useState<'stage1' | 'stage2' | 'stage3' | 'stage4'>('stage1');
  
  return (
    <div className="glass card-glass" style={{ borderRadius: 'var(--radius-xl)', overflow: 'hidden', marginBottom: 'var(--space-8)' }}>
      <div style={{ display: 'flex', borderBottom: '1px solid var(--color-border-subtle)', background: 'var(--color-bg-secondary)' }}>
        <Tab id="stage1" active={activeTab} onClick={setActiveTab} label="Stage 1: Ingestion Logs" />
        <Tab id="stage2" active={activeTab} onClick={setActiveTab} label="Stage 2: Anomaly Records" />
        <Tab id="stage3" active={activeTab} onClick={setActiveTab} label="Stage 3: Incident Reports" />
        <Tab id="stage4" active={activeTab} onClick={setActiveTab} label="Stage 4: Healed Reports" />
      </div>
      <div style={{ padding: 'var(--space-6)' }}>
        {activeTab === 'stage1' && <Stage1Logs />}
        {activeTab === 'stage2' && <Stage2Anomalies />}
        {activeTab === 'stage3' && <Stage3Incidents />}
        {activeTab === 'stage4' && <Stage4Healed />}
      </div>
    </div>
  );
}

function Tab({ id, active, onClick, label }: any) {
  const isActive = active === id;
  return (
    <button
      onClick={() => onClick(id)}
      style={{
        padding: 'var(--space-4) var(--space-6)',
        background: isActive ? 'transparent' : 'transparent',
        border: 'none',
        borderBottom: isActive ? '2px solid var(--color-accent-primary)' : '2px solid transparent',
        color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
        fontWeight: isActive ? 600 : 500,
        fontSize: 'var(--text-sm)',
        cursor: 'pointer',
        transition: 'all 200ms',
      }}
    >
      {label}
    </button>
  );
}

function Stage1Logs() {
  const [logType, setLogType] = useState<'raw' | 'normalized'>('normalized');
  const [serviceFilter, setServiceFilter] = useState('');
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchLogs = async () => {
      setLoading(true);
      try {
        const url = logType === 'raw' 
          ? '/api/v1/observation/logs/raw?limit=50' 
          : `/api/v1/observation/logs/history?limit=50${serviceFilter ? '&service=' + serviceFilter : ''}`;
        const res = await fetch(url);
        const data = await res.json();
        if (active) setLogs(data);
      } catch (e) {
        if (active) setLogs([]);
      }
      if (active) setLoading(false);
    };
    fetchLogs();
    return () => { active = false; };
  }, [logType, serviceFilter]);

  return (
    <div>
      <div style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <select 
          value={logType} 
          onChange={e => setLogType(e.target.value as any)}
          style={{ padding: '8px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-sunken)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
        >
          <option value="normalized">Normalized Logs</option>
          <option value="raw">Raw Logs</option>
        </select>
        {logType === 'normalized' && (
          <input 
            type="text" 
            placeholder="Filter by service (e.g. auth-service)"
            value={serviceFilter}
            onChange={e => setServiceFilter(e.target.value)}
            style={{ padding: '8px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-sunken)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)', flex: 1 }}
          />
        )}
      </div>
      {loading ? <p style={{ color: 'var(--color-text-tertiary)' }}>Loading...</p> : (
        <div style={{ maxHeight: 400, overflowY: 'auto', background: 'var(--color-bg-sunken)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)' }}>
          {logs.length === 0 ? <p style={{ color: 'var(--color-text-tertiary)' }}>No logs found.</p> : logs.map((log, i) => (
            <div key={i} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid var(--color-border-subtle)' }}>
              <pre style={{ margin: 0, color: 'var(--color-text-secondary)', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(log, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stage2Anomalies() {
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchAnomalies = async () => {
      setLoading(true);
      try {
        const res = await fetch('/api/v1/detection/anomalies/records?limit=50');
        const data = await res.json();
        if (active) setRecords(data);
      } catch (e) {
        if (active) setRecords([]);
      }
      if (active) setLoading(false);
    };
    fetchAnomalies();
    return () => { active = false; };
  }, []);

  return (
    <div>
      {loading ? <p style={{ color: 'var(--color-text-tertiary)' }}>Loading...</p> : (
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {records.length === 0 ? <p style={{ color: 'var(--color-text-tertiary)' }}>No anomaly records found.</p> : records.map((rec, i) => (
            <div key={i} style={{ marginBottom: 12, padding: 12, background: 'var(--color-bg-sunken)', borderRadius: 'var(--radius-md)', borderLeft: '3px solid var(--color-status-warning)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <strong style={{ color: 'var(--color-text-primary)' }}>{rec.service} — {rec.endpoint}</strong>
                <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{timeAgo(rec.timestamp)}</span>
              </div>
              <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>Reasons: {(rec.anomaly_reasons || []).join(', ')}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stage3Incidents() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchReports = async () => {
      setLoading(true);
      try {
        const res = await fetch('/api/v1/incident/reports/history?limit=50');
        const data = await res.json();
        if (active) setReports(data);
      } catch (e) {
        if (active) setReports([]);
      }
      if (active) setLoading(false);
    };
    fetchReports();
    return () => { active = false; };
  }, []);

  return (
    <div>
      {loading ? <p style={{ color: 'var(--color-text-tertiary)' }}>Loading...</p> : (
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {reports.length === 0 ? <p style={{ color: 'var(--color-text-tertiary)' }}>No incident reports found.</p> : reports.map((rep, i) => (
            <div key={i} style={{ marginBottom: 12, padding: 12, background: 'var(--color-bg-sunken)', borderRadius: 'var(--radius-md)', borderLeft: '3px solid var(--color-status-error)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <strong style={{ color: 'var(--color-text-primary)' }}>Detection {rep.detection_id?.substring(0,8)}</strong>
                <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{timeAgo(rep.timestamp || rep.created_at)}</span>
              </div>
              <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>{rep.human_report}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stage4Healed() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchReports = async () => {
      setLoading(true);
      try {
        const res = await fetch('/api/v1/healing/healed-reports?limit=50');
        const data = await res.json();
        if (active) setReports(data);
      } catch (e) {
        if (active) setReports([]);
      }
      if (active) setLoading(false);
    };
    fetchReports();
    return () => { active = false; };
  }, []);

  return (
    <div>
      {loading ? <p style={{ color: 'var(--color-text-tertiary)' }}>Loading...</p> : (
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          {reports.length === 0 ? <p style={{ color: 'var(--color-text-tertiary)' }}>No healed reports found.</p> : reports.map((rep, i) => (
            <div key={i} style={{ marginBottom: 12, padding: 12, background: 'var(--color-bg-sunken)', borderRadius: 'var(--radius-md)', borderLeft: '3px solid var(--color-status-success)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <strong style={{ color: 'var(--color-text-primary)' }}>{rep.service} Healed</strong>
                <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{timeAgo(rep.healed_at)}</span>
              </div>
              <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>Action: {rep.healing_action_taken}</p>
              <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>Time to heal: {rep.time_to_heal_seconds}s</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
