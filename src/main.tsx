import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './theme/tokens.css';
import './theme/base.css';
import './styles.css';
import './translate.css';
import './translate-extra.css';
import './studio-extra.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
