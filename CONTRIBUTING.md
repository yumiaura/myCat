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
   python3 -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   pip install PySide6  # for development
   ```

4. **Run the application:**
   ```bash
   # From source
   python3 mycat/main.py

   # Or as installed package
   mycat
   ```

## Code Style

- Follow PEP 8 for Python code style
- Use type hints where possible (already implemented in most places)
- Add docstrings to all public functions and classes
- Keep functions focused and not too long

## Testing

Currently there are no automated tests, but contributions in this area are very welcome!

Consider adding tests for:
- Sprite loading and parsing
- Configuration save/load
- Window behavior (position, transparency)
- Command-line argument parsing

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
