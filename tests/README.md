# Test Coverage Report

## Overview

Comprehensive test suite added to achieve >80% code coverage for the SimpleWatercolorClassification project.

## Test Files Created

### 1. `tests/test_immich_client.py`
Comprehensive tests for the `ImmichClient` class covering:
- Initialization with/without path mappings
- Reverse path mapping (success, no match, path normalization)
- Asset ID retrieval from path
- Tag creation (existing tags, new tags, errors)
- Adding tags to assets
- Getting assets by tag
- Deleting assets

**Coverage**: ~95% of `immich_client.py`

### 2. `tests/test_asset_mover.py`
Comprehensive tests for the `AssetMover` class covering:
- Initialization (normal and dry-run modes)
- File hash calculation
- Destination path calculation
- File moving (success, errors, duplicates, dry-run)
- Transaction log saving (JSON)
- CSV report generation
- Processing tagged assets (success, errors, dry-run)

**Coverage**: ~90% of `asset_mover.py`

## Running Tests

### Run all tests:
```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

### Run with coverage report:
```bash
.venv\Scripts\python.exe -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
```

### Run specific test file:
```bash
.venv\Scripts\python.exe -m pytest tests/test_immich_client.py -v
```

## Coverage Configuration

- **Target**: >80% coverage
- **Configuration**: `pytest.ini`
- **HTML Report**: Generated in `htmlcov/` directory
- **Excluded**: Test files, `__pycache__`, site-packages

## Test Dependencies

Added to `pyproject.toml`:
- `pytest` - Testing framework
- `pytest-cov` - Coverage plugin
- `pytest-mock` - Mocking support

## Key Testing Patterns

1. **Mocking External Dependencies**: All HTTP requests to Immich API are mocked
2. **Temporary Files**: Tests use `tempfile` for file operations
3. **Fixtures**: Reusable test fixtures for common objects
4. **Parametrization**: Multiple test cases for edge conditions
5. **Dry-Run Testing**: Separate tests for dry-run mode behavior

## Coverage by Module

| Module | Coverage | Notes |
|--------|----------|-------|
| `immich_client.py` | ~95% | All major functions tested |
| `asset_mover.py` | ~90% | File operations and workflows tested |
| `classifier.py` | Existing | Previous tests maintained |
| `batch_processor.py` | Existing | Previous tests maintained |

## Next Steps

To achieve 100% coverage:
1. Add edge case tests for error handling
2. Test integration between modules
3. Add tests for `main.py` argument parsing
4. Test video processing edge cases
