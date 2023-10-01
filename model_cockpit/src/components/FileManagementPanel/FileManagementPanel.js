import React, { useState, useEffect, useRef } from 'react';
import styles from './FileManagementPanel.module.scss';

function FileManagementPanel({ contentType, customAction }) {
    // Validate contentType
    const validContentTypes = ['specs', 'code', 'payload'];
    if (!validContentTypes.includes(contentType)) {
        // Redirect to homepage or show an error message.
    }

    // Calculate the page title based on contentType
    let pageTitle;
    switch (contentType) {
        case 'specs':
            pageTitle = 'Model Specifications';
            break;
        case 'code':
            pageTitle = 'Model Code';
            break;
        case 'payload':
            pageTitle = 'Payload Bay';
            break;
        default:
            pageTitle = 'Unknown Content Type';
    }

    const [isLoading, setIsLoading] = useState(true);
    const [fileList, setFileList] = useState([]);
    const [selectedFile, setSelectedFile] = useState('');
    const [fileContent, setFileContent] = useState('');
    const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
    
    const fileListEndpoint = `/file-list/${contentType}`;
    const fileContentEndpoint = `/file-content/${contentType}`;
    const fileUploadEndpoint = `/upload-file/${contentType}`;
    const fileDeleteEndpoint = `/delete-file/${contentType}`;
    const activateEndpoint = `/activate/${contentType}`;

    const fileInputRef = useRef();
    const textAreaRef = useRef();
    
    const fetchFileList = async () => {
        try {
            setIsLoading(true);
            const response = await fetch(fileListEndpoint);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            const data = await response.json();
            setFileList(data);
        } catch (error) {
            console.error('Error fetching file list:', error);
        } finally {
            setIsLoading(false);
        }
    };
    
    const handleFileSelect = async (fileName) => {
        try {
            const response = await fetch(`${fileContentEndpoint}/${fileName}`);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            const data = await response.text();
            setFileContent(data);
            setSelectedFile(fileName);
            setHasUnsavedChanges(false);  // Reset unsaved changes flag
        } catch (error) {
            console.error('Error fetching file content:', error);
        }
    };

    const handleContentChange = (newContent) => {
        setFileContent(newContent);
        setHasUnsavedChanges(true); // Content has been edited
    };

    const handleSave = async () => {
        try {
            const formData = new FormData();
            formData.append('file', new Blob([fileContent], { type: 'text/plain' }), selectedFile);
            formData.append('overwrite', 'true');  // Since handleSave is intended to update the file
    
            const response = await fetch(fileUploadEndpoint, {
                method: 'POST',
                body: formData, // Sending as form data
            });
    
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            setHasUnsavedChanges(false);
            alert('File saved successfully!');
        } catch (error) {
            console.error('Error saving file:', error);
            alert('Error saving file!');
        }
    };
    
    const handleFileDelete = async (fileName) => {
        try {
            const response = await fetch(`${fileDeleteEndpoint}/${fileName}`, { method: 'DELETE' });
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            fetchFileList();  // Refresh the file list after deletion
            alert('File deleted successfully!');
        } catch (error) {
            console.error('Error deleting file:', error);
            alert('Error deleting file!');
        }
    };

    const handleFileUpload = async () => {
        try {
            // Trigger click event on the hidden file input
            fileInputRef.current.click();
        } catch (error) {
            console.error('Error triggering file input:', error);
        }
    };
    
    const uploadFile = async (file) => {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('overwrite', 'false');  // Since uploadFile is intended for new uploads
    
            const response = await fetch(fileUploadEndpoint, {
                method: 'POST',
                body: formData, // Sending the file as form data
            });
    
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            fetchFileList();  // Refresh the file list after upload
            alert('File uploaded successfully!');
        } catch (error) {
            console.error('Error uploading file:', error);
            alert('Error uploading file!');
        }
    };

    const handleActivateClick = async () => {
        try {
            // Make the API call to load the selected file into the model engine
            const response = await fetch(`${activateEndpoint}/${selectedFile}`, { method: 'POST' });
            
            if (!response.ok) {
                const data = await response.json(); // Parse the JSON from the response
                throw new Error(data.error || `HTTP error! Status: ${response.status}`);
            }
            
            alert('File activated successfully!');
        } catch (error) {
            console.error('Error activating file:', error);
            alert(`Error activating file! ${error.message}`);
        }
    };

    useEffect(() => {
        // Reset states to their initial values
        setSelectedFile(null);
        setFileContent('');
        setHasUnsavedChanges(false);
        // Fetch the new file list for the given contentType
        fetchFileList();
    }, [contentType]);

    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event.ctrlKey && event.key === 's') {
                event.preventDefault();
                handleSave();
            }
        };
    
        const textarea = textAreaRef.current;
        if (textarea) { // Check if textarea exists in the DOM
            textarea.addEventListener('keydown', handleKeyDown);
    
            // Cleanup: remove event listener when component is unmounted or when textarea is removed from the DOM
            return () => {
                textarea.removeEventListener('keydown', handleKeyDown);
            };
        }
    });

    // Helper function to determine the allowed file types based on contentType
    const getAllowedFileTypes = () => {
        switch (contentType) {
            case 'specs':
                return '.xml';
            case 'code':
                return '.py';
            case 'payload':
                return '*';
            default:
                return '';
        }
    };

    return (
        <div className={`${styles.fileManagementPanel} ${styles[contentType]}`}>
            <h1>{pageTitle}</h1>
            {isLoading ? (
                <p>Loading...</p> // Or any other loading indicator you prefer
            ) : (
                <div className={styles.commonPanelStyles}>
                    {/* File List and Upload Button */}
                    <div className={styles.fileListContainer}>
                        <div className={styles.listActions}>
                            {contentType !== 'payload' && (
                                <button 
                                    onClick={handleActivateClick} 
                                    className={styles.activateButton}
                                    disabled={!selectedFile}
                                >
                                    <i className="fas fa-play"></i> Activate
                                </button>
                            )}
                            {customAction && <button onClick={customAction.action} className={styles.customActionButton}>{customAction.name}</button>}
                            <button 
                                onClick={handleFileUpload}
                                className={styles.uploadButton}
                            >
                                <i className="fas fa-arrow-up"></i>Upload File
                            </button>
                            <input 
                                type="file" 
                                ref={fileInputRef} 
                                style={{ display: 'none' }} 
                                accept={getAllowedFileTypes()} 
                                onChange={(e) => uploadFile(e.target.files[0])}
                            />
                        </div>
                        <ul className={styles.fileList}>
                            {fileList.map(file => (
                                <li 
                                    key={file} 
                                    className={file === selectedFile ? styles.selectedListItem : styles.listItem}
                                    onClick={() => handleFileSelect(file)}
                                >
                                    {file}
                                    <button onClick={() => handleFileDelete(file)} className={styles.deleteButton}>
                                        <i className="fas fa-trash-alt"></i> Delete
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className={styles.textSection}>
                        {/* Text area for file content */}
                        <textarea 
                            ref={textAreaRef}
                            value={fileContent} 
                            onChange={(e) => handleContentChange(e.target.value)} 
                            className={styles.textArea}
                        />
                        
                        {/* Action Buttons */}
                        <div className={styles.textActions}>
                            <button 
                                onClick={handleSave} 
                                disabled={!hasUnsavedChanges}
                                className={styles.saveButton}
                            >
                                <i className="fas fa-save"></i>Save
                            </button>
                            <button 
                                onClick={() => handleFileSelect(selectedFile)}
                                className={styles.revertButton}
                            >
                                <i className="fas fa-undo"></i>Revert
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default FileManagementPanel;