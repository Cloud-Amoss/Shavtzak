#!/usr/bin/env python3
"""
Command-line interface for the staff scheduling system.

Provides commands for:
- Generating schedules
- Viewing worker statistics
- Generating reports
"""

import argparse
import logging
import sys
from pathlib import Path

from scheduler import SchedulingSystem
from scheduler.utils import validate_date_format


# Configure logging
def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def command_schedule(args):
    """
    Generate a schedule for a specific date.

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)

    # Validate date format
    if not validate_date_format(args.date):
        logger.error(f"Invalid date format: {args.date}. Expected YYYY-MM-DD")
        sys.exit(1)

    # Initialize system
    system = SchedulingSystem()

    try:
        # Load data
        logger.info("Loading master worker list...")
        system.load_master_list(args.master)

        logger.info("Loading configuration...")
        system.load_config(args.config)

        logger.info(f"Loading jobs for {args.date}...")
        system.load_daily_jobs(args.date, args.jobs)

        # Solve schedule
        logger.info("Solving optimization problem...")
        schedule, infeasible_jobs, statistics = system.solve_schedule(
            args.date,
            time_limit=args.time_limit
        )

        # Display results
        print("\n" + "=" * 80)
        print(f"SCHEDULE OPTIMIZATION COMPLETE - {args.date}")
        print("=" * 80)
        print(f"Status: {statistics['optimization_status']}")
        print(f"Workers Scheduled: {statistics['workers_scheduled']} / {statistics['workers_available']} available")
        print(f"Jobs Fully Staffed: {statistics['jobs_fully_staffed']} / {statistics['total_jobs']}")

        if statistics['jobs_partially_staffed'] > 0:
            print(f"⚠  Jobs Partially Staffed: {statistics['jobs_partially_staffed']}")

        if statistics['jobs_unstaffed'] > 0:
            print(f"⚠  Jobs Unstaffed: {statistics['jobs_unstaffed']}")

        print(f"Minimum Rest Time: {statistics['minimum_rest_time_minutes']} minutes")
        print(f"Solve Time: {statistics['solve_time_seconds']:.2f} seconds")

        # Export schedule
        logger.info(f"Exporting schedule to {args.output}...")
        system.export_daily_schedule(args.date, schedule, args.output)
        print(f"\n✓ Schedule saved to: {args.output}")

        # Update master list if requested
        if args.update_master:
            logger.info("Updating master worker list...")
            system.update_master_list(args.date, schedule)
            system.export_master_list(args.master)
            print(f"✓ Master list updated: {args.master}")

        # Generate text report if requested
        if args.report:
            report_path = args.report
            report = system.generate_report(args.date, schedule)

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            print(f"✓ Text report saved to: {report_path}")

        # Show warnings
        if infeasible_jobs:
            print("\n⚠  WARNINGS:")
            for job_info in infeasible_jobs:
                print(f"   - Job {job_info['job_id']} '{job_info['job_name']}': "
                      f"{job_info['shortage']} {job_info['position']} position(s) short")

        print("=" * 80 + "\n")

        # Exit with warning code if there are issues
        if statistics['jobs_unstaffed'] > 0 or statistics['optimization_status'] == 'INFEASIBLE':
            sys.exit(2)
        elif statistics['jobs_partially_staffed'] > 0:
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid data: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


def command_stats(args):
    """
    Display worker statistics.

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)

    system = SchedulingSystem()

    try:
        logger.info("Loading master worker list...")
        system.load_master_list(args.master)

        if args.all:
            # Display stats for all workers
            print("\n" + "=" * 80)
            print("WORKER STATISTICS - ALL WORKERS")
            print("=" * 80 + "\n")

            for worker in sorted(system.workers, key=lambda w: w.cumulative_stats.total_hours, reverse=True):
                stats = system.get_worker_statistics(worker.id)
                print(f"{stats['name']} (ID: {stats['id']})")
                print(f"  Positions: {', '.join(stats['positions'])}")
                print(f"  Total Hours: {stats['cumulative_stats']['total_hours']:.2f}")
                print(f"  Total Jobs: {stats['cumulative_stats']['total_jobs']}")
                print(f"  Days Worked: {stats['total_days_worked']}")

                if stats['cumulative_stats']['jobs_by_position']:
                    print(f"  Jobs by Position:")
                    for position, count in stats['cumulative_stats']['jobs_by_position'].items():
                        print(f"    - {position}: {count}")

                print()

        elif args.worker_id:
            # Display stats for specific worker
            stats = system.get_worker_statistics(args.worker_id)

            if not stats:
                logger.error(f"Worker ID {args.worker_id} not found")
                sys.exit(1)

            print("\n" + "=" * 80)
            print(f"WORKER STATISTICS - {stats['name']}")
            print("=" * 80 + "\n")

            print(f"ID: {stats['id']}")
            print(f"Name: {stats['name']}")
            print(f"Rank: {stats['rank']}")
            print(f"Positions: {', '.join(stats['positions'])}")
            print(f"Days Off: {', '.join(stats['days_off']) if stats['days_off'] else 'None'}")
            print()

            print("CUMULATIVE STATISTICS:")
            print(f"  Total Hours: {stats['cumulative_stats']['total_hours']:.2f}")
            print(f"  Total Jobs: {stats['cumulative_stats']['total_jobs']}")
            print(f"  Total Days Worked: {stats['total_days_worked']}")

            if stats['cumulative_stats']['jobs_by_position']:
                print(f"  Jobs by Position:")
                for position, count in stats['cumulative_stats']['jobs_by_position'].items():
                    print(f"    - {position}: {count}")

            print()

            if stats['recent_history']:
                print("RECENT WORK HISTORY (last 10 days):")
                for record in stats['recent_history']:
                    print(f"  {record['date']}: {record['jobs_worked']} jobs, {record['total_hours']:.2f} hours")
                    for assignment in record['assignments']:
                        print(f"    - {assignment['start_time']}-{assignment['end_time']}: "
                              f"{assignment['job_name']} ({assignment['position']})")

            print("=" * 80 + "\n")

        else:
            logger.error("Must specify either --worker-id or --all")
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


def command_report(args):
    """
    Generate a text report from an existing schedule.

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger(__name__)

    from scheduler.file_io import load_daily_schedule

    try:
        logger.info(f"Loading schedule from {args.schedule}...")
        schedule_data = load_daily_schedule(args.schedule)

        date = schedule_data.get('date', 'Unknown')

        # Create a minimal system just for report generation
        system = SchedulingSystem()
        report = system.generate_report(date, schedule_data)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"✓ Report saved to: {args.output}")
        else:
            print(report)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Staff Scheduling Optimization System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate schedule for a specific date
  %(prog)s schedule --date 2025-11-10 --jobs jobs_2025-11-10.json --output schedule_2025-11-10.json

  # Generate schedule and update master list
  %(prog)s schedule --date 2025-11-10 --jobs jobs_2025-11-10.json --output schedule_2025-11-10.json --update-master

  # View statistics for a specific worker
  %(prog)s stats --worker-id 1

  # View statistics for all workers
  %(prog)s stats --all

  # Generate text report from schedule
  %(prog)s report --schedule schedule_2025-11-10.json --output report_2025-11-10.txt
        """
    )

    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Schedule command
    schedule_parser = subparsers.add_parser('schedule', help='Generate a schedule')
    schedule_parser.add_argument('--date', required=True,
                                help='Date to schedule (YYYY-MM-DD)')
    schedule_parser.add_argument('--jobs', required=True,
                                help='Path to jobs JSON file')
    schedule_parser.add_argument('--output', required=True,
                                help='Path to output schedule JSON file')
    schedule_parser.add_argument('--master', default='master_workers.json',
                                help='Path to master workers file (default: master_workers.json)')
    schedule_parser.add_argument('--config', default='config.json',
                                help='Path to config file (default: config.json)')
    schedule_parser.add_argument('--update-master', action='store_true',
                                help='Update master worker list with schedule results')
    schedule_parser.add_argument('--report',
                                help='Generate text report to this file')
    schedule_parser.add_argument('--time-limit', type=int, default=30,
                                help='Optimization time limit in seconds (default: 30)')
    schedule_parser.set_defaults(func=command_schedule)

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='View worker statistics')
    stats_parser.add_argument('--worker-id', type=int,
                             help='Worker ID to view stats for')
    stats_parser.add_argument('--all', action='store_true',
                             help='View stats for all workers')
    stats_parser.add_argument('--master', default='master_workers.json',
                             help='Path to master workers file (default: master_workers.json)')
    stats_parser.set_defaults(func=command_stats)

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate text report from schedule')
    report_parser.add_argument('--schedule', required=True,
                              help='Path to schedule JSON file')
    report_parser.add_argument('--output',
                              help='Path to output text file (prints to stdout if not specified)')
    report_parser.set_defaults(func=command_report)

    # Parse arguments
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
