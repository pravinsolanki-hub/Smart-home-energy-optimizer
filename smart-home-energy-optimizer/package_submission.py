import os
import zipfile

def create_clean_zip():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(base_dir)
    zip_output_path = os.path.join(parent_dir, "smart-home-energy-optimizer.zip")

    # Excluded directories and file patterns
    exclude_dirs = {".venv", "__pycache__", ".git", ".pytest_cache", ".idea", ".vscode"}
    exclude_files = {".DS_Store", "Thumbs.db"}
    exclude_extensions = {".pyc", ".pyo", ".pyd"}

    print(f"Creating clean cross-platform ZIP at: {zip_output_path}")

    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(base_dir):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file in exclude_files:
                    continue
                if any(file.endswith(ext) for ext in exclude_extensions):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                
                # CRITICAL: Always use POSIX forward slashes in ZIP archives
                posix_arcname = rel_path.replace("\\", "/")

                zipf.write(full_path, arcname=posix_arcname)
                print(f"  + {posix_arcname}")

    print("\nVerifying archive contents:")
    with zipfile.ZipFile(zip_output_path, "r") as zipf:
        infolist = zipf.infolist()
        print(f"Total files in archive: {len(infolist)}")
        for info in infolist[:10]:
            print(f"    {info.filename} ({info.file_size} bytes)")
        if len(infolist) > 10:
            print(f"    ... and {len(infolist) - 10} more files.")

    print(f"\nSUCCESS: Clean ZIP created ({os.path.getsize(zip_output_path)} bytes) with POSIX forward slashes.")

if __name__ == "__main__":
    create_clean_zip()
