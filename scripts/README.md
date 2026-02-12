# Utility & Test Scripts

This folder contains utility scripts and test files for development and debugging.

## Utility Scripts

- **add_sprell_supplier.py** - Add Sprell supplier to database
- **check_prices.py** - Quick price verification tool
- **clear_cache.py** - Clear SNKRDUNK cache
- **debug_prices.py** - Debug price calculation issues
- **driver_setup.py** - Setup Selenium WebDriver
- **database.py** - Database utilities

## Test Scripts

- **test_api_endpoints.py** - API endpoint integration tests
- **test_complete_flow.py** - End-to-end workflow tests
- **test_complete_simulation.py** - Full system simulation
- **test_live_api_comparison.py** - Compare API responses
- **test_fresh_scan.py** - Test fresh competitor scans
- **test_*_simple.py** - Simple component tests
- **test_*_standalone.py** - Standalone scraper tests

## Usage

Run scripts directly from the project root:

```bash
# From project root
python scripts/test_api_endpoints.py
python scripts/check_prices.py
```

**Note:** Most test scripts require the API server to be running.
