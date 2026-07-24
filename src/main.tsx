import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { ComponentPreview } from './components/ComponentPreview';
import { ToastProvider } from './components/ui';
import './theme/tokens.css';
import './theme/base.css';
import './styles.css';
import './translate.css';
import './translate-extra.css';
import './studio-extra.css';

const isComponentPreview = new URLSearchParams(window.location.search).get('ui-preview') === '1';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{isComponentPreview ? <ComponentPreview /> : <ToastProvider><App /></ToastProvider>}</React.StrictMode>,
);
