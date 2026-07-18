# Contributing to Desktop Cat

Thank you for considering contributing to this cute desktop pet project! 🐱

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yumiaura/mycat.git
   cd mycat
   ```

2. **Create a virtual environment:**
   ```bash
   # On Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # On Windows
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   pip install PySide6  # for development
   pip install openai
   ```

4. **Set up your OpenAI API token:**
   ```bash
   # Windows (PowerShell)
   setx OPENAI_API_KEY "your_api_key_here"

   # Linux/macOS
   export OPENAI_API_KEY="your_api_key_here"
   ```

5. **Run the application:**
   ```bash
   # From source
   python3 mycat/main.py

   # Or as installed package
   mycat
   ```

## Code Style

- Follow PEP 8 for Python code style
- Lint with [ruff](https://docs.astral.sh/ruff/): `ruff check .` (CI fails on findings)
- Use type hints where possible (already implemented in most places)
- Add docstrings to all public functions and classes
- Keep functions focused and not too long

## Testing

The test suite lives in `tests/` and runs on pytest. Qt runs headless through
the offscreen platform (set up in `tests/conftest.py`), so no display is
needed:

```bash
pip install ruff pytest
python -m pytest -q
```

CI runs `ruff check .` and the test suite on Python 3.10 and 3.12 for every
pull request — please run both locally before opening one, and add tests for
new features and bug fixes.

## Documentation

When adding new features:
- Update the README.md with usage examples
- Add docstrings to new functions
- Update type hints if adding new parameters

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and test them
4. Update documentation if needed
5. Commit with clear messages: `git commit -m "Add amazing feature"`
6. Push to your fork: `git push origin feature/amazing-feature`
7. Open a Pull Request

## Feature Ideas

Some ideas for contributions (check issues for more):
- [ ] Unit tests and testing framework
- [ ] System tray icon integration
- [ ] Multiple cat instances support
- [ ] More animation types (sleeping, walking)
- [ ] Settings/preferences GUI
- [ ] macOS improvements
- [ ] Additional sprite packs
- [ ] Keyboard shortcuts
- [ ] Configuration file format improvements

## Reporting Bugs

- Use the GitHub Issues page
- Include your operating system and desktop environment
- Provide steps to reproduce the issue
- Include any error messages from the terminal

## License

This project is open source. Feel free to contribute and improve it!
