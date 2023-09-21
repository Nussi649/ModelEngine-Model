import React, { useState, useEffect } from 'react';
import FileSelectDialog from '../FileSelectDialog/FileSelectDialog.js';  // Import the FileSelectDialog component
import styles from './ModelManagement.module.css';

function ModelManagement() {
    const backendURL = process.env.REACT_APP_BACKEND_URL;

    // State to hold database statistics
    const [databaseStats, setDatabaseStats] = useState({
        indexes: 0,
        totalNodes: 0,
        modelObjects: 0,
        composites: 0
    });

    // State for file titles and their contents
    const [modelSpecsFileName, setModelSpecsFileName] = useState('Not loaded');
    const [modelSpecsContent, setModelSpecsContent] = useState('');
    const [modelCodeFileName, setModelCodeFileName] = useState('Not loaded');
    const [modelCodeContent, setModelCodeContent] = useState('');

    // State for controlling the FileSelectDialog's visibility
    const [isFileDialogOpen, setIsFileDialogOpen] = useState(false);
    const [currentFileDialogType, setCurrentFileDialogType] = useState('');  // 'specs' or 'code'

    useEffect(() => {
        // Fetch the model state when the component is mounted
        fetchModelState();
    }, []);

    const fetchModelState = async () => {
        try {
            let response = await fetch(`${backendURL}/model-state`);
            let data = await response.json();

            // Set the database stats
            setDatabaseStats({
                indexes: data.indexes,
                totalNodes: data.totalNodes,
                modelObjects: data.modelObjects,
                composites: data.composites
            });

            // Set the loaded file names and contents for model specifications and code
            setModelSpecsFileName(data.specsFilename);
            setModelSpecsContent(data.specsContent);
            setModelCodeFileName(data.codeFilename);
            setModelCodeContent(data.codeContent);
        } catch (error) {
            console.error("Failed to fetch model state:", error);
        }
    };

    const handleFileSelect = async (file, endpoint) => {
        try {
            const response = await fetch(endpoint);
            const fileContent = await response.text();
            
            if (currentFileDialogType === 'specs') {
                setModelSpecsFileName(file);
                setModelSpecsContent(fileContent);
            } else {
                setModelCodeFileName(file);
                setModelCodeContent(fileContent);
            }
        } catch (error) {
            console.error("Error fetching file content:", error);
        }

        setIsFileDialogOpen(false);
    };

    const handleUploadFile = async (filename, content, filetype, load) => {
        try {
            const formData = new FormData();
            formData.append('file', new Blob([content], { type: 'text/plain' }), filename);
    
            const response = await fetch(`${backendURL}/upload-file/${filetype}?load=${load}`, {
                method: 'POST',
                body: formData,
            });
    
            const data = await response.json();
            if (data.status !== 'success') {
                console.error("Failed to save/commit the file.");
            }
        } catch (error) {
            console.error("Error saving/committing file:", error);
        }
    };

    const handleOpenSpecsFileDialog = () => {
        setCurrentFileDialogType('specs');
        setIsFileDialogOpen(true);
    };

    const handleOpenCodeFileDialog = () => {
        setCurrentFileDialogType('code');
        setIsFileDialogOpen(true);
    };

    return (
        <div>
            <h1>Model Cockpit</h1>

            {/* Database Operations Card */}
            <div className={styles.databaseOperations}>
                <div>
                    <p>Number of indexes: {databaseStats.indexes}</p>
                    <p>Total nodes: {databaseStats.totalNodes}</p>
                    <p>ModelObjects: {databaseStats.modelObjects}</p>
                    <p>Composites: {databaseStats.composites}</p>
                </div>
                <div>
                    <button>Setup</button>
                    <button>Reset</button>
                </div>
            </div>

            {/* Model Specifications Section */}
            <section className={styles.modelSpecifications}>
                <div>
                    <h2>Model Specifications</h2>
                    <label>Loaded File: {modelSpecsFileName}</label>
                    <button onClick={handleOpenSpecsFileDialog}>Select File</button>
                    <button onClick={() => handleUploadFile(modelSpecsFileName, modelSpecsContent, 'specs', false)}>Save</button>
                    <button onClick={() => handleUploadFile(modelSpecsFileName, modelSpecsContent, 'specs', true)}>Commit</button>
                </div>
                <textarea readOnly value={modelSpecsContent} />
            </section>

            {/* Model Code Section */}
            <section className={styles.modelCode}>
                <div>
                    <h2>Model Code</h2>
                    <label>Loaded File: {modelCodeFileName}</label>
                    <button onClick={handleOpenCodeFileDialog}>Select File</button>
                    <button onClick={() => handleUploadFile(modelCodeFileName, modelCodeContent, 'code', false)}>Save</button>
                    <button onClick={() => handleUploadFile(modelCodeFileName, modelCodeContent, 'code', true)}>Commit</button>
                </div>
                <textarea readOnly value={modelCodeContent} />
            </section>

            {/* File Select Dialog */}
            <FileSelectDialog 
                isOpen={isFileDialogOpen}
                dialogName={currentFileDialogType === 'specs' ? "Model Specifications" : "Model Code"}
                fetchFileListEndpoint={currentFileDialogType === 'specs' ? `${backendURL}/filelist/specs` : `${backendURL}/filelist/code`}
                uploadFileEndpoint={currentFileDialogType === 'specs' ? `${backendURL}/upload-specs` : `${backendURL}/upload-code`}
                onFileSelect={(file) => handleFileSelect(file, currentFileDialogType === 'specs' ? `${backendURL}/file-content/specs/${file}` : `${backendURL}/file-content/code/${file}`)}
                onDismiss={() => setIsFileDialogOpen(false)}
            />
        </div>
    );
}

export default ModelManagement;