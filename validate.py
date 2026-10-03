#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.validation.validator import DataValidator


def main():
    print("Validating scheduling data...\n")
    
    validator = DataValidator("data")
    is_valid, errors, warnings = validator.validate_all()
    
    if errors:
        print("❌ VALIDATION FAILED\n")
        print("Errors:")
        for error in errors:
            print(f"  • {error}")
        print()
    
    if warnings:
        print("⚠ Warnings:")
        for warning in warnings:
            print(f"  • {warning}")
        print()
    
    if is_valid:
        print("✓ Time slots valid")
        print("✓ Courses valid")
        print("✓ Student groups valid")
        print("✓ Course enrollments valid")
        print("✓ Lecturers valid")
        print("✓ Teaching assignments valid")
        print("✓ Rooms valid")
        print("✓ Lecturer availability valid")
        print("\n✅ Data validation passed.")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
