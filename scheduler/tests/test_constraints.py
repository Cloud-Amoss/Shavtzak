"""
Tests for scheduling constraints.

Tests:
- Overlapping job constraints
- Max jobs per worker
- Position hierarchy
- Partial staffing
"""

import unittest
import tempfile
import json
from pathlib import Path

from scheduler.models import Worker, Job, Config
from scheduler import SchedulingSystem
from scheduler.file_io import save_master_workers, save_config


class TestConstraints(unittest.TestCase):
    """Test scheduling constraints."""

    def test_overlapping_jobs(self):
        """Test 2: Workers cannot be assigned to overlapping jobs."""
        workers = [
            Worker(id=i, name=f"Worker {i}", rank=1, positions=["operator"])
            for i in range(1, 11)
        ]

        # Create overlapping jobs
        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="12:00",
                required_positions={"operator": 2}, priority=1),
            Job(id="J2", name="Job 2", start_time="10:00", end_time="14:00",
                required_positions={"operator": 2}, priority=1),
            Job(id="J3", name="Job 3", start_time="11:00", end_time="15:00",
                required_positions={"operator": 2}, priority=1)
        ]

        config = Config(max_jobs_per_person_per_day=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Verify no worker is assigned to overlapping jobs
            for worker_schedule in schedule['worker_schedules']:
                if worker_schedule['status'] == 'SCHEDULED':
                    assignments = worker_schedule['assignments']

                    # Check all pairs of assignments
                    for i, a1 in enumerate(assignments):
                        for a2 in assignments[i+1:]:
                            from scheduler.utils import jobs_overlap
                            overlap = jobs_overlap(
                                a1['start_time'], a1['end_time'],
                                a2['start_time'], a2['end_time']
                            )
                            self.assertFalse(overlap,
                                f"Worker {worker_schedule['name']} assigned to overlapping jobs")

    def test_max_jobs_constraint(self):
        """Test 5: Worker should not exceed max_jobs_per_day."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"])
        ]

        # Create many non-overlapping jobs
        jobs = [
            Job(id=f"J{i}", name=f"Job {i}",
                start_time=f"{8+i*2:02d}:00", end_time=f"{8+i*2+1:02d}:00",
                required_positions={"operator": 1}, priority=1)
            for i in range(5)  # 5 jobs
        ]

        config = Config(max_jobs_per_person_per_day=2)  # Max 2 jobs

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Worker should have at most 2 jobs
            for worker_schedule in schedule['worker_schedules']:
                if worker_schedule['person_id'] == 1:
                    self.assertLessEqual(worker_schedule['jobs_today'], 2)

    def test_position_hierarchy(self):
        """Test 3: Manager can fill supervisor role via hierarchy."""
        workers = [
            Worker(id=1, name="Manager", rank=4, positions=["manager"]),
            Worker(id=2, name="Operator", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Needs Supervisor", start_time="08:00", end_time="12:00",
                required_positions={"supervisor": 1}, priority=1)
        ]

        config = Config(
            position_hierarchy={
                "manager": ["manager", "supervisor", "operator"],
                "supervisor": ["supervisor", "operator"],
                "operator": ["operator"]
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Manager should be able to fill supervisor position
            self.assertEqual(stats['jobs_fully_staffed'], 1)

            # Verify manager was assigned
            job_assignments = schedule['job_assignments'][0]
            self.assertEqual(len(job_assignments['assigned_workers']), 1)
            self.assertEqual(job_assignments['assigned_workers'][0]['person_id'], 1)
            self.assertEqual(job_assignments['assigned_workers'][0]['position_filled'], 'supervisor')

    def test_partial_staffing_allowed(self):
        """Test 6: Job can be partially staffed when allowed."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"]),
            Worker(id=2, name="Worker 2", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Needs 3 Operators", start_time="08:00", end_time="12:00",
                required_positions={"operator": 3}, priority=1)
        ]

        config = Config(allow_partial_staffing=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Job should be partially staffed
            job_assignments = schedule['job_assignments'][0]
            self.assertEqual(job_assignments['staffing_status'], 'PARTIALLY_STAFFED')
            self.assertEqual(len(job_assignments['assigned_workers']), 2)

    def test_partial_staffing_disallowed(self):
        """Test that partial staffing can be disallowed."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"]),
            Worker(id=2, name="Worker 2", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Needs 3 Operators", start_time="08:00", end_time="12:00",
                required_positions={"operator": 3}, priority=1)
        ]

        config = Config(allow_partial_staffing=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Job should be unstaffed (can't meet exact requirement)
            job_assignments = schedule['job_assignments'][0]
            self.assertEqual(job_assignments['staffing_status'], 'UNSTAFFED')

    def test_rest_time_constraint(self):
        """Test minimum rest time between consecutive jobs."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="10:00",
                required_positions={"operator": 1}, priority=1),
            Job(id="J2", name="Job 2", start_time="10:15", end_time="12:00",
                required_positions={"operator": 1}, priority=1)
        ]

        config = Config(
            max_jobs_per_person_per_day=2,
            min_rest_between_jobs_minutes=30  # Requires 30 min rest
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Worker should not be assigned to both jobs (only 15 min rest)
            scheduled_workers = [
                w for w in schedule['worker_schedules']
                if w['status'] == 'SCHEDULED'
            ]

            if scheduled_workers:
                worker = scheduled_workers[0]
                # Should have at most 1 job since rest time is insufficient
                self.assertLessEqual(worker['jobs_today'], 1)


if __name__ == '__main__':
    unittest.main()
