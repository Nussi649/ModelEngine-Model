import React, { useState, useEffect } from 'react';
import './InterpreterSection.scss';

const InterpreterSection = ({ onToggle, isActive }) => {
    return (
        <div className="interpreterSection">
            <button>Go to Payload Management</button>
            <label>
                <input 
                    type="checkbox" 
                    checked={isActive} 
                    onChange={() => onToggle('interpreter', !isActive)} 
                />
                Activate
            </label>
        </div>
    );
};

export default InterpreterSection;