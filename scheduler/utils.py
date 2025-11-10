"""
Utility functions for the scheduling system.

Provides helper functions for:
- Time parsing and conversion
- Job overlap detection
- Rest time calculation
"""

import re
from datetime import datetime, timedelta
from typing import Tuple


def validate_time_format(time_str: str) -> bool:
    """
    Validate that time string is in HH:MM format.

    Args:
        time_str: Time string to validate

    Returns:
        True if valid, False otherwise
    """
    pattern = r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$'
    return bool(re.match(pattern, time_str))


def validate_date_format(date_str: str) -> bool:
    """
    Validate that date string is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def time_to_minutes(time_str: str) -> int:
    """
    Convert HH:MM time string to minutes since midnight.

    Args:
        time_str: Time in HH:MM format

    Returns:
        Minutes since midnight (0-1439)

    Raises:
        ValueError: If time format is invalid
    """
    if not validate_time_format(time_str):
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM")

    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes


def minutes_to_time(minutes: int) -> str:
    """
    Convert minutes since midnight to HH:MM format.

    Args:
        minutes: Minutes since midnight

    Returns:
        Time string in HH:MM format
    """
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def calculate_duration_hours(start_time: str, end_time: str) -> float:
    """
    Calculate duration between two times in hours.

    Args:
        start_time: Start time in HH:MM format
        end_time: End time in HH:MM format

    Returns:
        Duration in hours

    Raises:
        ValueError: If time formats are invalid
    """
    start_min = time_to_minutes(start_time)
    end_min = time_to_minutes(end_time)

    if end_min < start_min:
        raise ValueError(f"End time {end_time} is before start time {start_time}")

    return (end_min - start_min) / 60.0


def calculate_rest_time(job1_end: str, job2_start: str) -> int:
    """
    Calculate rest time in minutes between end of job1 and start of job2.

    Args:
        job1_end: End time of first job (HH:MM)
        job2_start: Start time of second job (HH:MM)

    Returns:
        Rest time in minutes (can be negative if jobs overlap)
    """
    end_min = time_to_minutes(job1_end)
    start_min = time_to_minutes(job2_start)
    return start_min - end_min


def jobs_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """
    Check if two time ranges overlap.

    Two jobs overlap if one starts before the other ends.

    Args:
        start1: Start time of first job (HH:MM)
        end1: End time of first job (HH:MM)
        start2: Start time of second job (HH:MM)
        end2: End time of second job (HH:MM)

    Returns:
        True if jobs overlap, False otherwise
    """
    start1_min = time_to_minutes(start1)
    end1_min = time_to_minutes(end1)
    start2_min = time_to_minutes(start2)
    end2_min = time_to_minutes(end2)

    # Jobs overlap if start of one is before end of the other
    # and vice versa
    return start1_min < end2_min and start2_min < end1_min


def get_current_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        Current timestamp string (e.g., "2025-11-10T06:30:00Z")
    """
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def format_minutes(minutes: int) -> str:
    """
    Format minutes into human-readable string.

    Args:
        minutes: Number of minutes

    Returns:
        Formatted string (e.g., "2h 30m" or "45m")
    """
    if minutes < 0:
        return f"-{format_minutes(-minutes)}"

    hours = minutes // 60
    mins = minutes % 60

    if hours > 0:
        if mins > 0:
            return f"{hours}h {mins}m"
        return f"{hours}h"
    return f"{mins}m"


def parse_date(date_str: str) -> datetime:
    """
    Parse date string in YYYY-MM-DD format.

    Args:
        date_str: Date string

    Returns:
        datetime object

    Raises:
        ValueError: If date format is invalid
    """
    if not validate_date_format(date_str):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")

    return datetime.strptime(date_str, '%Y-%m-%d')
