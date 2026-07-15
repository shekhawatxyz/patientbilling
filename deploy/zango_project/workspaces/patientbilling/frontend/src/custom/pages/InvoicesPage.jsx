import { CrudHandler } from '@zango-core/crud/table';

const InvoicesPage = () => (
  <CrudHandler
    api_endpoint="/invoices/invoices/"
    headerProps={{ title: 'Invoices' }}
  />
);

export default InvoicesPage;
