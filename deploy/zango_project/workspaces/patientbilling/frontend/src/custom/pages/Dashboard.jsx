import { useEffect, useRef, useState } from 'react';

const StatCard = ({ label, value, color }) => (
  <div style={{
    background: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: '24px',
    flex: 1,
    minWidth: 180,
  }}>
    <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>{label}</div>
    <div style={{ fontSize: 28, fontWeight: 700, color: color || '#111827' }}>{value}</div>
  </div>
);

const FakeProviderBanner = () => (
  <div style={{
    marginBottom: 24,
    padding: '12px 16px',
    border: '1px solid #fcd34d',
    borderRadius: 8,
    background: '#fffbeb',
    color: '#92400e',
    fontSize: 13,
    fontWeight: 500,
  }}>
    AI Insights are running on a local deterministic demo provider, not a real LLM.
  </div>
);

const Dashboard = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchDashboard = () => {
    fetch('/api/dashboard/')
      .then((r) => r.json())
      .then((d) => setData(d.response))
      .catch(() => setError('Failed to load dashboard data'));
  };

  useEffect(() => {
    fetchDashboard();
    // AI agents (claim-validator, denial-analyzer, appeal-drafter) run as
    // background Celery tasks; poll so pending_ai_tasks reflects live state.
    intervalRef.current = setInterval(fetchDashboard, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  if (error) return <div style={{ padding: 32, color: '#dc2626' }}>{error}</div>;
  if (!data) return <div style={{ padding: 32, color: '#6b7280' }}>Loading…</div>;

  return (
    <div style={{ padding: 32 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24, color: '#111827' }}>
        Billing Dashboard
      </h1>

      {data.ai_provider_is_fake && <FakeProviderBanner />}

      <div style={{ display: 'flex', gap: 16, marginBottom: 32, flexWrap: 'wrap' }}>
        <StatCard label="Total Claims" value={data.total_claims} />
        <StatCard label="Pending Claims" value={data.pending_claims} color="#f59e0b" />
        <StatCard label="Denial Rate" value={`${data.denial_rate}%`} color="#dc2626" />
        <StatCard
          label="Pending Revenue"
          value={`$${Number(data.pending_revenue).toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          color="#059669"
        />
        <StatCard
          label="AI Agents Running"
          value={data.pending_ai_tasks > 0 ? `${data.pending_ai_tasks} in progress` : 'None'}
          color={data.pending_ai_tasks > 0 ? '#4f46e5' : undefined}
        />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: 14 }}>
          Recent Claims
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f9fafb' }}>
              {['Claim #', 'Patient', 'Amount', 'Status'].map((h) => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left', color: '#6b7280', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.recent_claims || []).map((c) => (
              <tr key={c.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 16px' }}>{c.claim_number}</td>
                <td style={{ padding: '10px 16px' }}>{c.patient}</td>
                <td style={{ padding: '10px 16px' }}>${Number(c.total_amount).toLocaleString()}</td>
                <td style={{ padding: '10px 16px' }}>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 12,
                    fontSize: 11,
                    fontWeight: 600,
                    background: '#eff6ff',
                    color: '#1d4ed8',
                    textTransform: 'capitalize',
                  }}>
                    {(c.workflow_status || '').replace(/_/g, ' ')}
                  </span>
                </td>
              </tr>
            ))}
            {!data.recent_claims?.length && (
              <tr>
                <td colSpan={4} style={{ padding: '20px 16px', textAlign: 'center', color: '#9ca3af' }}>
                  No claims yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Dashboard;
