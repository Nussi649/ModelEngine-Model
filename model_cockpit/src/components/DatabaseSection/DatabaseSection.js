import React, { useState, useEffect } from 'react';
import './DatabaseSection.scss';

const DatabaseSection = ({ onToggle, isActive, onWipe, onSetup }) => {
    return (
        <div className="databaseSection">
            {/* Render Database Stats Here */}
            <label>
                <input 
                    type="checkbox" 
                    checked={isActive} 
                    onChange={() => onToggle('database', !isActive)} 
                />
                Activate
            </label>
            <button onClick={onWipe}>Wipe Database</button>
            <button onClick={onSetup}>Setup Database</button>
        </div>
    );
};

export default DatabaseSection;