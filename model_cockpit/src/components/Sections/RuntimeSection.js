import React from 'react';
import { Link } from 'react-router-dom';
import styles from '../../styles/sectionStyles.module.scss';

const RuntimeSection = ({ indicatorRef, onToggle, isActive, codeFilename }) => {
    return (
        <div className={`${styles.sectionContainer} ${styles.runtimeSection}`}>
            <h2 className={styles.title}>Runtime</h2>

            <div className={styles.iconContainer}>
                <i className="fas fa-code"></i>
            </div>
            <div className={styles.toggleSection}>
                <label className={styles.switch}>
                    <input type="checkbox" checked={isActive} onChange={() => onToggle('runtime')}/>
                    <span ref={indicatorRef} className={styles.slider}></span>
                </label>
            </div>
            <div className={styles.filesSection}>
                <label className={styles.fileNameLabel}>{codeFilename}</label>
                <Link to="/code">
                    <button className={styles.manageButton}>
                        <i className="fas fa-folder-open"></i> Code Files
                    </button>
                </Link>
            </div>
        </div>
    );
};

export default RuntimeSection;
