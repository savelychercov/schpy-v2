# SchPy - Schedule Maker

A PyQt5-based desktop application for creating and managing college schedules. SchPy generates optimal schedules using advanced algorithms and provides a comprehensive GUI for schedule visualization and editing.

## Features

- **Automatic Schedule Generation**: Generate optimal college schedules using advanced algorithms
- **Interactive GUI**: User-friendly interface built with PyQt5
- **Data Management**: Edit groups, disciplines, teachers, and classrooms
- **Excel Export**: Export schedules to Excel format
- **Error Reporting**: View and fix scheduling conflicts
- **Logging System**: Comprehensive logging for debugging and monitoring
- **Build System**: Create standalone executable files

## Requirements

- **Python 3.12** (required - no other versions supported)
- Windows OS (build system is Windows-specific)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd schpy
```

### 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Copy the example environment file and configure as needed:

```bash
copy .env.example .env
```

Edit `.env` to adjust logging levels and debug settings:
- `SCHPY_LOG_LEVEL`: Main logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `SCHPY_DEBUG`: Enable debug mode (true/false)
- `SCHPY_PERFORMANCE_LOGS`: Enable performance logging (true/false)

## Usage

### Running the Application

```bash
python run.py
```

The application will start with the main window where you can:
- Generate new schedules
- View and edit existing schedules
- Export schedules to Excel
- Manage input data (groups, disciplines, teachers, classrooms)
- View scheduling errors and conflicts

### Building Executable

To create a standalone `.exe` file:

```bash
cd build
python build.py
```

The executable will be created in the `dist` folder with the following features:
- Single file executable
- Custom icon and version information
- Automatic cleanup of temporary files
- Version number based on application usage counter

## Development

### Code Quality with Ruff

This project uses Ruff for linting and code formatting. Configuration is in `ruff.toml`:

```bash
# Check code
ruff check .

# Format code
ruff format .

# Fix auto-fixable issues
ruff check --fix .
```

**Ruff Configuration Highlights:**
- Target Python version: 3.12
- Line length: 88 characters
- All linting rules enabled (with selective ignores)
- Auto-fixing enabled for all fixable issues
- Specific per-file ignores for `__init__.py`

### Project Structure

```
schpy/
├── build/                  # Build scripts and output
│   └── build.py           # PyInstaller build script
├── config/                # Configuration modules
│   ├── constants.py       # Application constants
│   ├── logger.py          # Logging configuration
│   └── messages.py        # Message definitions
├── css/                   # Stylesheets for GUI
├── src/                   # Source code
│   ├── db.py             # Database operations
│   ├── schedule_maker.py # Schedule generation logic
│   ├── schemas.py        # Data schemas
│   ├── best_of.py        # Schedule optimization
│   └── window.py         # Main GUI window
├── test/                  # Test files
├── logs/                  # Log files directory
├── requirements.txt       # Python dependencies
├── ruff.toml             # Ruff configuration
├── run.py                # Application entry point
└── .env.example          # Environment variables template
```

### Key Dependencies

- **PyQt5**: GUI framework
- **SQLAlchemy**: Database ORM
- **pandas**: Data manipulation
- **matplotlib**: Plotting and visualization
- **openpyxl**: Excel file handling
- **pydantic**: Data validation
- **PyInstaller**: Executable creation

## Logging

The application uses a comprehensive logging system with separate loggers for different components:
- Main application logger
- Database operations logger
- Schedule generation logger
- GUI window logger
- Performance monitoring logger

Log files are stored in the `logs/` directory and can be configured via environment variables.

## Build Process Details

The build system (`build/build.py`) creates a Windows executable with:
- Version information based on usage counter
- Custom company and product details
- Icon integration
- All dependencies bundled
- Automatic cleanup of build artifacts

**Build Configuration:**
- Product Name: ScheduleMaker
- Company: savelychercov
- Output: Single `.exe` file in `dist/` folder
- Icon: `icon.ico`

## Contributing

1. Ensure you're using Python 3.12
2. Follow the existing code style (enforced by Ruff)
3. Run `ruff check --fix .` before committing
4. Test your changes thoroughly
5. Update documentation as needed

## Troubleshooting

### Common Issues

1. **Python Version**: Ensure you're using exactly Python 3.12
2. **Virtual Environment**: Always use a virtual environment to avoid conflicts
3. **Build Errors**: Make sure all dependencies are installed before building
4. **GUI Issues**: Check that PyQt5 is properly installed and compatible

### Getting Help

- Check the log files in the `logs/` directory for detailed error information
- Ensure all environment variables are properly set in `.env`
- Verify that all required files are present in their respective directories
