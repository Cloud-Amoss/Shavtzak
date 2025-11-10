"""
Staff Scheduling Optimization System

A comprehensive Python scheduling system using Google OR-Tools that optimizes
daily work assignments while maintaining historical tracking and ensuring
fairness across time.
"""

__version__ = "1.0.0"

from scheduler.models import Worker, Job, Config, Assignment, DailyRecord, CumulativeStats
from scheduler.scheduling_system import SchedulingSystem

__all__ = [
    'Worker',
    'Job',
    'Config',
    'Assignment',
    'DailyRecord',
    'CumulativeStats',
    'SchedulingSystem',
]
