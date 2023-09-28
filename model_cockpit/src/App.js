import React from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import Dashboard from './components/Dashboard/Dashboard';
import FileManagementPanel from './components/FileManagementPanel/FileManagementPanel';
import './App.scss';

function App() {
  return (
    <Router>
      <div className="App">
        <nav>
          <ul>
            <li><Link to="/">Home</Link></li>
            <li><Link to="/specs">Specifications</Link></li>
            <li><Link to="/code">Code</Link></li>
            <li><Link to="/payload">Payload Bay</Link></li>
          </ul>
        </nav>
        <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/specs" element={<FileManagementPanel contentType="specs" />} />
            <Route path="/code" element={<FileManagementPanel contentType="code" />} />
            <Route path="/payload" element={<FileManagementPanel contentType="payload" />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;