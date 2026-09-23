#!/usr/bin/env python
"""Generate synthetic candidates and jobs into ``data/``.

An operator action, never a service boot hook. The output is test data for
exercising the ranking pipeline locally; it is git-ignored, because it is
regenerable and carries no information the repository needs to keep.

The generated records are *plausible*, not distributionally grounded — see
docs/ROADMAP.md. They are suitable for testing mechanics and unsuitable for
evaluating ranking quality.

Usage::

    python scripts/generate_data.py
    python scripts/generate_data.py --resumes 200 --jobs 50 --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data_generation.resume_generator import ResumeGenerator  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "data"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--resumes", type=int, default=50, help="Number of candidate records (default: 50)"
    )
    parser.add_argument("--jobs", type=int, default=20, help="Number of job postings (default: 20)")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for reproducible output. Omit for fresh randomness each run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Directory to write into (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate the datasets and report what was written."""
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    generator = ResumeGenerator(seed=args.seed)

    resumes = generator.generate_resumes(args.resumes)
    jobs = generator.generate_jobs(args.jobs)

    resume_path = generator.save(resumes, args.output / "resumes.json", kind="resumes")
    job_path = generator.save(jobs, args.output / "jobs.json", kind="jobs")

    print(f"Wrote {len(resumes)} resumes -> {resume_path}")
    print(f"Wrote {len(jobs)} jobs     -> {job_path}")
    print()
    print("Summary:")
    print(json.dumps(generator.summarise(resumes), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
