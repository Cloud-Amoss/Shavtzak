# Staff Scheduling Optimization System

A comprehensive Python staff scheduling system using Google OR-Tools that optimizes daily work assignments while maintaining historical tracking and ensuring fairness across time.

## Features

- **Intelligent Optimization**: Uses Google OR-Tools CP-SAT solver to find optimal schedules
- **Multiple Objectives**:
  - Maximizes minimum rest time between consecutive job assignments
  - Balances cumulative workload fairly across workers
  - Prioritizes high-priority jobs when resources are constrained
- **Flexible Position Hierarchy**: Workers with higher-level positions can fill lower-level roles
- **Historical Tracking**: Maintains cumulative statistics and daily work history for all workers
- **Constraint Management**:
  - Prevents overlapping job assignments
  - Respects worker days off
  - Enforces maximum jobs per worker per day
  - Supports minimum rest time requirements
- **Partial Staffing**: Configurable option to allow partial job staffing when full staffing is impossible
- **Comprehensive Reporting**: JSON output and human-readable text reports

## Requirements

- Python 3.10 or higher
- Google OR-Tools 9.8.0 or higher

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Shavtzak
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Verify installation:
```bash
python -m scheduler.main --help
```

## Quick Start

### 1. Prepare Input Files

Create three input files:

**config.json** - System configuration:
```json
{
  "max_jobs_per_person_per_day": 1,
  "min_rest_between_jobs_minutes": 0,
  "position_hierarchy": {
    "manager": ["manager", "supervisor", "operator"],
    "supervisor": ["supervisor", "operator"]
  },
  "workload_balance_weight": 0.3,
  "allow_partial_staffing": true
}
```

**master_workers.json** - Worker database (see sample file)

**jobs_2025-11-10.json** - Daily jobs (see sample file)

### 2. Generate a Schedule

```bash
python -m scheduler.main schedule \
  --date 2025-11-10 \
  --jobs jobs_2025-11-10.json \
  --output schedule_2025-11-10.json
```

### 3. View Results

The schedule will be saved to `schedule_2025-11-10.json`. You can also generate a text report:

```bash
python -m scheduler.main report \
  --schedule schedule_2025-11-10.json \
  --output report_2025-11-10.txt
```

## Usage

### Command-Line Interface

The system provides three main commands:

#### 1. Schedule Generation

Generate an optimized schedule for a specific date:

```bash
python -m scheduler.main schedule \
  --date 2025-11-10 \
  --jobs jobs_2025-11-10.json \
  --output schedule_2025-11-10.json \
  [--master master_workers.json] \
  [--config config.json] \
  [--update-master] \
  [--report report.txt] \
  [--time-limit 30]
```

**Options:**
- `--date`: Date to schedule (YYYY-MM-DD format) [required]
- `--jobs`: Path to daily jobs JSON file [required]
- `--output`: Path to output schedule JSON file [required]
- `--master`: Path to master workers file (default: master_workers.json)
- `--config`: Path to config file (default: config.json)
- `--update-master`: Update master worker list with schedule results
- `--report`: Generate text report to this file
- `--time-limit`: Optimization time limit in seconds (default: 30)

**Example:**
```bash
python -m scheduler.main schedule \
  --date 2025-11-10 \
  --jobs jobs_2025-11-10.json \
  --output schedule_2025-11-10.json \
  --update-master \
  --report report_2025-11-10.txt
```

#### 2. Worker Statistics

View statistics for individual workers or all workers:

```bash
# View specific worker
python -m scheduler.main stats --worker-id 1

# View all workers
python -m scheduler.main stats --all
```

**Options:**
- `--worker-id`: Specific worker ID to view
- `--all`: View statistics for all workers
- `--master`: Path to master workers file (default: master_workers.json)

**Example Output:**
```
================================================================================
WORKER STATISTICS - Alice Smith
================================================================================

ID: 1
Name: Alice Smith
Rank: 4
Positions: manager, supervisor
Days Off: 2025-11-15, 2025-11-16

CUMULATIVE STATISTICS:
  Total Hours: 156.50
  Total Jobs: 42
  Total Days Worked: 1
  Jobs by Position:
    - manager: 8
    - supervisor: 34
```

#### 3. Report Generation

Generate a human-readable text report from an existing schedule:

```bash
python -m scheduler.main report \
  --schedule schedule_2025-11-10.json \
  [--output report.txt]
```

**Options:**
- `--schedule`: Path to schedule JSON file [required]
- `--output`: Path to output text file (prints to stdout if not specified)

### Python API

You can also use the scheduling system programmatically:

```python
from scheduler import SchedulingSystem

# Initialize system
scheduler = SchedulingSystem()

# Load data
scheduler.load_master_list('master_workers.json')
scheduler.load_config('config.json')
scheduler.load_daily_jobs('2025-11-10', 'jobs_2025-11-10.json')

# Solve optimization
schedule, infeasible_jobs, stats = scheduler.solve_schedule('2025-11-10')

# Check results
if stats['optimization_status'] == 'OPTIMAL':
    print(f"✓ Schedule generated successfully")
    print(f"  Minimum rest time: {stats['minimum_rest_time_minutes']} minutes")
    print(f"  Workers scheduled: {stats['workers_scheduled']}")

# Export results
scheduler.export_daily_schedule('2025-11-10', schedule, 'schedule_2025-11-10.json')

# Update master list
scheduler.update_master_list('2025-11-10', schedule)
scheduler.export_master_list('master_workers.json')

# Generate report
report = scheduler.generate_report('2025-11-10', schedule)
print(report)
```

## Configuration

### config.json

The configuration file controls system behavior:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_jobs_per_person_per_day` | int | 1 | Maximum jobs one worker can have per day |
| `min_rest_between_jobs_minutes` | int | 0 | Minimum rest time between consecutive jobs |
| `target_hours_per_person_per_day` | float | 8.0 | Target daily work hours (informational) |
| `position_hierarchy` | dict | {} | Maps positions to list of positions they can fill |
| `workload_balance_weight` | float | 0.3 | Weight for workload balancing (0.0-1.0) |
| `allow_partial_staffing` | bool | true | Allow jobs to be partially staffed |

### Position Hierarchy

The position hierarchy defines which positions can fill which job requirements. This is a **skill-based** system, not rank-based.

**Example:**
```json
{
  "manager": ["manager", "supervisor", "operator", "assistant"],
  "supervisor": ["supervisor", "operator", "assistant"],
  "operator": ["operator", "assistant"],
  "inspector": ["inspector"],
  "assistant": ["assistant"]
}
```

In this example:
- A worker with "manager" position can fill requirements for manager, supervisor, operator, or assistant
- A worker with "operator" position can fill requirements for operator or assistant
- A worker with "inspector" position can only fill inspector requirements

## Input File Formats

### master_workers.json

Stores persistent worker data with cumulative statistics and work history.

```json
{
  "last_updated": "2025-11-09",
  "workers": [
    {
      "id": 1,
      "name": "Alice Smith",
      "rank": 4,
      "positions": ["manager", "supervisor"],
      "days_off": ["2025-11-15", "2025-11-16"],
      "cumulative_stats": {
        "total_hours": 156.5,
        "total_jobs": 42,
        "jobs_by_position": {
          "manager": 8,
          "supervisor": 34
        }
      },
      "daily_history": [
        {
          "date": "2025-11-01",
          "jobs_worked": 2,
          "total_hours": 8.0,
          "assignments": [
            {
              "job_id": "J1",
              "job_name": "Morning Shift",
              "start_time": "08:00",
              "end_time": "12:00",
              "position": "supervisor"
            }
          ]
        }
      ]
    }
  ]
}
```

**Notes:**
- `cumulative_stats` NEVER resets - accumulates indefinitely across all time
- `daily_history` maintains a complete record of all past assignments
- `days_off` uses YYYY-MM-DD format

### jobs_YYYY-MM-DD.json

Defines jobs for a specific date.

```json
{
  "date": "2025-11-10",
  "jobs": [
    {
      "id": "J1",
      "name": "Morning Production Line A",
      "start_time": "08:00",
      "end_time": "12:00",
      "required_positions": {
        "supervisor": 1,
        "operator": 3
      },
      "priority": 1
    }
  ]
}
```

**Notes:**
- `start_time` and `end_time` use HH:MM format (24-hour)
- `priority`: 1 = highest priority, higher numbers = lower priority
- `required_positions`: Maps position name to count needed

## Output File Format

### schedule_YYYY-MM-DD.json

Contains the complete optimized schedule.

```json
{
  "date": "2025-11-10",
  "generated_at": "2025-11-10T06:30:00Z",
  "optimization_status": "OPTIMAL",
  "statistics": {
    "minimum_rest_time_minutes": 45,
    "average_rest_time_minutes": 78,
    "workers_scheduled": 35,
    "workers_available": 47,
    "workers_on_day_off": 3,
    "total_jobs": 16,
    "jobs_fully_staffed": 14,
    "jobs_partially_staffed": 2,
    "jobs_unstaffed": 0
  },
  "job_assignments": [...],
  "worker_schedules": [...],
  "workers_on_day_off": [...],
  "infeasible_jobs": [...],
  "warnings": [...]
}
```

See sample output files for complete structure.

## Optimization Model

The system uses Google OR-Tools CP-SAT solver with the following objectives:

### Primary Objective: Maximize Minimum Rest Time
Maximizes the minimum rest time between consecutive job assignments across all workers.

### Secondary Objective: Balance Workload
Minimizes the variance in cumulative work hours across workers, preferring to assign work to those with fewer cumulative hours.

### Tertiary Objective: Prioritize High-Priority Jobs
Ensures high-priority jobs are fully staffed before lower-priority jobs when resources are constrained.

### Hard Constraints
1. **Staffing Requirements**: All jobs must be staffed (fully or partially based on config)
2. **No Overlapping Assignments**: Workers cannot be assigned to overlapping jobs
3. **Max Jobs Per Day**: Workers cannot exceed max_jobs_per_person_per_day
4. **Days Off**: Workers are never scheduled on their days off
5. **Minimum Rest Time**: Rest time between consecutive jobs must meet minimum requirement
6. **Position Qualification**: Workers can only fill positions they're qualified for

## Testing

Run the test suite:

```bash
# Run all tests
python -m unittest discover scheduler/tests

# Run specific test file
python -m unittest scheduler.tests.test_basic

# Run with verbose output
python -m unittest discover scheduler/tests -v
```

The test suite includes 15+ test cases covering:
- Basic scheduling scenarios
- Constraint enforcement
- Position hierarchy
- Partial staffing
- Priority handling
- Rest time maximization
- Workload balancing
- Infeasibility detection
- Cumulative statistics updates

## Performance

The system is designed to handle:
- **50 workers** with multiple skills each
- **16 jobs** per day with varying requirements
- **Solve time**: < 30 seconds for typical scenarios
- **Optimization quality**: Finds optimal or near-optimal solutions

For larger problem instances, increase the `--time-limit` parameter.

## Troubleshooting

### Common Issues

**Issue: "INFEASIBLE" optimization status**
- **Cause**: Jobs cannot be staffed with available workers
- **Solutions**:
  - Enable partial staffing: `"allow_partial_staffing": true`
  - Add more workers or reduce job requirements
  - Check position hierarchy configuration
  - Review worker days off

**Issue: Partial staffing warnings**
- **Cause**: Not enough qualified workers available
- **Solutions**:
  - Increase worker count for that position
  - Adjust position hierarchy to allow more flexibility
  - Reduce required_positions counts
  - Check for workers on day off

**Issue: Poor workload balancing**
- **Cause**: Low workload_balance_weight or insufficient workers
- **Solutions**:
  - Increase `workload_balance_weight` (e.g., 0.5-0.8)
  - Add more workers to provide flexibility
  - Allow workers to have multiple jobs per day

**Issue: Solve time too long**
- **Cause**: Large problem size or complex constraints
- **Solutions**:
  - Reduce time limit: `--time-limit 10`
  - Simplify position hierarchy
  - Reduce number of overlapping jobs
  - Allow partial staffing

## Exit Codes

The CLI returns different exit codes based on results:

- `0`: Success - all jobs fully staffed
- `1`: Warning - some jobs partially staffed
- `2`: Error - jobs unstaffed or infeasible solution

## Contributing

Contributions are welcome! Please ensure:
- All tests pass: `python -m unittest discover scheduler/tests`
- Code follows PEP 8 style guidelines
- New features include tests and documentation

## License

[Specify your license here]

## Support

For issues, questions, or contributions, please [open an issue](https://github.com/yourusername/scheduler/issues).

## Version History

**1.0.0** (2025-11-10)
- Initial release
- Core scheduling functionality
- Position hierarchy support
- Cumulative statistics tracking
- CLI interface
- Comprehensive test suite
