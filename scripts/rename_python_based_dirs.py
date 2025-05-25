import os
import argparse
import shutil
import subprocess


def rename_python_version_dirs(root_dir: str, old_suffix: str, new_suffix: str, dry_run: bool = True):
    """
    Recursively renames directories ending with old_suffix to new_suffix.

    Args:
        root_dir: The root directory to start the search from.
        old_suffix: The suffix to search for (e.g., "-py3.11").
        new_suffix: The suffix to replace with (e.g., "-py3.12").
        dry_run: If True, only print what would be renamed without actually renaming.
    """
    renamed_count = 0
    skipped_count = 0

    print(f"Starting scan in: {os.path.abspath(root_dir)}")
    if dry_run:
        print("DRY RUN active: No directories will actually be renamed.")
    print(f"Looking for directories ending with '{old_suffix}' to rename to '{new_suffix}'...")
    print("-" * 30)

    # We use topdown=False to process deeper directories first.
    # This can be helpful if renaming a parent might affect paths to children,
    # though for simple suffix renaming, it's less critical.
    for dirpath, dirnames, _filenames in os.walk(root_dir, topdown=False):
        for dirname in list(dirnames): # Iterate over a copy as dirnames can be modified by os.rename
            if dirname.endswith(old_suffix):
                old_name_full_path = os.path.join(dirpath, dirname)
                new_dirname = dirname[:-len(old_suffix)] + new_suffix
                new_name_full_path = os.path.join(dirpath, new_dirname)

                print(f"Found: '{old_name_full_path}'")
                if os.path.exists(new_name_full_path):
                    print(f"  SKIPPED: Target '{new_name_full_path}' already exists.")
                    skipped_count += 1
                    # shutil.rmtree(new_name_full_path)
                    continue

                if not dry_run:
                    try:
                        subprocess.run(["git", "mv", old_name_full_path, new_name_full_path], check=True)
                        print(f"  RENAMED to: '{new_name_full_path}'")
                        renamed_count += 1
                        # If os.rename is successful, we need to update dirnames
                        # so that subsequent iterations of os.walk (if any for this level)
                        # don't try to process the old directory name.
                        # This is more relevant if topdown=True or if there are multiple
                        # renames in the same parent directory.
                        try:
                            dirnames.remove(dirname)
                            dirnames.append(new_dirname)
                        except ValueError:
                            # Should not happen if dirname was in list(dirnames)
                            pass
                    except OSError as e:
                        print(f"  ERROR renaming '{old_name_full_path}': {e}")
                        skipped_count += 1
                else:
                    print(f"  WOULD RENAME to: '{new_name_full_path}'")
                    renamed_count +=1 # Count as if renamed for dry run stats

    print("-" * 30)
    if dry_run:
        print(f"Dry run complete. Would have attempted to rename {renamed_count} director(y/ies).")
    else:
        print(f"Renaming complete. {renamed_count} director(y/ies) renamed.")
    if skipped_count > 0:
        print(f"{skipped_count} director(y/ies) were skipped (e.g., target existed or error).")

def main():
    parser = argparse.ArgumentParser(
        description="Recursively rename directories based on a suffix.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "root_directory",
        help="The root directory to start searching for directories to rename."
    )
    parser.add_argument(
        "--old-suffix",
        default="-python-3.11",
        help="The suffix of directories to find (default: -py3.11)."
    )
    parser.add_argument(
        "--new-suffix",
        default="-python-3.12",
        help="The new suffix to apply to found directories (default: -py3.12)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the renaming. Without this flag, it's a dry run."
    )

    args = parser.parse_args()

    if not os.path.isdir(args.root_directory):
        print(f"Error: The specified root directory '{args.root_directory}' does not exist or is not a directory.")
    else:
        rename_python_version_dirs(
            args.root_directory,
            args.old_suffix,
            args.new_suffix,
            dry_run=not args.execute
        )


if __name__ == "__main__":
    main()
