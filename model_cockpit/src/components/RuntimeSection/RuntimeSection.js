import React, { useState, useEffect } from 'react';
import './RuntimeSection.scss';

const RuntimeSection = ({ onToggle, isActive }) => {
    return (
        <div className="runtimeSection">
            <button>Go to Code Management</button>
            <label>
                <input 
                    type="checkbox" 
                    checked={isActive} 
                    onChange={() => onToggle('runtime', !isActive)} 
                />
                Activate
            </label>
        </div>
    );
};

export default RuntimeSection;
