import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// For Zango platform deployment
// Ensures the root element exists before mounting React
function initializeApp() {
  // Try to find the Zango app container first, fallback to root
  let rootElement = document.getElementById('zango-app') || document.getElementById('root');
  
  // If neither exists, create one
  if (!rootElement) {
    rootElement = document.createElement('div');
    rootElement.id = 'zango-app';
    document.body.appendChild(rootElement);
  }
  
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  initializeApp();
}