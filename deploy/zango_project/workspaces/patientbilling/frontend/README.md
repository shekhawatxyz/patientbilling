# Zango CRM React Application

A modern CRM application built with the Zango React framework.

## Quick Start

```bash
# Install dependencies
npm install

# Create your environment file from the example
cp .env.example .env

# Start development server
npm run dev

# Build for production
npm run build
```

## Prerequisites

- Node.js 18 or higher
- npm, pnpm, or yarn package manager

## Project Structure

```
├── src/
│   ├── types/
│   │   └── zango.d.ts      # TypeScript type definitions for Zango
│   ├── App.tsx             # Main application component
│   ├── index.tsx           # Application entry point
│   ├── index.zango.tsx     # Zango platform entry point
│   ├── index.css           # Global styles and Tailwind directives
│   └── vite-env.d.ts       # Vite environment type definitions
├── public/                 # Static assets
│   └── favicon.svg         # Application icon
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore file
├── index.html              # HTML template
├── package.json            # Project dependencies and scripts
├── README.md               # Project documentation
├── tailwind.config.ts      # Tailwind CSS configuration
├── tsconfig.json           # TypeScript configuration
├── tsconfig.node.json      # TypeScript configuration for node
├── vite.config.ts          # Vite configuration with proxy setup
└── vite.config.zango.ts    # Vite configuration for single-file Zango build
```

## Configuration

The application works out of the box with sensible defaults. Most configuration is handled automatically by the framework.

### Environment Variables

The project includes a `.env.example` file with default configuration. To get started:

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Modify the variables as needed:
   ```env
   # API Base URL (defaults to http://localhost:8000)
   VITE_API_BASE_URL=http://localhost:8000
   
   # Proxy routes (comma-separated paths to proxy)
   VITE_PROXY_ROUTES=/api,/zango,/frame
   
   # Environment (development, staging, production)
   VITE_APP_ENV=development
   ```

**Note:** The defaults work for standard development setups. Only modify if you need to connect to a different backend server.

## TypeScript Support

This project is built with TypeScript for enhanced type safety and developer experience. All source files use `.tsx` extensions for React components and `.ts` for other TypeScript files.

### Type Definitions

Type definitions for the Zango framework are available in `src/types/zango.d.ts`. You can extend these types as needed for your custom implementations.

## Page Types

The framework supports several page types:

### 1. CRUD Pages
- Automatically generated table views with full CRUD operations
- Configured via `extra_params.api_endpoint`
- Example: `"page_type": "crud", "extra_params": { "api_endpoint": "/users/crud/" }`

### 2. Login Pages
- Authentication pages
- Path: `/app/login`
- Handled entirely by the framework

### 3. Custom Pages
- Manually created React components
- Full control over layout and functionality
- Located in `src/custom/pages/`

## How It Works

### Dynamic Route Configuration

The application automatically fetches its configuration from the `/frame/router/initialize` endpoint on startup. Your backend should return a JSON response with the following structure:

```json
{
  "response": {
    "app_name": "Your App Name",
    "metadata": {
      "title": "Page Title",
      "description": "App description",
      "favicon": "/api/v1/static/favicon.ico"
    },
    "theme": {
      "colors": {
        "primary": "#136f63",
        "secondary": "#52c41a",
        "background": "#f0f2f5",
        "text_primary": "#262626"
      },
      "typography": {
        "font_family": "system-ui, -apple-system, sans-serif",
        "font_size_base": "14px"
      }
    },
    "routes": [
      {
        "path": "/app/dashboard",
        "page_type": "custom",
        "component": "Dashboard",
        "entity": "dashboard"
      },
      {
        "path": "/app/users",
        "page_type": "crud",
        "entity": "users",
        "extra_params": {
          "api_endpoint": "/users/crud/"
        }
      },
      {
        "path": "/app/profile360/:entityType/:id",
        "page_type": "profile360",
        "exact": false
      }
    ],
    "menu": [
      {
        "name": "Dashboard",
        "icon": "<svg>...</svg>",
        "uri": "/app/dashboard"
      },
      {
        "name": "Users",
        "icon": "<svg>...</svg>",
        "uri": "/app/users",
        "children": [
          {
            "name": "Sub Menu",
            "uri": "/app/users/sub"
          }
        ]
      }
    ],
    "app_logo": "/logo.png",
    "profile_info": {
      "name": "User Name",
      "user_role": "Admin"
    }
  },
  "status": "success"
}
```

### Menu Structure

The navigation menu is configured separately from routes in the API response. Menu items can be:
- **Simple links**: Direct navigation to a route
- **Nested menus**: Parent items with children sub-menus
- **SVG icons**: Custom icons can be provided as SVG strings

### Authentication

The framework handles authentication automatically. After successful login, the auth token is stored and included in all API requests.

## Routing

### Route Matching

- **Custom pages**: Use exact path matching
  - `/app/dashboard` ✓
  - `/app/dashboard/something` ✗ (404)

- **CRUD pages**: Support nested routes
  - `/app/users` ✓
  - `/app/users/123` ✓
  - `/app/users/123/edit` ✓

### Smart Navigation

The framework includes smart navigation that automatically handles both internal and external routes. It determines whether to use client-side routing or server-side navigation based on your route configuration.

## Styling

### Tailwind CSS

The project uses Tailwind CSS v4. Add your custom styles in `src/index.css`:

```css
@import "tailwindcss";

/* Your custom styles */
.custom-class {
  @apply p-4 bg-blue-500 text-white;
}
```

### Theme Customization

Themes are configured through the API response. The framework supports comprehensive theming including:
- **Colors**: Primary, secondary, background, text, borders, etc.
- **Typography**: Font family, sizes, line heights
- **Layout**: Menu configuration, sidebar settings
- **Borders & Shadows**: Radius and shadow definitions

The framework automatically generates CSS variables from the theme configuration and applies them to your application.

## Available Scripts

### `npm run dev`
Starts the development server on port 3000 with:
- Hot Module Replacement (HMR)
- Fast refresh for React components  
- Automatic API proxying

### `npm run build`
Creates an optimized production build in the `dist/` directory.

### `npm run build:zango`
Creates a single-file build optimized for the Zango platform:
- Outputs to `zango-build/` directory
- Bundles everything into a single `zango-app.js` file
- Includes all CSS and assets inline
- Perfect for deployment to Zango platform

### `npm run preview`
Preview the production build locally.

### `npm run type-check`
Run TypeScript type checking without emitting files.

## Development Server

### Proxy Configuration

The development server automatically proxies API requests to your backend server (default: `http://localhost:8000`), eliminating CORS issues during development.

Proxied routes (by default):
- `/api/*` - General API endpoints
- `/zango/*` - Zango framework endpoints  
- `/frame/*` - Frame router endpoints (including `/frame/router/initialize`)

The proxy target and routes can be customized via environment variables if needed.

### API Response Structure

The framework expects the API response to be wrapped in a standard structure:
```json
{
  "response": { /* actual data */ },
  "status": "success" | "error"
}
```

## Troubleshooting

### TypeScript Errors

1. Run `npm run type-check` to identify type errors
2. Ensure all required type definitions are installed
3. Check `tsconfig.json` for proper configuration

### API Connection Issues

1. Verify the API base URL in configuration
2. Check CORS settings on your backend
3. Ensure authentication token is valid

### 404 Errors on Custom Routes

Custom pages use exact path matching. Ensure:
- The exact path is defined in your API routes
- No trailing slashes unless specified in the route

## Best Practices

1. **TypeScript**: Leverage TypeScript for type safety and better IDE support
2. **Component Naming**: Use PascalCase for component names (e.g., `Dashboard`, `UserProfile`)
3. **Type Definitions**: Define proper types for props and state in your components
4. **Code Quality**: Run `npm run type-check` before committing code

## Deployment

### Standard Deployment
Use `npm run build` to create a standard multi-file production build in the `dist/` directory. This can be deployed to any static hosting service.

### Zango Platform Deployment
Use `npm run build:zango` to create a single-file build optimized for the Zango platform:

```bash
npm run build:zango
```

This creates a `zango-build/zango-app.js` file that contains your entire application, ready to be deployed to the Zango platform.

## Learn More

- [Zango Framework Documentation](https://docs.zango.dev)
- [React Documentation](https://react.dev)
- [Vite Documentation](https://vitejs.dev)