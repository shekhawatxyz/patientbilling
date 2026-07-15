import { CrudHandler } from '@zango-core/crud/table';

const PatientDrawerDetail = ({ open, onClose, data, generalDetails, workflowDetails }) => {
  if (!open || !data) return null;
  const fields = generalDetails?.fields || {};

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px', borderBottom: '1px solid #e5e7eb' }}>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
          {fields.first_name?.value} {fields.last_name?.value}
        </h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#6b7280' }}>&times;</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
        <section style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
            Patient Info
          </div>
          {['first_name', 'last_name', 'date_of_birth', 'phone', 'email', 'address'].map((k) =>
            fields[k] ? (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
                <span style={{ fontSize: 13, color: '#6b7280' }}>{fields[k].display_name}</span>
                <span style={{ fontSize: 13, fontWeight: 500 }}>{fields[k].value || '—'}</span>
              </div>
            ) : null
          )}
        </section>

        <section>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
            Insurance
          </div>
          {['insurance_provider', 'insurance_policy_number', 'insurance_group_number'].map((k) =>
            fields[k] ? (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
                <span style={{ fontSize: 13, color: '#6b7280' }}>{fields[k].display_name}</span>
                <span style={{ fontSize: 13, fontWeight: 500 }}>{fields[k].value || '—'}</span>
              </div>
            ) : null
          )}
        </section>
      </div>
    </div>
  );
};

const PatientsPage = () => (
  <CrudHandler
    api_endpoint="/patients/patients/"
    headerProps={{ title: 'Patients' }}
    customDrawerDetail={PatientDrawerDetail}
  />
);

export default PatientsPage;
