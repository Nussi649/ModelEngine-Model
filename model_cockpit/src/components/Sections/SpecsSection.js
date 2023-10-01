import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import styles from '../../styles/sectionStyles.module.scss';

const SpecsSection = ({ indicatorRef, onToggle, isActive, specsFilename }) => {
    return (
        <div className={`${styles.sectionContainer} ${styles.specsSection}`}>
            <h2 className={styles.title}>Specifications</h2>

            <div className={styles.iconContainer}>
                <i className="fas fa-sitemap"></i>
            </div>
            
            <div className={styles.toggleSection}>
                <label className={styles.switch}>
                    <input type="checkbox" checked={isActive} onChange={() => onToggle('specs')}/>
                    <span ref={indicatorRef} className={styles.slider}></span>
                </label>
            </div>

            <div className={styles.filesSection}>
                <label className={styles.fileNameLabel}>{specsFilename}</label>
                <Link to="/specs">
                    <button className={styles.manageButton}>
                        <i className="fas fa-folder-open"></i> Specification Files
                    </button>
                </Link>
            </div>
        </div>
    );
};

export default SpecsSection;