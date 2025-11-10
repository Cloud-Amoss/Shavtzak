"""
Main scheduling system orchestrator.

This module provides the SchedulingSystem class which coordinates all components:
- Loading data from files
- Running optimization
- Generating schedules
- Updating worker records
- Exporting results
"""

import logging
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from collections import defaultdict

from scheduler.models import Worker, Job, Config, Assignment, DailyRecord
from scheduler.optimizer import ScheduleOptimizer
from scheduler.file_io import (
    load_master_workers,
    save_master_workers,
    load_daily_jobs,
    load_config,
    save_daily_schedule
)
from scheduler.utils import (
    get_current_timestamp,
    calculate_duration_hours,
    calculate_rest_time,
    format_minutes,
    validate_date_format
)

logger = logging.getLogger(__name__)


class SchedulingSystem:
    """
    Main system orchestrator for staff scheduling.

    Coordinates all components to:
    1. Load worker and job data
    2. Optimize schedules
    3. Update worker records
    4. Export results
    """

    def __init__(self):
        """Initialize the scheduling system."""
        self.workers: List[Worker] = []
        self.jobs: List[Job] = []
        self.config: Config = Config()
        self.optimizer: Optional[ScheduleOptimizer] = None
        self.last_updated: str = ""

    def load_master_list(self, filepath: str) -> None:
        """
        Load persistent worker data from JSON file.

        Args:
            filepath: Path to master_workers.json

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If data is invalid
        """
        self.workers, self.last_updated = load_master_workers(filepath)
        logger.info(f"Loaded {len(self.workers)} workers (last updated: {self.last_updated})")

    def load_config(self, filepath: str) -> None:
        """
        Load configuration from JSON file.

        Args:
            filepath: Path to config.json

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If data is invalid
        """
        self.config = load_config(filepath)
        logger.info("Configuration loaded successfully")

    def load_daily_jobs(self, date: str, filepath: str) -> None:
        """
        Load jobs for a specific date from JSON file.

        Args:
            date: Date in YYYY-MM-DD format
            filepath: Path to jobs_YYYY-MM-DD.json

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If data is invalid or date mismatch
        """
        jobs, file_date = load_daily_jobs(filepath)

        if file_date != date:
            raise ValueError(f"Date mismatch: expected {date}, got {file_date} in file")

        self.jobs = jobs
        logger.info(f"Loaded {len(self.jobs)} jobs for {date}")

    def get_available_workers(self, date: str) -> List[Worker]:
        """
        Get workers who are available on the given date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            List of available workers
        """
        return [w for w in self.workers if w.is_available(date)]

    def worker_can_fill_position(self, worker: Worker, position: str) -> bool:
        """
        Check if worker can fill a position based on skills and hierarchy.

        Args:
            worker: Worker to check
            position: Position requirement

        Returns:
            True if worker can fill the position
        """
        # Direct match
        if position in worker.positions:
            return True

        # Check hierarchy
        for worker_position in worker.positions:
            if worker_position in self.config.position_hierarchy:
                fillable = self.config.position_hierarchy[worker_position]
                if position in fillable:
                    return True

        return False

    def solve_schedule(self, date: str, time_limit: int = 30) -> Tuple[Dict, List, Dict]:
        """
        Solve the optimization problem to generate a schedule.

        Args:
            date: Date to schedule (YYYY-MM-DD)
            time_limit: Maximum solve time in seconds

        Returns:
            Tuple of:
            - schedule: Dict with complete schedule data
            - infeasible_jobs: List of jobs that couldn't be fully staffed
            - statistics: Dict of optimization statistics

        Raises:
            ValueError: If no workers or jobs loaded
        """
        if not self.workers:
            raise ValueError("No workers loaded. Call load_master_list() first.")
        if not self.jobs:
            raise ValueError("No jobs loaded. Call load_daily_jobs() first.")

        if not validate_date_format(date):
            raise ValueError(f"Invalid date format: {date}")

        logger.info(f"Starting optimization for {date}")

        # Create and run optimizer
        self.optimizer = ScheduleOptimizer(self.config)
        self.optimizer.build_model(self.workers, self.jobs, date)
        status, solver = self.optimizer.solve(time_limit_seconds=time_limit)

        # Extract solution
        solution = self.optimizer.extract_solution()

        # Build complete schedule structure
        schedule = self._build_schedule_structure(date, status, solution)

        # Identify infeasible jobs
        infeasible_jobs = self._identify_infeasible_jobs(solution)

        # Compile statistics
        statistics = self._compile_statistics(date, status, solution, infeasible_jobs)

        logger.info(f"Schedule optimization complete: {status}")

        return schedule, infeasible_jobs, statistics

    def _build_schedule_structure(
        self,
        date: str,
        status: str,
        solution: Dict
    ) -> Dict[str, Any]:
        """
        Build the complete schedule data structure from optimization solution.

        Args:
            date: Scheduled date
            status: Optimization status
            solution: Solution from optimizer

        Returns:
            Complete schedule dictionary
        """
        assignments = solution['assignments']

        # Group assignments by job
        job_assignments = defaultdict(list)
        for (worker_id, job_id, position), info in assignments.items():
            job_assignments[job_id].append({
                'worker_id': worker_id,
                'position': position
            })

        # Group assignments by worker
        worker_assignments = defaultdict(list)
        for (worker_id, job_id, position), info in assignments.items():
            worker_assignments[worker_id].append({
                'job_id': job_id,
                'position': position
            })

        # Build job assignments list
        job_assignments_list = []
        for job in self.jobs:
            assigned = job_assignments.get(job.id, [])

            # Count assigned vs required for each position
            assigned_by_position = defaultdict(int)
            for assignment in assigned:
                assigned_by_position[assignment['position']] += 1

            # Determine staffing status
            staffing_status = "FULLY_STAFFED"
            for position, count_needed in job.required_positions.items():
                assigned_count = assigned_by_position.get(position, 0)
                if assigned_count == 0:
                    staffing_status = "UNSTAFFED"
                    break
                elif assigned_count < count_needed:
                    staffing_status = "PARTIALLY_STAFFED"

            # Build assigned workers list
            assigned_workers = []
            for assignment in assigned:
                worker = self._get_worker_by_id(assignment['worker_id'])
                if worker:
                    # Calculate cumulative hours for this worker
                    cumulative = worker.cumulative_stats.total_hours + job.duration_hours()

                    assigned_workers.append({
                        'person_id': worker.id,
                        'name': worker.name,
                        'position_filled': assignment['position'],
                        'jobs_today': len(worker_assignments[worker.id]),
                        'hours_today': sum(
                            self._get_job_by_id(a['job_id']).duration_hours()
                            for a in worker_assignments[worker.id]
                        ),
                        'cumulative_hours': cumulative
                    })

            job_assignments_list.append({
                'job_id': job.id,
                'job_name': job.name,
                'start_time': job.start_time,
                'end_time': job.end_time,
                'priority': job.priority,
                'staffing_status': staffing_status,
                'required_positions': job.required_positions,
                'assigned_workers': assigned_workers
            })

        # Build worker schedules list
        worker_schedules = []
        available_workers = self.get_available_workers(date)

        for worker in available_workers:
            assignments_list = worker_assignments.get(worker.id, [])

            if assignments_list:
                # Build assignment details
                assignment_details = []
                jobs_sorted = sorted(
                    [self._get_job_by_id(a['job_id']) for a in assignments_list],
                    key=lambda j: j.start_time
                )

                for i, job in enumerate(jobs_sorted):
                    # Find position for this job
                    position = next(
                        a['position'] for a in assignments_list if a['job_id'] == job.id
                    )

                    # Calculate rest time after this job
                    rest_after = None
                    if i < len(jobs_sorted) - 1:
                        next_job = jobs_sorted[i + 1]
                        rest_after = calculate_rest_time(job.end_time, next_job.start_time)

                    assignment_details.append({
                        'job_id': job.id,
                        'job_name': job.name,
                        'start_time': job.start_time,
                        'end_time': job.end_time,
                        'position': position,
                        'rest_after_minutes': rest_after
                    })

                # Calculate minimum rest time for this worker
                rest_times = [a['rest_after_minutes'] for a in assignment_details
                             if a['rest_after_minutes'] is not None]
                min_rest = min(rest_times) if rest_times else None

                total_hours = sum(job.duration_hours() for job in jobs_sorted)

                worker_schedules.append({
                    'person_id': worker.id,
                    'name': worker.name,
                    'status': 'SCHEDULED',
                    'jobs_today': len(assignments_list),
                    'total_hours_today': total_hours,
                    'cumulative_hours': worker.cumulative_stats.total_hours + total_hours,
                    'assignments': assignment_details,
                    'minimum_rest_time_minutes': min_rest
                })
            else:
                # Worker available but not scheduled
                worker_schedules.append({
                    'person_id': worker.id,
                    'name': worker.name,
                    'status': 'AVAILABLE_NOT_SCHEDULED',
                    'jobs_today': 0,
                    'total_hours_today': 0.0,
                    'cumulative_hours': worker.cumulative_stats.total_hours,
                    'assignments': [],
                    'minimum_rest_time_minutes': None
                })

        # Workers on day off
        workers_on_day_off = [
            {'person_id': w.id, 'name': w.name}
            for w in self.workers
            if not w.is_available(date)
        ]

        return {
            'date': date,
            'generated_at': get_current_timestamp(),
            'optimization_status': status,
            'job_assignments': job_assignments_list,
            'worker_schedules': sorted(worker_schedules, key=lambda x: x['person_id']),
            'workers_on_day_off': workers_on_day_off
        }

    def _identify_infeasible_jobs(self, solution: Dict) -> List[Dict]:
        """
        Identify jobs that couldn't be fully staffed.

        Args:
            solution: Optimization solution

        Returns:
            List of infeasible job details
        """
        assignments = solution['assignments']

        # Count assignments per job per position
        job_position_counts = defaultdict(lambda: defaultdict(int))
        for (worker_id, job_id, position), _ in assignments.items():
            job_position_counts[job_id][position] += 1

        infeasible = []
        for job in self.jobs:
            for position, count_needed in job.required_positions.items():
                assigned_count = job_position_counts[job.id].get(position, 0)

                if assigned_count < count_needed:
                    infeasible.append({
                        'job_id': job.id,
                        'job_name': job.name,
                        'position': position,
                        'required': count_needed,
                        'assigned': assigned_count,
                        'shortage': count_needed - assigned_count
                    })

        return infeasible

    def _compile_statistics(
        self,
        date: str,
        status: str,
        solution: Dict,
        infeasible_jobs: List[Dict]
    ) -> Dict[str, Any]:
        """
        Compile comprehensive statistics from the solution.

        Args:
            date: Scheduled date
            status: Optimization status
            solution: Solution data
            infeasible_jobs: List of infeasible jobs

        Returns:
            Statistics dictionary
        """
        stats = solution.get('statistics', {})
        available_workers = self.get_available_workers(date)
        workers_on_day_off = len(self.workers) - len(available_workers)

        # Count job staffing status
        assignments = solution['assignments']
        job_position_counts = defaultdict(lambda: defaultdict(int))
        for (worker_id, job_id, position), _ in assignments.items():
            job_position_counts[job_id][position] += 1

        jobs_fully_staffed = 0
        jobs_partially_staffed = 0
        jobs_unstaffed = 0

        for job in self.jobs:
            fully_staffed = True
            any_staffed = False

            for position, count_needed in job.required_positions.items():
                assigned = job_position_counts[job.id].get(position, 0)
                if assigned > 0:
                    any_staffed = True
                if assigned < count_needed:
                    fully_staffed = False

            if fully_staffed:
                jobs_fully_staffed += 1
            elif any_staffed:
                jobs_partially_staffed += 1
            else:
                jobs_unstaffed += 1

        # Calculate average rest time
        rest_times = []
        for worker in available_workers:
            worker_jobs = [
                self._get_job_by_id(job_id)
                for (w_id, job_id, pos), _ in assignments.items()
                if w_id == worker.id
            ]
            if len(worker_jobs) >= 2:
                sorted_jobs = sorted(worker_jobs, key=lambda j: j.start_time)
                for i in range(len(sorted_jobs) - 1):
                    rest = calculate_rest_time(sorted_jobs[i].end_time, sorted_jobs[i + 1].start_time)
                    if rest >= 0:
                        rest_times.append(rest)

        avg_rest = sum(rest_times) / len(rest_times) if rest_times else 0

        return {
            'minimum_rest_time_minutes': stats.get('minimum_rest_time_minutes', 0),
            'average_rest_time_minutes': avg_rest,
            'workers_scheduled': stats.get('workers_scheduled', 0),
            'workers_available': len(available_workers),
            'workers_on_day_off': workers_on_day_off,
            'total_jobs': len(self.jobs),
            'jobs_fully_staffed': jobs_fully_staffed,
            'jobs_partially_staffed': jobs_partially_staffed,
            'jobs_unstaffed': jobs_unstaffed,
            'optimization_status': status,
            'solve_time_seconds': stats.get('solve_time_seconds', 0)
        }

    def update_master_list(self, date: str, schedule: Dict) -> None:
        """
        Update master worker list with new assignments.

        Updates cumulative_stats and daily_history for each scheduled worker.

        Args:
            date: Date of the schedule
            schedule: Schedule dictionary from solve_schedule()
        """
        # Extract worker schedules from schedule
        worker_schedules = schedule.get('worker_schedules', [])

        for worker_schedule in worker_schedules:
            if worker_schedule['status'] != 'SCHEDULED':
                continue

            worker_id = worker_schedule['person_id']
            worker = self._get_worker_by_id(worker_id)

            if not worker:
                logger.warning(f"Worker {worker_id} not found in master list")
                continue

            # Build assignments list
            assignments = []
            for assignment_data in worker_schedule['assignments']:
                assignment = Assignment(
                    job_id=assignment_data['job_id'],
                    job_name=assignment_data['job_name'],
                    start_time=assignment_data['start_time'],
                    end_time=assignment_data['end_time'],
                    position=assignment_data['position']
                )
                assignments.append(assignment)

            # Create daily record
            daily_record = DailyRecord(
                date=date,
                jobs_worked=worker_schedule['jobs_today'],
                total_hours=worker_schedule['total_hours_today'],
                assignments=assignments
            )

            # Update cumulative stats
            worker.cumulative_stats.total_hours += worker_schedule['total_hours_today']
            worker.cumulative_stats.total_jobs += worker_schedule['jobs_today']

            for assignment in assignments:
                position = assignment.position
                worker.cumulative_stats.jobs_by_position[position] = \
                    worker.cumulative_stats.jobs_by_position.get(position, 0) + 1

            # Add to daily history
            worker.daily_history.append(daily_record)

        # Update last_updated timestamp
        self.last_updated = date

        logger.info(f"Updated master list with {len([w for w in worker_schedules if w['status'] == 'SCHEDULED'])} worker schedules")

    def export_daily_schedule(self, date: str, schedule: Dict, filepath: str) -> None:
        """
        Export daily schedule to JSON file.

        Args:
            date: Date of schedule
            schedule: Schedule dictionary
            filepath: Output file path

        Raises:
            IOError: If file cannot be written
        """
        # Add warnings for partially staffed jobs
        warnings = []
        for job in schedule['job_assignments']:
            if job['staffing_status'] == 'PARTIALLY_STAFFED':
                warnings.append(
                    f"Job {job['job_id']} '{job['job_name']}' partially staffed"
                )
            elif job['staffing_status'] == 'UNSTAFFED':
                warnings.append(
                    f"Job {job['job_id']} '{job['job_name']}' is unstaffed"
                )

        # Get statistics from schedule
        stats = {
            'minimum_rest_time_minutes': schedule.get('minimum_rest_time_minutes', 0),
            'average_rest_time_minutes': 0,  # Will be calculated
            'workers_scheduled': len([w for w in schedule['worker_schedules'] if w['status'] == 'SCHEDULED']),
            'workers_available': len(schedule['worker_schedules']),
            'workers_on_day_off': len(schedule.get('workers_on_day_off', [])),
            'total_jobs': len(schedule['job_assignments']),
            'jobs_fully_staffed': len([j for j in schedule['job_assignments'] if j['staffing_status'] == 'FULLY_STAFFED']),
            'jobs_partially_staffed': len([j for j in schedule['job_assignments'] if j['staffing_status'] == 'PARTIALLY_STAFFED']),
            'jobs_unstaffed': len([j for j in schedule['job_assignments'] if j['staffing_status'] == 'UNSTAFFED'])
        }

        # Identify infeasible jobs
        infeasible_jobs = []
        for job in schedule['job_assignments']:
            if job['staffing_status'] != 'FULLY_STAFFED':
                infeasible_jobs.append({
                    'job_id': job['job_id'],
                    'job_name': job['job_name'],
                    'status': job['staffing_status']
                })

        output = {
            'date': date,
            'generated_at': schedule.get('generated_at', get_current_timestamp()),
            'optimization_status': schedule.get('optimization_status', 'UNKNOWN'),
            'statistics': stats,
            'job_assignments': schedule['job_assignments'],
            'worker_schedules': schedule['worker_schedules'],
            'workers_on_day_off': schedule.get('workers_on_day_off', []),
            'infeasible_jobs': infeasible_jobs,
            'warnings': warnings
        }

        save_daily_schedule(filepath, output)
        logger.info(f"Exported schedule to {filepath}")

    def export_master_list(self, filepath: str) -> None:
        """
        Save updated master worker list to JSON file.

        Args:
            filepath: Output file path

        Raises:
            IOError: If file cannot be written
        """
        save_master_workers(filepath, self.workers, self.last_updated)
        logger.info(f"Exported master worker list to {filepath}")

    def generate_report(self, date: str, schedule: Dict) -> str:
        """
        Generate human-readable text report of the schedule.

        Args:
            date: Date of schedule
            schedule: Schedule dictionary

        Returns:
            Formatted text report
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"STAFF SCHEDULE REPORT - {date}")
        lines.append("=" * 80)
        lines.append("")

        # Summary statistics
        stats = schedule.get('statistics', {})
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Optimization Status: {schedule.get('optimization_status', 'UNKNOWN')}")
        lines.append(f"Total Jobs: {stats.get('total_jobs', 0)}")
        lines.append(f"  - Fully Staffed: {stats.get('jobs_fully_staffed', 0)}")
        lines.append(f"  - Partially Staffed: {stats.get('jobs_partially_staffed', 0)}")
        lines.append(f"  - Unstaffed: {stats.get('jobs_unstaffed', 0)}")
        lines.append(f"Workers Scheduled: {stats.get('workers_scheduled', 0)} / {stats.get('workers_available', 0)} available")
        lines.append(f"Workers on Day Off: {stats.get('workers_on_day_off', 0)}")
        lines.append(f"Minimum Rest Time: {format_minutes(stats.get('minimum_rest_time_minutes', 0))}")
        lines.append("")

        # Job assignments
        lines.append("JOB ASSIGNMENTS")
        lines.append("-" * 80)
        for job in schedule.get('job_assignments', []):
            lines.append(f"\n[{job['job_id']}] {job['job_name']}")
            lines.append(f"  Time: {job['start_time']} - {job['end_time']}")
            lines.append(f"  Priority: {job['priority']}")
            lines.append(f"  Status: {job['staffing_status']}")
            lines.append(f"  Required Positions: {job['required_positions']}")

            if job['assigned_workers']:
                lines.append(f"  Assigned Workers:")
                for worker in job['assigned_workers']:
                    lines.append(f"    - {worker['name']} ({worker['position_filled']})")
            else:
                lines.append(f"  Assigned Workers: None")

        lines.append("")

        # Worker schedules
        lines.append("WORKER SCHEDULES")
        lines.append("-" * 80)

        scheduled_workers = [w for w in schedule.get('worker_schedules', []) if w['status'] == 'SCHEDULED']
        for worker in scheduled_workers:
            lines.append(f"\n{worker['name']} (ID: {worker['person_id']})")
            lines.append(f"  Jobs Today: {worker['jobs_today']}")
            lines.append(f"  Hours Today: {worker['total_hours_today']:.2f}")
            lines.append(f"  Cumulative Hours: {worker['cumulative_hours']:.2f}")

            if worker.get('minimum_rest_time_minutes') is not None:
                lines.append(f"  Minimum Rest: {format_minutes(worker['minimum_rest_time_minutes'])}")

            lines.append(f"  Assignments:")
            for assignment in worker['assignments']:
                rest_info = ""
                if assignment.get('rest_after_minutes') is not None:
                    rest_info = f" (rest after: {format_minutes(assignment['rest_after_minutes'])})"

                lines.append(
                    f"    {assignment['start_time']}-{assignment['end_time']}: "
                    f"{assignment['job_name']} ({assignment['position']}){rest_info}"
                )

        # Warnings
        warnings = schedule.get('warnings', [])
        if warnings:
            lines.append("")
            lines.append("WARNINGS")
            lines.append("-" * 80)
            for warning in warnings:
                lines.append(f"  ! {warning}")

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

    def get_worker_statistics(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive statistics for a specific worker.

        Args:
            worker_id: Worker ID

        Returns:
            Dictionary with worker statistics, or None if not found
        """
        worker = self._get_worker_by_id(worker_id)
        if not worker:
            return None

        return {
            'id': worker.id,
            'name': worker.name,
            'rank': worker.rank,
            'positions': worker.positions,
            'days_off': worker.days_off,
            'cumulative_stats': worker.cumulative_stats.to_dict(),
            'total_days_worked': len(worker.daily_history),
            'recent_history': [d.to_dict() for d in worker.daily_history[-10:]]  # Last 10 days
        }

    def _get_worker_by_id(self, worker_id: int) -> Optional[Worker]:
        """Helper to find worker by ID."""
        for worker in self.workers:
            if worker.id == worker_id:
                return worker
        return None

    def _get_job_by_id(self, job_id: str) -> Optional[Job]:
        """Helper to find job by ID."""
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None
