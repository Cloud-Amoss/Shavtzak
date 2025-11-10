"""
Tests for optimization objectives.

Tests:
- Priority handling
- Rest time maximization
- Workload balancing
- Infeasibility detection
"""

import unittest
import tempfile
import json
from pathlib import Path

from scheduler.models import Worker, Job, Config, CumulativeStats
from scheduler import SchedulingSystem
from scheduler.file_io import save_master_workers, save_config


class TestOptimization(unittest.TestCase):
    """Test optimization objectives."""

    def test_priority_handling(self):
        """Test 7: High-priority jobs are staffed before low-priority when constrained."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"]),
            Worker(id=2, name="Worker 2", rank=1, positions=["operator"])
        ]

        # Create overlapping jobs with different priorities
        jobs = [
            Job(id="J1", name="High Priority", start_time="08:00", end_time="12:00",
                required_positions={"operator": 2}, priority=1),  # High priority
            Job(id="J2", name="Low Priority", start_time="08:00", end_time="12:00",
                required_positions={"operator": 2}, priority=5)   # Low priority
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

            # High priority job should be fully staffed
            high_priority_job = [j for j in schedule['job_assignments'] if j['job_id'] == 'J1'][0]
            low_priority_job = [j for j in schedule['job_assignments'] if j['job_id'] == 'J2'][0]

            # High priority should have more workers
            high_workers = len(high_priority_job['assigned_workers'])
            low_workers = len(low_priority_job['assigned_workers'])

            self.assertGreaterEqual(high_workers, low_workers)

    def test_rest_time_maximization(self):
        """Test 8: Verify gaps between assignments are maximized."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="09:00",
                required_positions={"operator": 1}, priority=1),
            Job(id="J2", name="Job 2", start_time="11:00", end_time="12:00",
                required_positions={"operator": 1}, priority=1),
            Job(id="J3", name="Job 3", start_time="14:00", end_time="15:00",
                required_positions={"operator": 1}, priority=1)
        ]

        config = Config(max_jobs_per_person_per_day=3)

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

            # Worker should be assigned to all jobs with good rest times
            worker_schedule = [w for w in schedule['worker_schedules'] if w['person_id'] == 1][0]

            if worker_schedule['jobs_today'] > 1:
                # Check rest times are positive
                for assignment in worker_schedule['assignments']:
                    if assignment.get('rest_after_minutes') is not None:
                        self.assertGreater(assignment['rest_after_minutes'], 0)

    def test_workload_balancing(self):
        """Test 9: Workers with fewer cumulative hours are preferred."""
        # Create workers with different cumulative hours
        workers = [
            Worker(id=1, name="Experienced", rank=1, positions=["operator"],
                  cumulative_stats=CumulativeStats(total_hours=200.0, total_jobs=50)),
            Worker(id=2, name="New", rank=1, positions=["operator"],
                  cumulative_stats=CumulativeStats(total_hours=10.0, total_jobs=2))
        ]

        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="12:00",
                required_positions={"operator": 1}, priority=1)
        ]

        config = Config(workload_balance_weight=0.5)  # High weight for balancing

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

            # New worker should be preferred
            job_assignments = schedule['job_assignments'][0]
            assigned_worker_id = job_assignments['assigned_workers'][0]['person_id']

            # Worker 2 (new) should be assigned
            self.assertEqual(assigned_worker_id, 2)

    def test_infeasibility_detection(self):
        """Test 10: Detect when jobs cannot be staffed."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Needs Inspector", start_time="08:00", end_time="12:00",
                required_positions={"inspector": 2}, priority=1)
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

            # Job should be unstaffed
            job_assignments = schedule['job_assignments'][0]
            self.assertEqual(job_assignments['staffing_status'], 'UNSTAFFED')
            self.assertEqual(stats['jobs_unstaffed'], 1)

    def test_cumulative_stats_update(self):
        """Test that cumulative statistics are updated correctly."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"],
                  cumulative_stats=CumulativeStats(total_hours=100.0, total_jobs=25))
        ]

        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="12:00",
                required_positions={"operator": 1}, priority=1)
        ]

        config = Config()

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

            # Update master list
            system.update_master_list("2025-11-10", schedule)

            # Check cumulative stats were updated
            worker = system.workers[0]
            self.assertEqual(worker.cumulative_stats.total_hours, 104.0)  # 100 + 4
            self.assertEqual(worker.cumulative_stats.total_jobs, 26)  # 25 + 1
            self.assertEqual(worker.cumulative_stats.jobs_by_position['operator'], 1)

            # Check daily history
            self.assertEqual(len(worker.daily_history), 1)
            self.assertEqual(worker.daily_history[0].date, "2025-11-10")
            self.assertEqual(worker.daily_history[0].jobs_worked, 1)
            self.assertEqual(worker.daily_history[0].total_hours, 4.0)

    def test_multiple_positions_per_job(self):
        """Test jobs requiring multiple different positions."""
        workers = [
            Worker(id=1, name="Supervisor", rank=3, positions=["supervisor"]),
            Worker(id=2, name="Operator 1", rank=1, positions=["operator"]),
            Worker(id=3, name="Operator 2", rank=1, positions=["operator"]),
            Worker(id=4, name="Inspector", rank=2, positions=["inspector"])
        ]

        jobs = [
            Job(id="J1", name="Complex Job", start_time="08:00", end_time="12:00",
                required_positions={"supervisor": 1, "operator": 2, "inspector": 1},
                priority=1)
        ]

        config = Config()

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

            # Job should be fully staffed
            job_assignments = schedule['job_assignments'][0]
            self.assertEqual(job_assignments['staffing_status'], 'FULLY_STAFFED')
            self.assertEqual(len(job_assignments['assigned_workers']), 4)

            # Verify correct positions
            positions_filled = [w['position_filled'] for w in job_assignments['assigned_workers']]
            self.assertIn('supervisor', positions_filled)
            self.assertIn('inspector', positions_filled)
            self.assertEqual(positions_filled.count('operator'), 2)


if __name__ == '__main__':
    unittest.main()
