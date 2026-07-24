import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { ToastProvider } from './components/ui';
import './theme/tokens.css';
import './theme/base.css';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root')!);

const render = async () => {
  const isComponentPreview = import.meta.env.DEV
    && new URLSearchParams(window.location.search).get('ui-preview') === '1';
  if (isComponentPreview) {
    const { ComponentPreview } = await import('./components/ComponentPreview');
    root.render(<React.StrictMode><ComponentPreview /></React.StrictMode>);
    return;
  }
  root.render(<React.StrictMode><ToastProvider><App /></ToastProvider></React.StrictMode>);
};

void render();
