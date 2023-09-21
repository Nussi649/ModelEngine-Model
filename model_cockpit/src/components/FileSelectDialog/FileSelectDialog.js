import React, { useState, useEffect } from 'react';
import styles from './FileSelectDialog.module.css';

function FileSelectDialog({
    isOpen,
    dialogName,
    fetchFileListEndpoint,
    fetchFileContentEndpoint,
    uploadFileEndpoint,
    onFileSelect,
    onDismiss
}) {
    const [fileList, setFileList] = useState([]);

    useEffect(() => {
        if (isOpen) {
            fetchFileList();
        }
    }, [isOpen, fetchFileListEndpoint]);

    const fetchFileList = () => {
        // Fetch the list of files from the provided endpoint
        fetch(fetchFileListEndpoint)
            .then(response => response.json())
            .then(data => setFileList(data))
            .catch(error => console.error('Error fetching files:', error));
    }

    const handleFileUpload = (file) => {
        // Logic to upload a new file
        // Assuming you'll use FormData for the file upload
        const formData = new FormData();
        formData.append('file', file);

        fetch(uploadFileEndpoint, {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                fetchFileList(); // Re-fetch the file list after a successful upload
            })
            .catch(error => console.error('Error uploading file:', error));
    };

    const dismissDialog = () => {
        onDismiss();
    };

    return (
        isOpen && (
            <div className={styles.dialog}>
                <div className={styles.dialogHeader}>
                    <h3>{dialogName}</h3>
                    <button className={styles.closeButton} onClick={dismissDialog}>X</button>
                </div>
                <ul>
                    {fileList.map(file => (
                        <li key={file} onClick={() => onFileSelect(file)}>
                            {file}
                        </li>
                    ))}
                </ul>
                <input 
                    type="file" 
                    onChange={e => handleFileUpload(e.target.files[0])} 
                />
            </div>
        )
    );
}

export default FileSelectDialog;