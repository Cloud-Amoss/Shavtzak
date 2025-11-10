"""
Data models for the staff scheduling optimization system.

This module defines the core data structures:
- Worker: Represents a worker with skills, availability, and work history
- Job: Represents a work assignment with time and staffing requirements
- Config: System configuration parameters
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Assignment:
    """Represents a single job assignment for a worker."""
    job_id: str
    job_name: str
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format
    position: str  # Position filled by worker

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'job_id': self.job_id,
            'job_name': self.job_name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'position': self.position
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Assignment':
        """Create Assignment from dictionary."""
        return cls(
            job_id=data['job_id'],
            job_name=data['job_name'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            position=data['position']
        )


@dataclass
class DailyRecord:
    """Represents a worker's daily work record."""
    date: str  # YYYY-MM-DD format
    jobs_worked: int
    total_hours: float
    assignments: List[Assignment] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'date': self.date,
            'jobs_worked': self.jobs_worked,
            'total_hours': self.total_hours,
            'assignments': [a.to_dict() for a in self.assignments]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DailyRecord':
        """Create DailyRecord from dictionary."""
        return cls(
            date=data['date'],
            jobs_worked=data['jobs_worked'],
            total_hours=data['total_hours'],
            assignments=[Assignment.from_dict(a) for a in data.get('assignments', [])]
        )


@dataclass
class CumulativeStats:
    """Cumulative statistics for a worker across all time."""
    total_hours: float = 0.0
    total_jobs: int = 0
    jobs_by_position: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_hours': self.total_hours,
            'total_jobs': self.total_jobs,
            'jobs_by_position': self.jobs_by_position
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CumulativeStats':
        """Create CumulativeStats from dictionary."""
        return cls(
            total_hours=data.get('total_hours', 0.0),
            total_jobs=data.get('total_jobs', 0),
            jobs_by_position=data.get('jobs_by_position', {})
        )


@dataclass
class Worker:
    """
    Represents a worker with skills, availability, and work history.

    Attributes:
        id: Unique worker identifier
        name: Worker's full name
        rank: Display rank (not used in scheduling logic)
        positions: List of positions/skills the worker has
        days_off: List of dates (YYYY-MM-DD) when worker is unavailable
        cumulative_stats: Lifetime work statistics (never resets)
        daily_history: List of daily work records
    """
    id: int
    name: str
    rank: int
    positions: List[str]
    days_off: List[str] = field(default_factory=list)
    cumulative_stats: CumulativeStats = field(default_factory=CumulativeStats)
    daily_history: List[DailyRecord] = field(default_factory=list)

    def is_available(self, date: str) -> bool:
        """Check if worker is available on given date."""
        return date not in self.days_off

    def has_position(self, position: str) -> bool:
        """Check if worker has a specific position."""
        return position in self.positions

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'rank': self.rank,
            'positions': self.positions,
            'days_off': self.days_off,
            'cumulative_stats': self.cumulative_stats.to_dict(),
            'daily_history': [d.to_dict() for d in self.daily_history]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Worker':
        """Create Worker from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            rank=data['rank'],
            positions=data['positions'],
            days_off=data.get('days_off', []),
            cumulative_stats=CumulativeStats.from_dict(data.get('cumulative_stats', {})),
            daily_history=[DailyRecord.from_dict(d) for d in data.get('daily_history', [])]
        )


@dataclass
class Job:
    """
    Represents a job with time and staffing requirements.

    Attributes:
        id: Unique job identifier
        name: Descriptive job name
        start_time: Start time in HH:MM format
        end_time: End time in HH:MM format
        required_positions: Dict mapping position name to count needed
        priority: Priority level (1=highest, higher numbers=lower priority)
    """
    id: str
    name: str
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format
    required_positions: Dict[str, int]
    priority: int = 1

    def duration_hours(self) -> float:
        """Calculate job duration in hours."""
        from scheduler.utils import time_to_minutes
        start_min = time_to_minutes(self.start_time)
        end_min = time_to_minutes(self.end_time)
        return (end_min - start_min) / 60.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'required_positions': self.required_positions,
            'priority': self.priority
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        """Create Job from dictionary."""
        return cls(
            id=data['id'],
            name=data['name'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            required_positions=data['required_positions'],
            priority=data.get('priority', 1)
        )


@dataclass
class Config:
    """
    System configuration parameters.

    Attributes:
        max_jobs_per_person_per_day: Maximum jobs one worker can have per day
        min_rest_between_jobs_minutes: Minimum rest time between consecutive jobs
        target_hours_per_person_per_day: Target daily work hours
        position_hierarchy: Maps positions to list of positions they can fill
        workload_balance_weight: Weight for workload balancing (0.0-1.0)
        allow_partial_staffing: Whether to allow partial job staffing
    """
    max_jobs_per_person_per_day: int = 1
    min_rest_between_jobs_minutes: int = 0
    target_hours_per_person_per_day: float = 8.0
    position_hierarchy: Dict[str, List[str]] = field(default_factory=dict)
    workload_balance_weight: float = 0.3
    allow_partial_staffing: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'max_jobs_per_person_per_day': self.max_jobs_per_person_per_day,
            'min_rest_between_jobs_minutes': self.min_rest_between_jobs_minutes,
            'target_hours_per_person_per_day': self.target_hours_per_person_per_day,
            'position_hierarchy': self.position_hierarchy,
            'workload_balance_weight': self.workload_balance_weight,
            'allow_partial_staffing': self.allow_partial_staffing
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        """Create Config from dictionary."""
        return cls(
            max_jobs_per_person_per_day=data.get('max_jobs_per_person_per_day', 1),
            min_rest_between_jobs_minutes=data.get('min_rest_between_jobs_minutes', 0),
            target_hours_per_person_per_day=data.get('target_hours_per_person_per_day', 8.0),
            position_hierarchy=data.get('position_hierarchy', {}),
            workload_balance_weight=data.get('workload_balance_weight', 0.3),
            allow_partial_staffing=data.get('allow_partial_staffing', True)
        )
