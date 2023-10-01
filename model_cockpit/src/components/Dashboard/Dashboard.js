import React, { useState, useEffect, useRef } from 'react';
import SpecsSection from '../Sections/SpecsSection.js';
import RuntimeSection from '../Sections/RuntimeSection.js';
import DatabaseSection from '../Sections/DatabaseSection.js';
import InterpreterSection from '../Sections/InterpreterSection.js';
import styles from './Dashboard.module.scss';

const Dashboard = () => {
    const [modelState, setModelState] = useState({
        indexes: 0,
        totalNodes: 0,
        modelObjects: 0,
        composites: 0
    });
    const [isLoading, setIsLoading] = useState(true);
    const [specsActive, setSpecsActive] = useState(false);
    const [runtimeActive, setRuntimeActive] = useState(false);
    const [databaseActive, setDatabaseActive] = useState(false);
    const [interpreterActive, setInterpreterActive] = useState(false);

    const specsIndicatorRef = useRef(null);
    const runtimeIndicatorRef = useRef(null);
    const dbIndicatorRef = useRef(null);
    const interpreterIndicatorRef = useRef(null);

    const [specsDbPath, setSpecsDbPath] = useState('');
    const [runtimeDbPath, setRuntimeDbPath] = useState('');
    const [sharedPath, setSharedPath] = useState('');
    const [dbInterpreterPath, setDbInterpreterPath] = useState('');

    const backendURL = process.env.REACT_APP_BACKEND_URL;

    const processStatusResponse = (res) => {
        // Assuming statusResponse is something like:
        // { specsActive: true, runtimeActive: false, ... , specsFilename: "somefile.xml", ... }
        
        if('specsActive' in res) setSpecsActive(res.specsActive);
        if('runtimeActive' in res) setRuntimeActive(res.runtimeActive);
        if('databaseActive' in res) setDatabaseActive(res.databaseActive);
        if('interpreterActive' in res) setInterpreterActive(res.interpreterActive);
        
        setModelState(prevState => ({
            ...prevState,
            specsFilename: 'specsFilename' in res ? res.specsFilename : prevState.specsFilename,
            codeFilename: 'codeFilename' in res ? res.codeFilename : prevState.codeFilename,
            indexes: 'indexes' in res ? res.indexes : prevState.indexes,
            totalNodes: 'totalNodes' in res ? res.totalNodes : prevState.totalNodes,
            modelObjects: 'modelObjects' in res ? res.modelObjects : prevState.modelObjects,
            composites: 'composites' in res ? res.composites : prevState.composites
        }));
    };

    const sendActivationRequest = async (actions) => {
        // actions would be an array of objects like [{ section: 'specs', action: 'activate' }, { section: 'runtime', action: 'deactivate' }, ...]
        
        try {
            const response = await fetch(`${backendURL}/component-set-state`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ actions })
            });
            
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const data = await response.json();
            
            processStatusResponse(data);
        } catch (error) {
            console.error('Error changing status of sections:', error);
        }
    };

    const handleToggle = (toggledComponent) => {
        let actions = [];
    
        const activate = (component) => actions.push({ component, action: 'start' });
        const deactivate = (component) => actions.push({ component, action: 'stop' });
    
        switch (toggledComponent) {
            case 'specs':
                if (specsActive) {
                    if (interpreterActive) deactivate('interpreter');
                    if (databaseActive) deactivate('database');
                    deactivate('specs');
                } else {
                    activate('specs');
                }
                break;
    
            case 'runtime':
                if (runtimeActive) {
                    if (interpreterActive) deactivate('interpreter');
                    if (databaseActive) deactivate('database');
                    deactivate('runtime')
                } else {
                    activate('runtime');
                }
                break;
    
            case 'database':
                if (databaseActive) {
                    if (interpreterActive) deactivate('interpreter');
                    deactivate('database');
                } else {
                    if (!specsActive) activate('specs');
                    if (!runtimeActive) activate('runtime');
                    activate('database');
                }
                break;
    
            case 'interpreter':
                if (interpreterActive) {
                    deactivate('interpreter');
                } else {
                    if (!specsActive) activate('specs');
                    if (!runtimeActive) activate('runtime');
                    if (!databaseActive) activate('database');
                    activate('interpreter');
                }
                break;
    
            default:
                console.error('Invalid component toggled:', toggledComponent);
                return;
        }
    
        sendActivationRequest(actions);
    };

    const sendStatusRequest = async (components) => {
        // components would be an array like ['specs', 'runtime', 'database', 'interpreter']
        
        try {
            const response = await fetch(`${backendURL}/component-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ components })
            });
            
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const data = await response.json();
            
            processStatusResponse(data);
        } catch (error) {
            console.error('Error getting sections status:', error);
        }
    };

    const handleDatabaseActions = async (action) => {
        try {
            let endpoint;
            switch (action) {
                case 'wipe':
                    endpoint = `${backendURL}/db-wipe`;
                    break;
                case 'setup':
                    endpoint = `${backendURL}/db-init`;
                    break;
                default:
                    console.error('Invalid database action:', action);
                    return;
            }
            
            const response = await fetch(endpoint, { method: 'POST' });
    
            if (!response.ok) {
                const message = `An error has occurred: ${response.status}`;
                console.error(message);
                // Optionally: set some state variable to show an error message in the UI
                return;
            }
    
            const data = await response.json();
            console.log('Database action response:', data);
    
            processStatusResponse(data)
    
        } catch (error) {
            console.error('Error during database action:', error);
            // Optionally: set some state variable to show an error message in the UI
        }
    };

    const updatePaths = () => {
        if (
            specsIndicatorRef.current &&
            runtimeIndicatorRef.current &&
            dbIndicatorRef.current &&
            interpreterIndicatorRef.current
        ) {
            const specsPos = specsIndicatorRef.current.getBoundingClientRect();
            const runtimePos = runtimeIndicatorRef.current.getBoundingClientRect();
            const dbPos = dbIndicatorRef.current.getBoundingClientRect();
            const interpreterPos = interpreterIndicatorRef.current.getBoundingClientRect();

            // Define the shared control point between 'specs' and 'runtime' to 'database'
            const sharedControlX = dbPos.x - 150;
            const sharedControlY = dbPos.y + dbPos.height / 2;
            const mergePointX = dbPos.x - 50;
            const mergePointY = dbPos.y + dbPos.height / 2;

            // Define the starting and ending points and control points for the cubic bezier curve between 'specs' and 'database'
            const specsStartX = specsPos.x + specsPos.width;
            const specsStartY = specsPos.y + specsPos.height / 2;
            const specsControlX1 = specsStartX + 100;
            const specsControlY1 = specsStartY;

            // Define the starting and ending points and control points for the cubic bezier curve between 'runtime' and 'database'
            const runtimeStartX = runtimePos.x + runtimePos.width;
            const runtimeStartY = runtimePos.y + runtimePos.height / 2;
            const runtimeControlX1 = runtimeStartX + 100;
            const runtimeControlY1 = runtimeStartY;

            // Define the starting and ending points and control points for the cubic bezier curve between 'database' and 'interpreter'
            const dbStartX = dbPos.x + dbPos.width;
            const dbStartY = dbPos.y + dbPos.height / 2;
            const dbControlX1 = dbStartX + 100;
            const dbControlY1 = dbStartY;

            const interpreterEndX = interpreterPos.x;
            const interpreterEndY = interpreterPos.y + interpreterPos.height / 2;
            const interpreterControlX2 = interpreterEndX - 50;
            const interpreterControlY2 = interpreterEndY;
        
            // Constructing the path strings for the SVG <path> elements
            const path1 = `
                M ${specsStartX} ${specsStartY} 
                C ${specsControlX1} ${specsControlY1}, ${sharedControlX} ${sharedControlY}, ${mergePointX} ${mergePointY}
            `
            const path2 = `
                M ${runtimeStartX} ${runtimeStartY} 
                C ${runtimeControlX1} ${runtimeControlY1}, ${sharedControlX} ${sharedControlY}, ${mergePointX} ${mergePointY}
            `
            const path3 = `
                M ${mergePointX} ${mergePointY}
                L ${dbStartX - dbPos.width} ${dbStartY}
            `
            const path4 = `
                M ${dbStartX} ${dbStartY} 
                C ${dbControlX1} ${dbControlY1}, ${interpreterControlX2} ${interpreterControlY2}, ${interpreterEndX} ${interpreterEndY}
            `;
    
            setSpecsDbPath(path1);
            setRuntimeDbPath(path2);
            setSharedPath(path3)
            setDbInterpreterPath(path4);
        }
      };
    
    useEffect(() => {
        const getInitialStatus = async () => {
            try {
                await sendStatusRequest(['specs', 'runtime', 'database', 'interpreter']);
            } catch (error) {
                console.error('Error fetching initial component status:', error);
            } finally {
                setIsLoading(false);
            }
        };

        getInitialStatus();
        updatePaths();
    }, []);

    useEffect(() => {
        // Call updatePaths whenever the component is mounted or updated
        updatePaths();
    }, [modelState, specsActive, runtimeActive, databaseActive, interpreterActive]);

    return (
        <div className={styles.dashboard}>
            <h1>Model Cockpit</h1>
    
            {isLoading ? (
                <p>Loading model state...</p>
            ) : (
                <div className={styles.columnsContainer}>
                    <div className={styles.leftColumn}>
                        <SpecsSection 
                            indicatorRef={specsIndicatorRef}
                            onToggle={() => handleToggle('specs')} 
                            isActive={specsActive} 
                            specsFilename={modelState.specsFilename}
                        />
                        <RuntimeSection 
                            indicatorRef={runtimeIndicatorRef}
                            onToggle={() => handleToggle('runtime')} 
                            isActive={runtimeActive} 
                            codeFilename={modelState.codeFilename}
                        />
                    </div>
    
                    <div className={styles.centerColumn}>
                        <DatabaseSection 
                            indicatorRef={dbIndicatorRef}
                            onToggle={() => handleToggle('database')} 
                            isActive={databaseActive} 
                            onWipe={() => handleDatabaseActions('wipe')} 
                            onInitialize={() => handleDatabaseActions('setup')}
                            stats={{
                                indexes: modelState.indexes,
                                totalNodes: modelState.totalNodes,
                                modelObjects: modelState.modelObjects,
                                composites: modelState.composites
                            }}
                        />
                    </div>
    
                    <div className={styles.rightColumn}>
                        <InterpreterSection 
                            indicatorRef={interpreterIndicatorRef}
                            onToggle={() => handleToggle('interpreter')} 
                            isActive={interpreterActive} 
                        />
                    </div>
    
                    <svg className={styles.connectorLines} style={{ width: '100%', height: '100%' }}>
                        <path d={specsDbPath} className={styles.connectorLine} style={{ fill: 'none', stroke: '#000', strokeWidth: '2' }} />
                        <path d={runtimeDbPath} className={styles.connectorLine} style={{ fill: 'none', stroke: '#000', strokeWidth: '2' }} />
                        <path d={sharedPath} className={styles.connectorLine} style={{ fill: 'none', stroke: '#000', strokeWidth: '2' }} />
                        <path d={dbInterpreterPath} className={styles.connectorLine} style={{ fill: 'none', stroke: '#000', strokeWidth: '2' }} />
                    </svg>
                </div>
            )}
        </div>
    );
};

export default Dashboard;