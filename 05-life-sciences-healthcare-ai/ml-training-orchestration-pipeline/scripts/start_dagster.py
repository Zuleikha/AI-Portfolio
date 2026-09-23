#!/usr/bin/env python3
"""Start Dagster development server"""

import os
import subprocess
import sys


def start_dagster():
    """Start Dagster development server"""
    # Set environment variables
    os.environ["DAGSTER_HOME"] = os.getcwd()

    print("Starting Dagster development server...")
    print("This will open a web interface at http://localhost:3000")
    print("Press Ctrl+C to stop the server")

    try:
        # Start Dagster dev server
        subprocess.run([sys.executable, "-m", "dagster", "dev", "-f", "src/dagster_definitions.py"])
    except KeyboardInterrupt:
        print("\nStopping Dagster server...")
    except Exception as e:
        print(f"Error starting Dagster: {e}")


if __name__ == "__main__":
    start_dagster()
