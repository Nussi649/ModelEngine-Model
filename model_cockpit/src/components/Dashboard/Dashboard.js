import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import SpecsSection from './SpecsSection/SpecsSection';
import RuntimeSection from './RuntimeSection/RuntimeSection';
import DatabaseSection from './DatabaseSection/DatabaseSection';
import InterpreterSection from './InterpreterSection/InterpreterSection';
import styles from './Dashboard.module.scss';

const Dashboard = () => {
    const [modelState, setModelState] = useState({});
    const [isLoading, setIsLoading] = useState(true);
    const [specsActive, setSpecsActive] = useState(false);
    const [runtimeActive, setRuntimeActive] = useState(false);
    const [databaseActive, setDatabaseActive] = useState(false);
    const [interpreterActive, setInterpreterActive] = useState(false);

    const backendURL = process.env.REACT_APP_BACKEND_URL;

    const handleToggle = async (section, activate) => {
        // Call API to toggle the section and update state based on API response
        // If `section` has dependencies, ensure they are active before toggling
        // If deactivating `section`, ensure dependent sections are deactivated first
        // Example:
        // const response = await apiToggleSection(section, activate);
        // if (response.success) setSpecsActive(activate); // Update corresponding state
    };

    const handleDatabaseActions = async (action) => {
        // Handle Database specific actions like Wipe and Setup
        // Example:
        // const response = await apiDatabaseAction(action);
        // Handle response and update state if needed
    };
    
    useEffect(() => {
        const fetchModelState = async () => {
            try {
                const response = await fetch(`${backendURL}/model-state`);
                if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
                const data = await response.json();
                setModelState(data);
            } catch (error) {
                console.error('Error fetching model state:', error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchModelState();
    }, []);

    return (
        <div className={styles.dashboard}>
            <h1>Dashboard</h1>

            {isLoading ? (
                <p>Loading model state...</p>
            ) : (
                <>
                    <SpecsSection 
                        onToggle={handleToggle} 
                        isActive={modelState.specsActive} 
                        specsFilename={modelState.specsFilename}
                    />
                    
                    <RuntimeSection 
                        onToggle={handleToggle} 
                        isActive={modelState.runtimeActive} 
                        codeFilename={modelState.codeFilename}
                    />
                    
                    <DatabaseSection 
                        onToggle={handleToggle} 
                        isActive={modelState.databaseActive} 
                        onWipe={() => handleDatabaseActions('wipe')} 
                        onSetup={() => handleDatabaseActions('setup')}
                        indexes={modelState.indexes}
                        totalNodes={modelState.totalNodes}
                        modelObjects={modelState.modelObjects}
                        composites={modelState.composites}
                    />
                    
                    <InterpreterSection 
                        onToggle={handleToggle} 
                        isActive={modelState.interpreterActive} 
                    />
                </>
            )}
        </div>
    );
};

export default Dashboard;