import React from 'react';
import { Link } from 'react-router-dom';
import styles from '../../styles/sectionStyles.module.scss';

const InterpreterSection = ({ indicatorRef, isActive, onToggle }) => {
    return (
        <div className={`${styles.sectionContainer} ${styles.interpreterSection}`}>
            <h2 className={styles.title}>Interpreter</h2>

            <div className={styles.iconContainer}>
                <i className="fas fa-comments"></i>
            </div>

            {/* File Section */}
            <div className={styles.fileSection}>
                <Link to="/payload">
                    <button className={styles.manageButton}>
                        <i className="fas fa-folder-open"></i> Payload Bay
                    </button>
                </Link>
            </div>

            {/* Toggle Button */}
            <div className={styles.toggleContainer}>
                <label className={styles.switch}>
                    <input type="checkbox" checked={isActive} onChange={() => onToggle('interpreter')} />
                    <span ref={indicatorRef} className={styles.slider}></span>
                </label>
            </div>

            {/* Dynamic Button */}
            {isActive && (
                <div className={styles.terminalContainer}>
                    <a href="/terminal">
                        <button className={styles.manageButton}>
                            <i className="fas fa-terminal"></i> Command Interface
                        </button>
                    </a>
                </div>
            )}
        </div>
    );
};

export default InterpreterSection;