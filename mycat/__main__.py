# Allow running: python -m mycat
def main():
    from .main import main as entry
    entry()

if __name__ == "__main__":
    main()
