#!/usr/bin/env python3
"""
Validate workflow JSON files against the schema
"""
import json
import os
import sys
from pathlib import Path
import jsonschema
from jsonschema import Draft7Validator

def load_schema():
    """Load the workflow schema"""
    schema_path = Path("schema/workflow.schema.json")
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, 'r') as f:
        return json.load(f)

def validate_workflow(workflow_path, schema):
    """Validate a single workflow file against the schema"""
    try:
        with open(workflow_path, 'r') as f:
            workflow_data = json.load(f)

        # Create validator
        validator = Draft7Validator(schema)

        # Validate
        errors = list(validator.iter_errors(workflow_data))

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'workflow_data': workflow_data
        }

    except json.JSONDecodeError as e:
        return {
            'valid': False,
            'errors': [f"JSON decode error: {e}"],
            'workflow_data': None
        }
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Error reading file: {e}"],
            'workflow_data': None
        }

def main():
    """Main validation function"""
    print("🔍 Validating workflow files against schema...")
    print("=" * 60)

    # Load schema
    try:
        schema = load_schema()
        print(f"✅ Schema loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load schema: {e}")
        return 1

    # Find all workflow files
    flows_dir = Path("flows")
    if not flows_dir.exists():
        print(f"❌ Flows directory not found: {flows_dir}")
        return 1

    workflow_files = list(flows_dir.glob("*.json"))
    if not workflow_files:
        print("❌ No JSON workflow files found in flows directory")
        return 1

    print(f"📁 Found {len(workflow_files)} workflow files to validate")
    print()

    # Validate each file
    results = {}
    valid_count = 0
    invalid_count = 0

    for workflow_file in sorted(workflow_files):
        print(f"🔍 Validating: {workflow_file.name}")

        result = validate_workflow(workflow_file, schema)
        results[workflow_file.name] = result

        if result['valid']:
            print(f"  ✅ Valid")
            valid_count += 1
        else:
            print(f"  ❌ Invalid - {len(result['errors'])} error(s)")
            invalid_count += 1

            # Show first few errors
            for i, error in enumerate(result['errors'][:3]):
                if isinstance(error, str):
                    print(f"     • {error}")
                else:
                    path = " → ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
                    print(f"     • {path}: {error.message}")

            if len(result['errors']) > 3:
                print(f"     • ... and {len(result['errors']) - 3} more errors")

        print()

    # Summary
    print("=" * 60)
    print("📊 VALIDATION SUMMARY")
    print(f"✅ Valid workflows: {valid_count}")
    print(f"❌ Invalid workflows: {invalid_count}")
    print(f"📁 Total workflows: {len(workflow_files)}")

    if invalid_count == 0:
        print("\n🎉 All workflows are valid!")
        return 0
    else:
        print(f"\n⚠️  {invalid_count} workflow(s) need attention")

        # Detailed error report for invalid files
        print("\n🔍 DETAILED ERROR REPORT")
        print("=" * 60)

        for filename, result in results.items():
            if not result['valid']:
                print(f"\n📄 {filename}")
                print("-" * 40)

                for i, error in enumerate(result['errors']):
                    if isinstance(error, str):
                        print(f"{i+1}. {error}")
                    else:
                        path = " → ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
                        print(f"{i+1}. Path: {path}")
                        print(f"   Error: {error.message}")
                        if hasattr(error, 'schema_path') and error.schema_path:
                            schema_path = " → ".join(str(p) for p in error.schema_path)
                            print(f"   Schema: {schema_path}")
                        print()

        return 1

if __name__ == "__main__":
    sys.exit(main())