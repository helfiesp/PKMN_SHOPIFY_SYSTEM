#!/usr/bin/env python3
"""
Verify that the reorganized directory structure works correctly.
Tests all critical imports and file references.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("Directory Structure Verification")
print("=" * 80)

tests_passed = 0
tests_failed = 0

def test(description, test_func):
    """Run a test and track results."""
    global tests_passed, tests_failed
    try:
        test_func()
        print(f"[PASS] {description}")
        tests_passed += 1
        return True
    except Exception as e:
        print(f"[FAIL] {description}")
        print(f"       Error: {e}")
        tests_failed += 1
        return False

# Test 1: Database shim import
def test_database_import():
    from database import SessionLocal
    assert SessionLocal is not None

test("database.py can be imported", test_database_import)

# Test 2: FastAPI app structure
def test_app_imports():
    from app.main import app
    from app.database import get_db
    from app.models import Product, Variant
    from app.schemas import PricePlanResponse

test("FastAPI app imports work", test_app_imports)

# Test 3: Services layer
def test_services():
    from app.services.shopify_service import shopify_service
    from app.services.snkrdunk_service import snkrdunk_service
    from app.services.price_plan_service import price_plan_service

test("Services layer imports work", test_services)

# Test 4: Routers
def test_routers():
    from app.routers import shopify, snkrdunk, competitors
    assert shopify.router is not None
    assert snkrdunk.router is not None
    assert competitors.router is not None

test("Router imports work", test_routers)

# Test 5: Competition scripts exist
def test_competition_scripts():
    comp_dir = project_root / "competition"
    scripts = ["boosterpakker.py", "hatamontcg.py", "pokemadness.py"]
    for script in scripts:
        assert (comp_dir / script).exists(), f"Missing {script}"

test("Competition scripts exist in competition/", test_competition_scripts)

# Test 6: Legacy scripts exist
def test_legacy_scripts():
    legacy_dir = project_root / "legacy"
    scripts = ["main.py", "snkrdunk.py", "shopify_price_updater_confirmed.py"]
    for script in scripts:
        assert (legacy_dir / script).exists(), f"Missing {script}"

test("Legacy scripts exist in legacy/", test_legacy_scripts)

# Test 7: Documentation exists
def test_docs():
    docs_dir = project_root / "docs"
    docs = ["README_API.md", "QUICKSTART.md", "DEPLOYMENT_GUIDE.md"]
    for doc in docs:
        assert (docs_dir / doc).exists(), f"Missing {doc}"

test("Documentation exists in docs/", test_docs)

# Test 8: Deployment files exist
def test_deployment():
    deploy_dir = project_root / "deployment"
    files = ["deploy.sh", "Dockerfile", "docker-compose.example.yml"]
    for file in files:
        assert (deploy_dir / file).exists(), f"Missing {file}"

test("Deployment files exist in deployment/", test_deployment)

# Test 9: Essential root files
def test_root_files():
    files = ["run.py", "requirements.txt", "alembic.ini", ".env.example"]
    for file in files:
        assert (project_root / file).exists(), f"Missing {file}"

test("Essential root files exist", test_root_files)

# Test 10: Alembic config
def test_alembic():
    alembic_dir = project_root / "alembic"
    assert alembic_dir.exists(), "Alembic directory missing"
    assert (alembic_dir / "env.py").exists(), "alembic/env.py missing"

test("Alembic structure intact", test_alembic)

# Summary
print("=" * 80)
print(f"Results: {tests_passed} passed, {tests_failed} failed")
print("=" * 80)

if tests_failed > 0:
    print("\n[!] Some tests failed. Please review the errors above.")
    sys.exit(1)
else:
    print("\n[OK] All tests passed! Directory structure is correct.")
    sys.exit(0)
