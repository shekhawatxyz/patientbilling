// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-nocheck
import { ZangoApp } from '@zango-core/crm-framework';
import * as customPages from './custom/pages';

const App = () => (
  <ZangoApp
    appInitializerEndpoint="/appbuilder/initializer/"
    customPages={customPages}
  />
);

export default App;