import React from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
import Dashboard from './components/Dashboard/Dashboard';
import ModelManagement from './components/ModelManagement/ModelManagement';
import PayloadBay from './components/PayloadBay/PayloadBay';
import './App.css';

function App() {
  return (
    <Router>
      <div className="App">
        <nav>
          <ul>
            <li><Link to="/">Dashboard</Link></li>
            <li><Link to="/model-management">Model Management</Link></li>
            <li><Link to="/payload-bay">Payload Bay</Link></li>
          </ul>
        </nav>
        <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/model-management" element={<ModelManagement />} />
            <Route path="/payload-bay" element={<PayloadBay />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;