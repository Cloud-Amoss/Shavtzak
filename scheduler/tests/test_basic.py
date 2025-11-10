"""
Basic tests for the scheduling system.

Tests fundamental functionality:
- Data model creation
- Time utilities
- File I/O
- Simple scheduling scenarios
"""

import unittest
import tempfile
import json
from pathlib import Path

from scheduler.models import Worker, Job, Config, Assignment, DailyRecord, CumulativeStats
from scheduler.utils import (
    time_to_minutes,
    minutes_to_time,
    calculate_duration_hours,
    calculate_rest_time,
    jobs_overlap,
    validate_time_format,
    validate_date_format
)
from scheduler.file_io import (
    load_master_workers,
    save_master_workers,
    load_daily_jobs,
    load_config,
    save_config
)
from scheduler import SchedulingSystem


class TestTimeUtils(unittest.TestCase):
    """Test time utility functions."""

    def test_time_to_minutes(self):
        """Test conversion from HH:MM to minutes."""
        self.assertEqual(time_to_minutes("00:00"), 0)
        self.assertEqual(time_to_minutes("08:00"), 480)
        self.assertEqual(time_to_minutes("12:30"), 750)
        self.assertEqual(time_to_minutes("23:59"), 1439)

    def test_minutes_to_time(self):
        """Test conversion from minutes to HH:MM."""
        self.assertEqual(minutes_to_time(0), "00:00")
        self.assertEqual(minutes_to_time(480), "08:00")
        self.assertEqual(minutes_to_time(750), "12:30")
        self.assertEqual(minutes_to_time(1439), "23:59")

    def test_calculate_duration_hours(self):
        """Test duration calculation."""
        self.assertEqual(calculate_duration_hours("08:00", "12:00"), 4.0)
        self.assertEqual(calculate_duration_hours("09:00", "17:00"), 8.0)
        self.assertEqual(calculate_duration_hours("10:30", "11:15"), 0.75)

    def test_calculate_rest_time(self):
        """Test rest time calculation."""
        self.assertEqual(calculate_rest_time("12:00", "13:00"), 60)
        self.assertEqual(calculate_rest_time("08:00", "08:30"), 30)
        self.assertEqual(calculate_rest_time("10:00", "09:00"), -60)  # Overlap

    def test_jobs_overlap(self):
        """Test overlap detection."""
        # Non-overlapping
        self.assertFalse(jobs_overlap("08:00", "12:00", "13:00", "17:00"))

        # Overlapping
        self.assertTrue(jobs_overlap("08:00", "12:00", "10:00", "14:00"))
        self.assertTrue(jobs_overlap("08:00", "17:00", "09:00", "10:00"))

        # Adjacent (not overlapping)
        self.assertFalse(jobs_overlap("08:00", "12:00", "12:00", "16:00"))

    def test_validate_time_format(self):
        """Test time format validation."""
        self.assertTrue(validate_time_format("08:00"))
        self.assertTrue(validate_time_format("23:59"))
        self.assertFalse(validate_time_format("24:00"))
        self.assertFalse(validate_time_format("8:00"))
        self.assertFalse(validate_time_format("08:60"))

    def test_validate_date_format(self):
        """Test date format validation."""
        self.assertTrue(validate_date_format("2025-11-10"))
        self.assertTrue(validate_date_format("2025-01-01"))
        self.assertFalse(validate_date_format("2025-13-01"))
        self.assertFalse(validate_date_format("25-11-10"))
        self.assertFalse(validate_date_format("2025/11/10"))


class TestDataModels(unittest.TestCase):
    """Test data model classes."""

    def test_worker_creation(self):
        """Test Worker model creation."""
        worker = Worker(
            id=1,
            name="Test Worker",
            rank=3,
            positions=["operator", "supervisor"]
        )

        self.assertEqual(worker.id, 1)
        self.assertEqual(worker.name, "Test Worker")
        self.assertEqual(worker.rank, 3)
        self.assertEqual(worker.positions, ["operator", "supervisor"])
        self.assertTrue(worker.has_position("operator"))
        self.assertFalse(worker.has_position("manager"))

    def test_worker_availability(self):
        """Test worker availability checking."""
        worker = Worker(
            id=1,
            name="Test Worker",
            rank=3,
            positions=["operator"],
            days_off=["2025-11-15", "2025-11-16"]
        )

        self.assertTrue(worker.is_available("2025-11-10"))
        self.assertFalse(worker.is_available("2025-11-15"))
        self.assertFalse(worker.is_available("2025-11-16"))

    def test_worker_serialization(self):
        """Test Worker to/from dict conversion."""
        worker = Worker(
            id=1,
            name="Test Worker",
            rank=3,
            positions=["operator"]
        )

        worker_dict = worker.to_dict()
        worker2 = Worker.from_dict(worker_dict)

        self.assertEqual(worker.id, worker2.id)
        self.assertEqual(worker.name, worker2.name)
        self.assertEqual(worker.positions, worker2.positions)

    def test_job_creation(self):
        """Test Job model creation."""
        job = Job(
            id="J1",
            name="Test Job",
            start_time="08:00",
            end_time="12:00",
            required_positions={"operator": 2, "supervisor": 1},
            priority=1
        )

        self.assertEqual(job.id, "J1")
        self.assertEqual(job.duration_hours(), 4.0)
        self.assertEqual(job.required_positions["operator"], 2)

    def test_config_creation(self):
        """Test Config model creation."""
        config = Config(
            max_jobs_per_person_per_day=2,
            min_rest_between_jobs_minutes=30,
            position_hierarchy={
                "supervisor": ["supervisor", "operator"]
            }
        )

        self.assertEqual(config.max_jobs_per_person_per_day, 2)
        self.assertEqual(config.min_rest_between_jobs_minutes, 30)


class TestFileIO(unittest.TestCase):
    """Test file I/O functions."""

    def test_save_and_load_workers(self):
        """Test saving and loading worker data."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"]),
            Worker(id=2, name="Worker 2", rank=2, positions=["supervisor"])
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "workers.json"

            # Save
            save_master_workers(str(filepath), workers, "2025-11-10")

            # Load
            loaded_workers, last_updated = load_master_workers(str(filepath))

            self.assertEqual(len(loaded_workers), 2)
            self.assertEqual(loaded_workers[0].name, "Worker 1")
            self.assertEqual(loaded_workers[1].name, "Worker 2")
            self.assertEqual(last_updated, "2025-11-10")

    def test_save_and_load_jobs(self):
        """Test saving and loading job data."""
        jobs = [
            Job(id="J1", name="Job 1", start_time="08:00", end_time="12:00",
                required_positions={"operator": 2}, priority=1),
            Job(id="J2", name="Job 2", start_time="13:00", end_time="17:00",
                required_positions={"supervisor": 1}, priority=2)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "jobs.json"

            # Create jobs file
            data = {
                "date": "2025-11-10",
                "jobs": [job.to_dict() for job in jobs]
            }

            with open(filepath, 'w') as f:
                json.dump(data, f)

            # Load
            from scheduler.file_io import load_daily_jobs
            loaded_jobs, date = load_daily_jobs(str(filepath))

            self.assertEqual(len(loaded_jobs), 2)
            self.assertEqual(loaded_jobs[0].name, "Job 1")
            self.assertEqual(date, "2025-11-10")

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        config = Config(
            max_jobs_per_person_per_day=2,
            position_hierarchy={"manager": ["manager", "supervisor"]}
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "config.json"

            # Save
            save_config(str(filepath), config)

            # Load
            loaded_config = load_config(str(filepath))

            self.assertEqual(loaded_config.max_jobs_per_person_per_day, 2)
            self.assertEqual(loaded_config.position_hierarchy["manager"], ["manager", "supervisor"])


class TestBasicScheduling(unittest.TestCase):
    """Test basic scheduling scenarios."""

    def test_simple_schedule(self):
        """Test 1: Basic scheduling with 5 workers and 3 non-overlapping jobs."""
        # Create workers
        workers = [
            Worker(id=i, name=f"Worker {i}", rank=1, positions=["operator"])
            for i in range(1, 6)
        ]

        # Create non-overlapping jobs
        jobs = [
            Job(id="J1", name="Morning", start_time="08:00", end_time="10:00",
                required_positions={"operator": 2}, priority=1),
            Job(id="J2", name="Midday", start_time="11:00", end_time="13:00",
                required_positions={"operator": 2}, priority=1),
            Job(id="J3", name="Afternoon", start_time="14:00", end_time="16:00",
                required_positions={"operator": 1}, priority=1)
        ]

        config = Config(
            max_jobs_per_person_per_day=3,
            allow_partial_staffing=False
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Save files
            save_master_workers(str(tmppath / "workers.json"), workers)
            save_config(str(tmppath / "config.json"), config)

            jobs_data = {"date": "2025-11-10", "jobs": [j.to_dict() for j in jobs]}
            with open(tmppath / "jobs.json", 'w') as f:
                json.dump(jobs_data, f)

            # Run scheduler
            system = SchedulingSystem()
            system.load_master_list(str(tmppath / "workers.json"))
            system.load_config(str(tmppath / "config.json"))
            system.load_daily_jobs("2025-11-10", str(tmppath / "jobs.json"))

            schedule, infeasible, stats = system.solve_schedule("2025-11-10")

            # Verify results
            self.assertEqual(stats['optimization_status'], 'OPTIMAL')
            self.assertEqual(stats['jobs_fully_staffed'], 3)
            self.assertEqual(stats['jobs_unstaffed'], 0)
            self.assertEqual(len(infeasible), 0)

    def test_worker_day_off(self):
        """Test 4: Worker should not be scheduled on their day off."""
        workers = [
            Worker(id=1, name="Worker 1", rank=1, positions=["operator"],
                  days_off=["2025-11-10"]),
            Worker(id=2, name="Worker 2", rank=1, positions=["operator"])
        ]

        jobs = [
            Job(id="J1", name="Job", start_time="08:00", end_time="12:00",
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

            # Worker 1 should not be scheduled (on day off)
            scheduled_workers = [
                w for w in schedule['worker_schedules']
                if w['status'] == 'SCHEDULED'
            ]

            scheduled_ids = [w['person_id'] for w in scheduled_workers]
            self.assertNotIn(1, scheduled_ids)
            self.assertIn(2, scheduled_ids)


if __name__ == '__main__':
    unittest.main()
