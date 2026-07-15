declare module '@zango-core/crm-framework' {
  export interface ZangoAppProps {
    appInitializerEndpoint: string;
  }

  export const ZangoApp: React.FC<ZangoAppProps>;
}

declare module '@zango-core/components';
declare module '@zango-core/crud';
declare module '@zango-core/training';
