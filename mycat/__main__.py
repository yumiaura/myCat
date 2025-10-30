# Allow running: python -m mycat
def main():
    try:
        from .main import main as entry
    except ImportError:
        # Fallback for direct execution
        import sys
        from pathlib import Path
        # Add parent directory to path
        parent_dir = Path(__file__).resolve().parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        from main import main as entry
    entry()

if __name__ == "__main__":
    main()
