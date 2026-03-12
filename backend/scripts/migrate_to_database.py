#!/usr/bin/env python3
"""
Data Migration Script - Migrate from JSON to SQLite Database

This script migrates existing JSON-based session and memory data
to the new SQLite database storage.

Usage:
    python -m backend.scripts.migrate_to_database [--backup] [--dry-run]

Options:
    --backup: Create backup of JSON files before migration (default: True)
    --dry-run: Show what would be done without actually migrating
    --force: Skip confirmation prompt

Example:
    python -m backend.scripts.migrate_to_database --backup --force
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.memory.migration import migrate_json_to_database
from app.core.database import get_database_info


def print_separator(title: str):
    """Print a section separator."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


async def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate JSON data to SQLite database"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup of JSON files before migration (default: True)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup creation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually migrating",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Get settings
    settings = get_settings()

    # Show current status
    print_separator("Current Database Status")

    info = get_database_info(settings)

    print(f"Database: {info['path']}")
    print(f"Exists: {info['exists']}")
    print(f"Size: {info['size_bytes']} bytes")
    print(f"\nTable Counts:")
    for table, count in info['tables'].items():
        print(f"  - {table}: {count}")

    # Check what to migrate
    print_separator("Migration Summary")

    sessions_dir = Path(settings.sessions_dir)
    metadata_file = Path(settings.data_dir) / "memory_metadata.json"

    session_count = len(list(sessions_dir.glob("*.json"))) if sessions_dir.exists() else 0
    has_metadata = metadata_file.exists()

    print(f"Session files to migrate: {session_count}")
    print(f"Memory metadata file: {'Found' if has_metadata else 'Not found'}")

    if session_count == 0 and not has_metadata:
        print("\n⚠️  No data to migrate found.")
        return

    # Dry run mode
    if args.dry_run:
        print("\n[DRY RUN] Migration would:")
        if session_count > 0:
            print(f"  - Migrate {session_count} session files")
        if has_metadata:
            print(f"  - Migrate memory metadata")
        print(f"  - Create backup: {not args.no_backup}")
        print("\nNo changes made. Run without --dry-run to perform migration.")
        return

    # Confirmation
    if not args.force:
        print_separator("Confirmation")
        response = input("Proceed with migration? (yes/no): ").strip().lower()
        if response not in ["yes", "y"]:
            print("\n❌ Migration cancelled.")
            return

    # Perform migration
    print_separator("Starting Migration")

    try:
        backup = not args.no_backup

        result = await migrate_json_to_database(backup=backup)

        print("\n✅ Migration completed successfully!")
        print(f"\nStatistics:")
        print(f"  - Sessions imported: {result['sessions_imported']}")
        print(f"  - Messages imported: {result['messages_imported']}")
        print(f"  - Memories imported: {result['memories_imported']}")
        print(f"  - Backup created: {result['backup_created']}")

        if result['errors']:
            print(f"\n⚠️  Errors encountered: {len(result['errors'])}")
            for error in result['errors']:
                print(f"  - {error}")

        # Show updated database info
        print_separator("Updated Database Status")

        info = get_database_info(settings)

        print(f"Database: {info['path']}")
        print(f"Size: {info['size_bytes']} bytes")
        print(f"\nTable Counts:")
        for table, count in info['tables'].items():
            print(f"  - {table}: {count}")

        print("\n🎉 Migration complete! You can now use the new database storage.")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
