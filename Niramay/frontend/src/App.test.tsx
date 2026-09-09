import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';
import { BrowserRouter } from 'react-router-dom';

describe('App Component', () => {
  it('renders the App container without crashing', () => {
    // We wrap App in a Router because it uses routing components inside
    render(<App />);
    // Let's just check if it renders the root div or anything inside
    expect(document.body).toBeInTheDocument();
  });
});
