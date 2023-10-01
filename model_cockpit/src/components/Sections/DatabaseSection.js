import React, { useState, useEffect } from 'react';
import styles from '../../styles/sectionStyles.module.scss';

const DatabaseSection = ({ indicatorRef, isActive, onToggle, stats, onWipe, onInitialize }) => {
    return (
        <div className={`${styles.sectionContainer} ${styles.databaseSection}`}>
            <h2 className={styles.title}>Database</h2>

            <div className={styles.iconContainer}>
                <i className="fas fa-database"></i>
            </div>

            {/* Files Section */}
            {isActive && (
                <div className={styles.filesSection}>
                    <p>Stats:</p>
                    <ul>
                        <li>Indexes: {stats.indexes}</li>
                        <li>Total Nodes: {stats.totalNodes}</li>
                        <li>Model Objects: {stats.modelObjects}</li>
                        <li>Composites: {stats.composites}</li>
                    </ul>
                </div>
            )}

            {/* Toggle Button */}
            <div className={styles.toggleContainer}>
                <label className={styles.switch}>
                    <input type="checkbox" checked={isActive} onChange={() => onToggle('db')} />
                    <span ref={indicatorRef} className={styles.slider}></span>
                </label>
            </div>

            {/* Database Controls */}
            <div className={styles.dbControls}>
                <button className={styles.manageButton} onClick={onWipe} disabled={!isActive}>Wipe Database</button>
                <button className={styles.manageButton} onClick={onInitialize} disabled={!isActive}>Initialize Database</button>
            </div>
        </div>
    );
};

export default DatabaseSection;