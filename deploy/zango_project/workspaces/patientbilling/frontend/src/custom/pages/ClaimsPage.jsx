import { CrudHandler, TableBody } from '@zango-core/crud/table';
import ClaimDetail from './ClaimDetail';

const NavigateTableBody = () => <TableBody defaultDetailView="navigate" />;

const ClaimsPage = () => (
  <CrudHandler
    api_endpoint="/claims/claims/"
    headerProps={{ title: 'Claims' }}
    enableDetailViewRoute={true}
    customMainDetail={ClaimDetail}
    customTableBody={NavigateTableBody}
  />
);

export default ClaimsPage;
