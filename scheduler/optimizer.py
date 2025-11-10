"""
Optimization engine using Google OR-Tools CP-SAT solver.

This module implements the Mixed Integer Linear Programming (MILP) model
that optimizes staff scheduling with the following objectives:
1. Maximize minimum rest time between consecutive job assignments
2. Balance cumulative workload fairly across workers
3. Prioritize high-priority jobs when resources are constrained
"""

import logging
from typing import List, Dict, Tuple, Set, Optional
from ortools.sat.python import cp_model

from scheduler.models import Worker, Job, Config
from scheduler.utils import time_to_minutes, jobs_overlap, calculate_rest_time

logger = logging.getLogger(__name__)


class ScheduleOptimizer:
    """
    Optimizer that creates optimal work schedules using OR-Tools CP-SAT solver.
    """

    def __init__(self, config: Config):
        """
        Initialize the optimizer with configuration.

        Args:
            config: System configuration
        """
        self.config = config
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Decision variables (populated during optimization)
        self.x = {}  # x[worker_id, job_id, position] = assignment variable
        self.worker_assigned_to_job = {}  # worker_assigned_to_job[worker_id, job_id]
        self.min_rest_time = None  # Minimum rest time variable (to maximize)

        # Data (set during solve)
        self.workers: List[Worker] = []
        self.jobs: List[Job] = []
        self.available_workers: List[Worker] = []
        self.solve_status = None  # Status from solve()

    def worker_can_fill_position(self, worker: Worker, position: str) -> bool:
        """
        Check if worker can fill a position based on their skills and hierarchy.

        A worker can fill a position if:
        1. They have the exact position in their positions list, OR
        2. They have a position that includes the required position in its hierarchy

        Args:
            worker: Worker to check
            position: Position requirement to fill

        Returns:
            True if worker can fill the position
        """
        # Direct match
        if position in worker.positions:
            return True

        # Check if any of worker's positions can fill this position via hierarchy
        for worker_position in worker.positions:
            if worker_position in self.config.position_hierarchy:
                fillable_positions = self.config.position_hierarchy[worker_position]
                if position in fillable_positions:
                    return True

        return False

    def get_eligible_workers(self, position: str) -> List[Worker]:
        """
        Get all available workers who can fill a given position.

        Args:
            position: Position to fill

        Returns:
            List of eligible workers
        """
        return [w for w in self.available_workers if self.worker_can_fill_position(w, position)]

    def jobs_overlap_check(self, job1: Job, job2: Job) -> bool:
        """
        Check if two jobs have overlapping time ranges.

        Args:
            job1: First job
            job2: Second job

        Returns:
            True if jobs overlap
        """
        return jobs_overlap(job1.start_time, job1.end_time, job2.start_time, job2.end_time)

    def create_decision_variables(self) -> None:
        """Create all decision variables for the optimization model."""
        # Binary variable: x[worker_id, job_id, position] = 1 if worker assigned to job in position
        for worker in self.available_workers:
            for job in self.jobs:
                for position in job.required_positions.keys():
                    if self.worker_can_fill_position(worker, position):
                        var_name = f'x_w{worker.id}_j{job.id}_p{position}'
                        self.x[worker.id, job.id, position] = self.model.NewBoolVar(var_name)

        # Binary variable: worker_assigned_to_job[worker_id, job_id] = 1 if worker assigned to job
        for worker in self.available_workers:
            for job in self.jobs:
                var_name = f'assigned_w{worker.id}_j{job.id}'
                self.worker_assigned_to_job[worker.id, job.id] = self.model.NewBoolVar(var_name)

        # Integer variable: minimum rest time across all workers (to maximize)
        self.min_rest_time = self.model.NewIntVar(0, 1440, 'min_rest_time')

        logger.info(f"Created {len(self.x)} assignment variables and {len(self.worker_assigned_to_job)} worker-job variables")

    def add_staffing_constraints(self) -> None:
        """
        Add constraints to ensure jobs are staffed according to requirements.

        If partial staffing is allowed, assigns at least 1 worker (if available) up to count needed.
        Otherwise, requires exact count.
        """
        for job in self.jobs:
            for position, count_needed in job.required_positions.items():
                eligible_workers = self.get_eligible_workers(position)

                if not eligible_workers:
                    logger.warning(f"No eligible workers for job {job.id} position {position}")
                    continue

                # Sum of workers assigned to this position in this job
                assigned = sum(
                    self.x[w.id, job.id, position]
                    for w in eligible_workers
                    if (w.id, job.id, position) in self.x
                )

                if self.config.allow_partial_staffing:
                    # Assign at least 1 if anyone available, up to count_needed
                    self.model.Add(assigned >= 1)
                    self.model.Add(assigned <= count_needed)
                else:
                    # Must assign exactly count_needed
                    self.model.Add(assigned == count_needed)

        logger.info("Added staffing constraints")

    def add_no_overlap_constraints(self) -> None:
        """
        Add constraints to prevent workers from being assigned to overlapping jobs.
        """
        overlap_constraints = 0
        for worker in self.available_workers:
            for i, job1 in enumerate(self.jobs):
                for job2 in self.jobs[i + 1:]:
                    if self.jobs_overlap_check(job1, job2):
                        # Worker cannot be assigned to both overlapping jobs
                        if (worker.id, job1.id) in self.worker_assigned_to_job and \
                           (worker.id, job2.id) in self.worker_assigned_to_job:
                            self.model.Add(
                                self.worker_assigned_to_job[worker.id, job1.id] +
                                self.worker_assigned_to_job[worker.id, job2.id] <= 1
                            )
                            overlap_constraints += 1

        logger.info(f"Added {overlap_constraints} no-overlap constraints")

    def add_max_jobs_constraints(self) -> None:
        """
        Add constraints to limit maximum jobs per worker per day.
        """
        for worker in self.available_workers:
            jobs_for_worker = [
                self.worker_assigned_to_job[worker.id, job.id]
                for job in self.jobs
                if (worker.id, job.id) in self.worker_assigned_to_job
            ]

            if jobs_for_worker:
                self.model.Add(
                    sum(jobs_for_worker) <= self.config.max_jobs_per_person_per_day
                )

        logger.info(f"Added max {self.config.max_jobs_per_person_per_day} jobs per worker constraints")

    def add_linking_constraints(self) -> None:
        """
        Link worker_assigned_to_job variables to position assignment variables.

        worker_assigned_to_job[w,j] is true if w is assigned to any position in job j.
        """
        for worker in self.available_workers:
            for job in self.jobs:
                # Get all positions this worker could fill in this job
                eligible_positions = [
                    pos for pos in job.required_positions.keys()
                    if self.worker_can_fill_position(worker, pos)
                ]

                if not eligible_positions:
                    continue

                # worker_assigned_to_job is true if assigned to any position
                position_vars = [
                    self.x[worker.id, job.id, pos]
                    for pos in eligible_positions
                    if (worker.id, job.id, pos) in self.x
                ]

                if position_vars and (worker.id, job.id) in self.worker_assigned_to_job:
                    # If assigned to any position, then worker_assigned_to_job must be true
                    for pos_var in position_vars:
                        self.model.Add(
                            self.worker_assigned_to_job[worker.id, job.id] >= pos_var
                        )

                    # If worker_assigned_to_job is true, at least one position must be assigned
                    self.model.Add(
                        sum(position_vars) >= self.worker_assigned_to_job[worker.id, job.id]
                    )

        logger.info("Added linking constraints between position and job assignments")

    def add_one_position_per_job_constraints(self) -> None:
        """
        Ensure each worker fills at most one position per job.
        """
        for worker in self.available_workers:
            for job in self.jobs:
                eligible_positions = [
                    pos for pos in job.required_positions.keys()
                    if self.worker_can_fill_position(worker, pos) and
                    (worker.id, job.id, pos) in self.x
                ]

                if len(eligible_positions) > 1:
                    # Worker can fill at most one position in this job
                    self.model.Add(
                        sum(self.x[worker.id, job.id, pos] for pos in eligible_positions) <= 1
                    )

        logger.info("Added one position per job constraints")

    def add_minimum_rest_time_constraints(self) -> None:
        """
        Add constraints to track and maximize minimum rest time between consecutive jobs.
        """
        rest_constraints = 0

        for worker in self.available_workers:
            # Get all jobs this worker could potentially be assigned to
            worker_jobs = [
                job for job in self.jobs
                if (worker.id, job.id) in self.worker_assigned_to_job
            ]

            if len(worker_jobs) < 2:
                continue

            # Sort jobs by start time
            sorted_jobs = sorted(worker_jobs, key=lambda j: time_to_minutes(j.start_time))

            # Check consecutive jobs
            for i in range(len(sorted_jobs) - 1):
                job1 = sorted_jobs[i]
                job2 = sorted_jobs[i + 1]

                rest_minutes = calculate_rest_time(job1.end_time, job2.start_time)

                if rest_minutes < 0:
                    # Jobs overlap, already handled by overlap constraints
                    continue

                # Create boolean for "both jobs assigned"
                both_assigned = self.model.NewBoolVar(
                    f'both_w{worker.id}_j{job1.id}_j{job2.id}'
                )

                # both_assigned is true iff both jobs are assigned to this worker
                self.model.Add(
                    self.worker_assigned_to_job[worker.id, job1.id] +
                    self.worker_assigned_to_job[worker.id, job2.id] == 2
                ).OnlyEnforceIf(both_assigned)

                self.model.Add(
                    self.worker_assigned_to_job[worker.id, job1.id] +
                    self.worker_assigned_to_job[worker.id, job2.id] <= 1
                ).OnlyEnforceIf(both_assigned.Not())

                # If both assigned, rest time must be at least min_rest_time
                if rest_minutes >= self.config.min_rest_between_jobs_minutes:
                    # This rest time contributes to the minimum
                    self.model.Add(rest_minutes >= self.min_rest_time).OnlyEnforceIf(both_assigned)
                    rest_constraints += 1

        logger.info(f"Added {rest_constraints} minimum rest time constraints")

    def create_objective(self) -> None:
        """
        Create the objective function that balances multiple goals.

        Objectives (in order of priority):
        1. Maximize minimum rest time between consecutive jobs
        2. Balance cumulative workload across workers
        3. Prioritize high-priority jobs to be fully staffed
        """
        objective_terms = []

        # Primary objective: Maximize minimum rest time
        # Scale up significantly to make it the dominant factor
        objective_terms.append(self.min_rest_time * 1000)

        # Secondary objective: Balance cumulative workload
        # Penalize assigning work to workers with more cumulative hours
        if self.config.workload_balance_weight > 0:
            for worker in self.available_workers:
                for job in self.jobs:
                    if (worker.id, job.id) not in self.worker_assigned_to_job:
                        continue

                    hours = job.duration_hours()
                    cumulative_hours = worker.cumulative_stats.total_hours

                    # Penalty proportional to cumulative hours
                    penalty = int(cumulative_hours * hours * self.config.workload_balance_weight * 10)

                    objective_terms.append(
                        -penalty * self.worker_assigned_to_job[worker.id, job.id]
                    )

        # Tertiary objective: Prioritize high-priority jobs
        # Penalize understaffing of high-priority jobs more heavily
        for job in self.jobs:
            for position, count_needed in job.required_positions.items():
                eligible_workers = self.get_eligible_workers(position)

                if not eligible_workers:
                    continue

                assigned = sum(
                    self.x[w.id, job.id, position]
                    for w in eligible_workers
                    if (w.id, job.id, position) in self.x
                )

                # Create variable for understaffing
                understaffed = self.model.NewIntVar(0, count_needed, f'understaffed_{job.id}_{position}')
                self.model.Add(understaffed == count_needed - assigned)

                # Higher priority (lower number) = higher penalty for understaffing
                priority_penalty = (10 - job.priority) * 100

                objective_terms.append(-priority_penalty * understaffed)

        # Set objective to maximize
        if objective_terms:
            self.model.Maximize(sum(objective_terms))
            logger.info(f"Created objective with {len(objective_terms)} terms")
        else:
            logger.warning("No objective terms created")

    def build_model(self, workers: List[Worker], jobs: List[Job], date: str) -> None:
        """
        Build the complete optimization model.

        Args:
            workers: List of all workers
            jobs: List of all jobs for the day
            date: Date being scheduled (YYYY-MM-DD)
        """
        self.workers = workers
        self.jobs = jobs
        self.available_workers = [w for w in workers if w.is_available(date)]

        logger.info(f"Building model for {date}")
        logger.info(f"Total workers: {len(workers)}, Available: {len(self.available_workers)}, Jobs: {len(jobs)}")

        # Create fresh model
        self.model = cp_model.CpModel()
        self.x = {}
        self.worker_assigned_to_job = {}

        # Build model step by step
        self.create_decision_variables()
        self.add_staffing_constraints()
        self.add_no_overlap_constraints()
        self.add_max_jobs_constraints()
        self.add_linking_constraints()
        self.add_one_position_per_job_constraints()
        self.add_minimum_rest_time_constraints()
        self.create_objective()

        logger.info("Model building complete")

    def solve(self, time_limit_seconds: int = 30) -> Tuple[str, Optional[cp_model.CpSolver]]:
        """
        Solve the optimization model.

        Args:
            time_limit_seconds: Maximum time to spend solving

        Returns:
            Tuple of (status_string, solver object)
            Status can be: OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN
        """
        self.solver.parameters.max_time_in_seconds = time_limit_seconds
        self.solver.parameters.log_search_progress = False

        logger.info(f"Starting solver (time limit: {time_limit_seconds}s)...")
        status = self.solver.Solve(self.model)
        self.solve_status = status  # Store for later use

        status_name = self.solver.StatusName(status)
        logger.info(f"Solver finished with status: {status_name}")

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.info(f"Objective value: {self.solver.ObjectiveValue()}")
            logger.info(f"Solve time: {self.solver.WallTime():.2f}s")

        return status_name, self.solver

    def extract_solution(self) -> Dict[str, any]:
        """
        Extract the solution from the solved model.

        Returns:
            Dictionary containing:
            - assignments: Dict mapping (worker_id, job_id, position) to assignment info
            - statistics: Dict with solution statistics
        """
        if self.solve_status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            logger.warning("Cannot extract solution - model not solved successfully")
            return {'assignments': {}, 'statistics': {}}

        assignments = {}

        # Extract all assignments
        for (worker_id, job_id, position), var in self.x.items():
            if self.solver.Value(var) == 1:
                assignments[worker_id, job_id, position] = {
                    'worker_id': worker_id,
                    'job_id': job_id,
                    'position': position
                }

        # Extract statistics
        min_rest = self.solver.Value(self.min_rest_time) if self.min_rest_time is not None else 0

        # Count scheduled workers
        scheduled_workers = set()
        for (worker_id, job_id), var in self.worker_assigned_to_job.items():
            if self.solver.Value(var) == 1:
                scheduled_workers.add(worker_id)

        statistics = {
            'minimum_rest_time_minutes': min_rest,
            'workers_scheduled': len(scheduled_workers),
            'workers_available': len(self.available_workers),
            'total_assignments': len(assignments),
            'objective_value': self.solver.ObjectiveValue(),
            'solve_time_seconds': self.solver.WallTime()
        }

        logger.info(f"Extracted {len(assignments)} assignments for {len(scheduled_workers)} workers")

        return {
            'assignments': assignments,
            'statistics': statistics
        }
