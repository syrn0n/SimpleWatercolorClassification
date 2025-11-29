import sqlite3
import hashlib
import os
from datetime import datetime
from typing import Optional, Dict, Tuple, Any
from pathlib import Path


class DatabaseManager:
    """Manages SQLite database for caching classification results."""

    VERSION = "1.0.0"

    def __init__(self, db_path: str = "classification_cache.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._init_schema()

    def _connect(self):
        """Establish database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

    def _init_schema(self):
        """Create database tables and indexes if they don't exist."""
        cursor = self.conn.cursor()

        # Create main table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classification_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_mtime REAL NOT NULL,

                -- Classification results
                file_type TEXT NOT NULL,
                is_watercolor BOOLEAN NOT NULL,
                confidence REAL NOT NULL,

                -- Video-specific fields (NULL for images)
                duration_seconds REAL,
                total_frames INTEGER,
                processed_frames INTEGER,
                planned_frames INTEGER,
                watercolor_frames_count INTEGER,
                percent_watercolor_frames REAL,
                avg_watercolor_confidence REAL,

                -- Metadata
                classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                classification_version TEXT,

                -- Immich integration
                immich_tagged BOOLEAN DEFAULT 0,
                immich_tag_id TEXT,
                immich_asset_id TEXT,

                -- Move tracking
                moved_to TEXT,
                moved_at TIMESTAMP,

                -- Error tracking
                error TEXT,

                UNIQUE(file_hash, file_path)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path
            ON classification_results(file_path)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_hash
            ON classification_results(file_hash)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_classified_at
            ON classification_results(classified_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_watercolor
            ON classification_results(is_watercolor)
        """)

        # Migration: Add top_label column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE classification_results ADD COLUMN top_label TEXT")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass

        # Migration: Add error column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE classification_results ADD COLUMN error TEXT")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass

        self.conn.commit()

    def calculate_file_hash(self, file_path: str) -> str:
        """
        Calculate SHA-256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of file hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_file_info(self, file_path: str) -> Tuple[int, float]:
        """
        Get file size and modification time.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (size_bytes, mtime_timestamp)
        """
        stat = os.stat(file_path)
        return stat.st_size, stat.st_mtime

    def check_if_processed(self, file_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file needs processing.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (needs_processing, cached_result)
            - needs_processing: True if file should be processed
            - cached_result: Previous result dict if available, None otherwise
        """
        if not os.path.exists(file_path):
            return True, None

        # Calculate current file info
        current_hash = self.calculate_file_hash(file_path)
        current_size, current_mtime = self.get_file_info(file_path)

        # Normalize path for consistent comparison
        normalized_path = os.path.normpath(file_path)

        # Check by path first
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM classification_results
            WHERE file_path = ?
            ORDER BY classified_at DESC
            LIMIT 1
        """, (normalized_path,))

        row = cursor.fetchone()

        if row:
            # File exists in DB at this path
            if row['file_hash'] == current_hash:
                # File unchanged, use cached result
                return False, dict(row)
            else:
                # File changed, needs reprocessing
                return True, None

        # Check if file was moved (search by hash)
        cursor.execute("""
            SELECT * FROM classification_results
            WHERE file_hash = ?
            ORDER BY classified_at DESC
            LIMIT 1
        """, (current_hash,))
        
        moved_row = cursor.fetchone()

        if moved_row:
            # File was moved, update location
            self.update_moved_location(moved_row['file_path'], normalized_path)
            result = dict(moved_row)
            result['file_path'] = normalized_path
            return False, result

        # New file, needs processing
        return True, None

    def check_if_processed_quick(self, file_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file needs processing using quick check (filename only).

        Args:
            file_path: Path to file

        Returns:
            Tuple of (needs_processing, cached_result)
        """
        if not os.path.exists(file_path):
            return True, None

        # Normalize path for consistent comparison
        normalized_path = os.path.normpath(file_path)

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM classification_results
            WHERE file_path = ?
            ORDER BY classified_at DESC
            LIMIT 1
        """, (normalized_path,))

        row = cursor.fetchone()

        if row:
            # File exists in DB at this path - assume valid for quick sync
            return False, dict(row)

        return True, None

    def save_result(self, file_path: str, result_data: Dict[str, Any]):
        """
        Save classification result to database.

        Args:
            file_path: Path to file
            result_data: Dictionary containing classification results
        """
        # Calculate file info
        file_hash = self.calculate_file_hash(file_path)
        file_size, file_mtime = self.get_file_info(file_path)

        # Normalize path
        normalized_path = os.path.normpath(file_path)

        cursor = self.conn.cursor()

        # Check if entry exists
        cursor.execute("""
            SELECT id FROM classification_results
            WHERE file_path = ? AND file_hash = ?
        """, (normalized_path, file_hash))

        existing = cursor.fetchone()

        if existing:
            # Update existing entry
            cursor.execute("""
                UPDATE classification_results SET
                    file_size = ?,
                    file_mtime = ?,
                    file_type = ?,
                    is_watercolor = ?,
                    confidence = ?,
                    duration_seconds = ?,
                    total_frames = ?,
                    processed_frames = ?,
                    planned_frames = ?,
                    watercolor_frames_count = ?,
                    percent_watercolor_frames = ?,
                    avg_watercolor_confidence = ?,
                    top_label = ?,
                    error = ?,
                    classified_at = CURRENT_TIMESTAMP,
                    classification_version = ?
                WHERE id = ?
            """, (
                file_size,
                file_mtime,
                result_data.get('file_type', 'image'),
                result_data.get('is_watercolor', False),
                result_data.get('confidence', 0.0),
                result_data.get('duration_seconds'),
                result_data.get('total_frames'),
                result_data.get('processed_frames'),
                result_data.get('planned_frames'),
                result_data.get('watercolor_frames_count'),
                result_data.get('percent_watercolor_frames'),
                result_data.get('avg_watercolor_confidence'),
                result_data.get('top_label'),
                result_data.get('error'),
                self.VERSION,
                existing['id']
            ))
        else:
            # Insert new entry
            cursor.execute("""
                INSERT INTO classification_results (
                    file_path, file_hash, file_size, file_mtime,
                    file_type, is_watercolor, confidence,
                    duration_seconds, total_frames, processed_frames, planned_frames,
                    watercolor_frames_count, percent_watercolor_frames,
                    avg_watercolor_confidence, top_label, error, classification_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                normalized_path,
                file_hash,
                file_size,
                file_mtime,
                result_data.get('file_type', 'image'),
                result_data.get('is_watercolor', False),
                result_data.get('confidence', 0.0),
                result_data.get('duration_seconds'),
                result_data.get('total_frames'),
                result_data.get('processed_frames'),
                result_data.get('planned_frames'),
                result_data.get('watercolor_frames_count'),
                result_data.get('percent_watercolor_frames'),
                result_data.get('avg_watercolor_confidence'),
                result_data.get('top_label'),
                result_data.get('error'),
                self.VERSION
            ))

        self.conn.commit()

    def update_moved_location(self, old_path: str, new_path: str):
        """
        Update file location when file is moved.

        Args:
            old_path: Previous file path
            new_path: New file path
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE classification_results SET
                moved_to = ?,
                moved_at = CURRENT_TIMESTAMP,
                file_path = ?
            WHERE file_path = ?
        """, (new_path, new_path, os.path.normpath(old_path)))
        self.conn.commit()

    def update_immich_info(self, file_path: str, tag_id: str = None, asset_id: str = None):
        """
        Update Immich integration information.

        Args:
            file_path: Path to file
            tag_id: Immich tag ID
            asset_id: Immich asset ID
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE classification_results SET
                immich_tagged = 1,
                immich_tag_id = ?,
                immich_asset_id = ?
            WHERE file_path = ?
        """, (tag_id, asset_id, os.path.normpath(file_path)))
        self.conn.commit()

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        cursor = self.conn.cursor()

        stats = {}

        # Total files
        cursor.execute("SELECT COUNT(*) as count FROM classification_results")
        stats['total_files'] = cursor.fetchone()['count']

        # Watercolor count
        cursor.execute("""
            SELECT COUNT(*) as count FROM classification_results
            WHERE is_watercolor = 1
        """)
        stats['watercolor_count'] = cursor.fetchone()['count']

        # Image count
        cursor.execute("""
            SELECT COUNT(*) as count FROM classification_results
            WHERE file_type = 'image'
        """)
        stats['image_count'] = cursor.fetchone()['count']

        # Video count
        cursor.execute("""
            SELECT COUNT(*) as count FROM classification_results
            WHERE file_type = 'video'
        """)
        stats['video_count'] = cursor.fetchone()['count']

        # Moved files count
        cursor.execute("""
            SELECT COUNT(*) as count FROM classification_results
            WHERE moved_to IS NOT NULL
        """)
        stats['moved_files_count'] = cursor.fetchone()['count']

        # Immich tagged count
        cursor.execute("""
            SELECT COUNT(*) as count FROM classification_results
            WHERE immich_tagged = 1
        """)
        stats['immich_tagged_count'] = cursor.fetchone()['count']

        return stats

    def clear_cache(self):
        """Clear all cached results."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM classification_results")
        self.conn.commit()

    def get_all_results(self):
        """
        Get all classification results from the database.
        
        Yields:
            Dictionary containing classification result data
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM classification_results
            ORDER BY classified_at DESC
        """)
        
        for row in cursor:
            yield dict(row)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
