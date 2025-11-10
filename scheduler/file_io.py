"""
File I/O functions for loading and saving scheduler data.

Handles JSON serialization/deserialization for:
- Master worker list
- Daily jobs
- Configuration
- Daily schedules
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

from scheduler.models import Worker, Job, Config
from scheduler.utils import validate_date_format

logger = logging.getLogger(__name__)


def load_master_workers(filepath: str) -> Tuple[List[Worker], str]:
    """
    Load master worker list from JSON file.

    Args:
        filepath: Path to master_workers.json file

    Returns:
        Tuple of (list of Worker objects, last_updated date string)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed or invalid
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Master workers file not found: {filepath}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")

    if 'workers' not in data:
        raise ValueError(f"Missing 'workers' key in {filepath}")

    workers = []
    for worker_data in data['workers']:
        try:
            worker = Worker.from_dict(worker_data)
            workers.append(worker)
        except Exception as e:
            logger.error(f"Error loading worker {worker_data.get('id', 'unknown')}: {e}")
            raise ValueError(f"Invalid worker data: {e}")

    last_updated = data.get('last_updated', '')
    logger.info(f"Loaded {len(workers)} workers from {filepath}")

    return workers, last_updated


def save_master_workers(filepath: str, workers: List[Worker], last_updated: str = None) -> None:
    """
    Save master worker list to JSON file.

    Args:
        filepath: Path to output file
        workers: List of Worker objects
        last_updated: Last update date (defaults to current date)

    Raises:
        IOError: If file cannot be written
    """
    if last_updated is None:
        last_updated = datetime.now().strftime('%Y-%m-%d')

    data = {
        'last_updated': last_updated,
        'workers': [worker.to_dict() for worker in workers]
    }

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(workers)} workers to {filepath}")
    except IOError as e:
        raise IOError(f"Cannot write to {filepath}: {e}")


def load_daily_jobs(filepath: str) -> Tuple[List[Job], str]:
    """
    Load daily jobs from JSON file.

    Args:
        filepath: Path to jobs_YYYY-MM-DD.json file

    Returns:
        Tuple of (list of Job objects, date string)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed or invalid
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Jobs file not found: {filepath}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")

    if 'jobs' not in data:
        raise ValueError(f"Missing 'jobs' key in {filepath}")

    date = data.get('date', '')
    if not date or not validate_date_format(date):
        raise ValueError(f"Invalid or missing date in {filepath}")

    jobs = []
    for job_data in data['jobs']:
        try:
            job = Job.from_dict(job_data)
            jobs.append(job)
        except Exception as e:
            logger.error(f"Error loading job {job_data.get('id', 'unknown')}: {e}")
            raise ValueError(f"Invalid job data: {e}")

    logger.info(f"Loaded {len(jobs)} jobs for {date} from {filepath}")

    return jobs, date


def load_config(filepath: str) -> Config:
    """
    Load configuration from JSON file.

    Args:
        filepath: Path to config.json file

    Returns:
        Config object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed or invalid
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {filepath}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")

    try:
        config = Config.from_dict(data)
        logger.info(f"Loaded configuration from {filepath}")
        return config
    except Exception as e:
        raise ValueError(f"Invalid config data: {e}")


def save_config(filepath: str, config: Config) -> None:
    """
    Save configuration to JSON file.

    Args:
        filepath: Path to output file
        config: Config object

    Raises:
        IOError: If file cannot be written
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved configuration to {filepath}")
    except IOError as e:
        raise IOError(f"Cannot write to {filepath}: {e}")


def save_daily_schedule(filepath: str, schedule_data: Dict[str, Any]) -> None:
    """
    Save daily schedule to JSON file.

    Args:
        filepath: Path to output file (e.g., schedule_2025-11-10.json)
        schedule_data: Complete schedule data dictionary

    Raises:
        IOError: If file cannot be written
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved daily schedule to {filepath}")
    except IOError as e:
        raise IOError(f"Cannot write to {filepath}: {e}")


def load_daily_schedule(filepath: str) -> Dict[str, Any]:
    """
    Load daily schedule from JSON file.

    Args:
        filepath: Path to schedule file

    Returns:
        Schedule data dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Schedule file not found: {filepath}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded schedule from {filepath}")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")
