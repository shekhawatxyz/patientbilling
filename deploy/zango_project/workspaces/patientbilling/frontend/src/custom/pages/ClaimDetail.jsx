import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const Tab = ({ label, active, onClick }) => (
  <button
    onClick={onClick}
    style={{
      padding: '10px 20px',
      border: 'none',
      background: 'none',
      cursor: 'pointer',
      fontSize: 13,
      fontWeight: active ? 600 : 400,
      color: active ? '#4f46e5' : '#6b7280',
      borderBottom: active ? '2px solid #4f46e5' : '2px solid transparent',
    }}
  >
    {label}
  </button>
);

const FieldRow = ({ label, value }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #f3f4f6' }}>
    <span style={{ fontSize: 13, color: '#6b7280' }}>{label}</span>
    <span style={{ fontSize: 13, fontWeight: 500, maxWidth: '60%', textAlign: 'right' }}>{value ?? '—'}</span>
  </div>
);

const ScoreBadge = ({ score }) => {
  const color = score >= 80 ? '#059669' : score >= 50 ? '#d97706' : '#dc2626';
  return (
    <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 12, background: color + '20', color, fontWeight: 700, fontSize: 13 }}>
      {score}/100
    </span>
  );
};

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

const AIInsightsTab = ({ claimId, objectUuid, apiEndpoint }) => {
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isFakeProvider, setIsFakeProvider] = useState(false);
  const intervalRef = useRef(null);

  const fetchClaim = () => {
    fetch(`${apiEndpoint}?action=fetch_item_details&object_uuid=${objectUuid}`)
      .then((r) => r.json())
      .then((d) => {
        const details = d?.response?.general_details?.fields || {};
        const aiValidation = details?.ai_validation_result?.value;
        const aiDenial = details?.ai_denial_analysis?.value;
        const aiAppeal = details?.ai_appeal_draft?.value;
        setClaim({ aiValidation, aiDenial, aiAppeal });
        setLoading(false);

        const allFilled = aiValidation && aiDenial && aiAppeal;
        if (allFilled && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchClaim();
    fetch('/api/dashboard/')
      .then((r) => r.json())
      .then((d) => setIsFakeProvider(d?.response?.ai_provider_is_fake === true))
      .catch(() => {});
    intervalRef.current = setInterval(fetchClaim, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [objectUuid]);

  if (loading) return <div style={{ padding: 24, color: '#6b7280' }}>Loading AI insights…</div>;

  const { aiValidation, aiDenial, aiAppeal } = claim || {};

  let validation = null;
  try { validation = typeof aiValidation === 'string' ? JSON.parse(aiValidation) : aiValidation; } catch {}

  let denial = null;
  try { denial = typeof aiDenial === 'string' ? JSON.parse(aiDenial) : aiDenial; } catch {}

  return (
    <div style={{ padding: 24 }}>
      {isFakeProvider && <FakeProviderBanner />}

      {!aiValidation && !aiDenial && !aiAppeal && (
        <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 16 }}>
          AI analysis is running… refreshing every 5s
        </div>
      )}

      {validation && (
        <div style={{ marginBottom: 24, background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>
            Claim Validation &nbsp;
            {validation.completeness_score != null && <ScoreBadge score={validation.completeness_score} />}
          </div>
          {validation.valid != null && (
            <div style={{ marginBottom: 8, fontSize: 13 }}>
              Status: <strong style={{ color: validation.valid ? '#059669' : '#dc2626' }}>{validation.valid ? 'Valid' : 'Invalid'}</strong>
            </div>
          )}
          {validation.issues?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Issues</div>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {validation.issues.map((i, idx) => <li key={idx} style={{ fontSize: 13, color: '#374151' }}>{i}</li>)}
              </ul>
            </div>
          )}
          {validation.code_suggestions?.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Code Suggestions</div>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {validation.code_suggestions.map((s, idx) => <li key={idx} style={{ fontSize: 13, color: '#374151' }}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {denial && (
        <div style={{ marginBottom: 24, background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8, padding: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>Denial Analysis</div>
          {denial.category && (
            <div style={{ marginBottom: 8, fontSize: 13 }}>
              Category: <span style={{ padding: '2px 8px', background: '#fef3c7', borderRadius: 12, fontWeight: 600 }}>{denial.category}</span>
            </div>
          )}
          {denial.root_cause && <div style={{ fontSize: 13, marginBottom: 8 }}>{denial.root_cause}</div>}
          {denial.corrective_actions?.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Corrective Actions</div>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {denial.corrective_actions.map((a, idx) => <li key={idx} style={{ fontSize: 13 }}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {aiAppeal && (
        <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>Appeal Draft</div>
          <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', margin: 0, color: '#1e3a8a' }}>{aiAppeal}</pre>
        </div>
      )}
    </div>
  );
};

const ClaimDetail = ({ data, generalDetails, workflowDetails, objectUuid, pk, apiUrl, onRefresh }) => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('info');

  if (!data) return null;

  const fields = generalDetails?.fields || {};
  const lineItems = data?.line_items || [];

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      <button
        onClick={() => navigate(-1)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 13, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 4 }}
      >
        ← Back to Claims
      </button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
          {fields.claim_number?.value || `Claim #${pk}`}
        </h1>
        {workflowDetails?.current_status_meta && (
          <span style={{
            padding: '3px 10px',
            borderRadius: 12,
            fontSize: 12,
            fontWeight: 600,
            background: (workflowDetails.current_status_meta.status_color || '#6b7280') + '20',
            color: workflowDetails.current_status_meta.status_color || '#6b7280',
          }}>
            {workflowDetails.current_status_meta.status_label}
          </span>
        )}
      </div>

      <div style={{ borderBottom: '1px solid #e5e7eb', display: 'flex', marginBottom: 0 }}>
        <Tab label="Claim Info" active={activeTab === 'info'} onClick={() => setActiveTab('info')} />
        <Tab label="Line Items" active={activeTab === 'lines'} onClick={() => setActiveTab('lines')} />
        <Tab label="Workflow" active={activeTab === 'workflow'} onClick={() => setActiveTab('workflow')} />
        <Tab label="AI Insights" active={activeTab === 'ai'} onClick={() => setActiveTab('ai')} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderTop: 'none', borderRadius: '0 0 8px 8px' }}>
        {activeTab === 'info' && (
          <div style={{ padding: 24 }}>
            {Object.entries(fields).map(([key, field]) => (
              <FieldRow key={key} label={field.display_name} value={field.value} />
            ))}
          </div>
        )}

        {activeTab === 'lines' && (
          <div style={{ padding: 0 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  {['Procedure Code', 'Description', 'Qty', 'Unit Price', 'Total'].map((h) => (
                    <th key={h} style={{ padding: '10px 16px', textAlign: 'left', color: '#6b7280', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lineItems.map((li, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px' }}>{li.procedure_code}</td>
                    <td style={{ padding: '10px 16px' }}>{li.procedure_description}</td>
                    <td style={{ padding: '10px 16px' }}>{li.quantity}</td>
                    <td style={{ padding: '10px 16px' }}>${li.unit_price}</td>
                    <td style={{ padding: '10px 16px' }}>${li.total_price}</td>
                  </tr>
                ))}
                {!lineItems.length && (
                  <tr><td colSpan={5} style={{ padding: '20px 16px', textAlign: 'center', color: '#9ca3af' }}>No line items</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'workflow' && (
          <div style={{ padding: 24 }}>
            {workflowDetails ? (
              <>
                <FieldRow label="Current Status" value={workflowDetails.current_status_meta?.status_label || workflowDetails.current_status} />
                {workflowDetails.next_transitions?.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>Available Transitions</div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {workflowDetails.next_transitions.map((t) => (
                        <span key={t.name} style={{ padding: '4px 12px', background: '#eff6ff', color: '#1d4ed8', borderRadius: 6, fontSize: 13, fontWeight: 500 }}>
                          {t.display_name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div style={{ color: '#9ca3af' }}>No workflow data</div>
            )}
          </div>
        )}

        {activeTab === 'ai' && (
          <AIInsightsTab claimId={pk} objectUuid={objectUuid} apiEndpoint={apiUrl} />
        )}
      </div>
    </div>
  );
};

export default ClaimDetail;
