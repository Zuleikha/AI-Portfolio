"""Tests for the synthetic data generator.

The generator's contract is *reproducibility*: a seed must pin the output
exactly, and seeding it must not disturb the caller's global random state.
Both are asserted here, because a generator that quietly drifts makes every
downstream ranking test flaky.
"""

from __future__ import annotations

import json
import random
from datetime import datetime

import pytest

from src.data_generation.resume_generator import (
    CITIES,
    SKILLS_BY_ROLE,
    ResumeGenerator,
)

FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0)


@pytest.fixture
def generator() -> ResumeGenerator:
    """A generator pinned to a seed and a fixed clock."""
    return ResumeGenerator(seed=42, now=FIXED_NOW)


# --- reproducibility -------------------------------------------------------


def test_same_seed_produces_identical_resumes():
    first = ResumeGenerator(seed=7, now=FIXED_NOW).generate_resumes(5)
    second = ResumeGenerator(seed=7, now=FIXED_NOW).generate_resumes(5)
    assert first == second


def test_different_seeds_produce_different_resumes():
    first = ResumeGenerator(seed=1, now=FIXED_NOW).generate_resumes(5)
    second = ResumeGenerator(seed=2, now=FIXED_NOW).generate_resumes(5)
    assert first != second


def test_seeding_does_not_disturb_global_random_state():
    """The generator owns a private RNG; it must not reseed the global one."""
    random.seed(123)
    expected = [random.random() for _ in range(3)]

    random.seed(123)
    ResumeGenerator(seed=999).generate_resumes(10)
    actual = [random.random() for _ in range(3)]

    assert actual == expected


def test_generated_ids_are_unique(generator: ResumeGenerator):
    ids = [resume["id"] for resume in generator.generate_resumes(50)]
    assert len(set(ids)) == 50


# --- candidate records -----------------------------------------------------


def test_resume_has_flat_contact_fields(generator: ResumeGenerator):
    """Contact details sit at the top level, not nested under personal_info."""
    resume = generator.generate_resume()
    for field in ("name", "email", "phone", "location"):
        assert field in resume, f"{field} should be a top-level key"
        assert resume[field]


def test_resume_has_all_expected_sections(generator: ResumeGenerator):
    resume = generator.generate_resume()
    assert set(resume) == {
        "id",
        "name",
        "email",
        "phone",
        "location",
        "role_category",
        "experience_years",
        "skills",
        "education",
        "work_history",
        "expected_salary",
        "availability",
        "remote_preference",
    }


def test_skills_come_from_the_candidates_own_role_pool(generator: ResumeGenerator):
    for resume in generator.generate_resumes(20):
        pools = SKILLS_BY_ROLE[resume["role_category"]]
        valid = set(pools["primary"] + pools["secondary"] + pools["tools"])
        assert set(resume["skills"]) <= valid


def test_skills_are_not_duplicated(generator: ResumeGenerator):
    for resume in generator.generate_resumes(20):
        assert len(resume["skills"]) == len(set(resume["skills"]))


def test_location_is_drawn_from_the_known_city_list(generator: ResumeGenerator):
    for resume in generator.generate_resumes(20):
        assert resume["location"] in CITIES


@pytest.mark.parametrize("years", [0])
def test_no_work_history_below_one_year(generator: ResumeGenerator, years: int):
    assert generator.generate_work_history("Data Scientist", years) == []


def test_work_history_is_capped_and_uses_iso_dates(generator: ResumeGenerator):
    history = generator.generate_work_history("Data Scientist", 15)
    assert 0 < len(history) <= 4
    for job in history:
        datetime.strptime(job["start_date"], "%Y-%m-%d")
        datetime.strptime(job["end_date"], "%Y-%m-%d")
        assert job["start_date"] < job["end_date"]


def test_more_experience_yields_at_least_as_many_skills(generator: ResumeGenerator):
    junior = generator.generate_skills("Data Scientist", 1)
    senior = generator.generate_skills("Data Scientist", 12)
    assert len(senior) > len(junior)


def test_unknown_role_raises(generator: ResumeGenerator):
    with pytest.raises(KeyError):
        generator.generate_skills("Chief Vibes Officer", 5)


# --- job records -----------------------------------------------------------


def test_job_experience_band_is_ordered(generator: ResumeGenerator):
    for job in generator.generate_jobs(25):
        assert job["min_experience"] <= job["max_experience"]


def test_job_uses_flat_experience_keys(generator: ResumeGenerator):
    """The feature pipeline reads min_experience/max_experience directly."""
    job = generator.generate_job()
    assert "min_experience" in job
    assert "max_experience" in job
    assert "experience_requirements" not in job


def test_job_always_states_required_skills(generator: ResumeGenerator):
    for job in generator.generate_jobs(25):
        assert len(job["required_skills"]) >= 3
        assert len(set(job["required_skills"])) == len(job["required_skills"])


def test_job_salary_band_is_ordered(generator: ResumeGenerator):
    for job in generator.generate_jobs(25):
        assert job["salary_min"] < job["salary_max"]


# --- dataset sizing --------------------------------------------------------


@pytest.mark.parametrize("count", [0, 1, 13])
def test_dataset_size_is_respected(generator: ResumeGenerator, count: int):
    assert len(generator.generate_resumes(count)) == count
    assert len(generator.generate_jobs(count)) == count


def test_negative_count_is_rejected(generator: ResumeGenerator):
    with pytest.raises(ValueError, match="non-negative"):
        generator.generate_resumes(-1)
    with pytest.raises(ValueError, match="non-negative"):
        generator.generate_jobs(-1)


# --- text rendering --------------------------------------------------------


def test_resume_text_contains_the_ranking_relevant_content(generator: ResumeGenerator):
    resume = generator.generate_resume()
    text = ResumeGenerator.render_resume_text(resume)

    assert resume["name"] in text
    assert "EXPERIENCE" in text
    assert "SKILLS" in text
    for skill in resume["skills"]:
        assert skill in text


def test_job_text_contains_title_and_required_skills(generator: ResumeGenerator):
    job = generator.generate_job()
    text = ResumeGenerator.render_job_text(job)

    assert job["title"] in text
    for skill in job["required_skills"]:
        assert skill in text


def test_resume_text_survives_an_empty_work_history(generator: ResumeGenerator):
    resume = generator.generate_resume()
    resume["work_history"] = []
    assert "EXPERIENCE" in ResumeGenerator.render_resume_text(resume)


# --- persistence -----------------------------------------------------------


def test_save_writes_envelope_and_creates_parent_directories(generator: ResumeGenerator, tmp_path):
    resumes = generator.generate_resumes(3)
    destination = tmp_path / "nested" / "deeper" / "resumes.json"

    written = generator.save(resumes, destination, kind="resumes")

    assert written == destination
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["metadata"]["count"] == 3
    assert payload["metadata"]["generator"] == "ResumeGenerator"
    assert payload["resumes"] == resumes


def test_save_is_utf8_clean(generator: ResumeGenerator, tmp_path):
    """Names such as O'Connor must round-trip byte-for-byte."""
    record = generator.generate_resume()
    record["name"] = "Siân O'Connor — Ingeniería"
    destination = generator.save([record], tmp_path / "r.json", kind="resumes")

    reloaded = json.loads(destination.read_text(encoding="utf-8"))
    assert reloaded["resumes"][0]["name"] == "Siân O'Connor — Ingeniería"


# --- summary statistics ----------------------------------------------------


def test_summarise_counts_roles_and_experience_bands():
    resumes = [
        {"role_category": "Data Scientist", "experience_years": 0},
        {"role_category": "Data Scientist", "experience_years": 2},
        {"role_category": "Data Scientist", "experience_years": 5},
        {"role_category": "DevOps Engineer", "experience_years": 9},
        {"role_category": "DevOps Engineer", "experience_years": 11},
    ]

    summary = ResumeGenerator.summarise(resumes)

    assert summary == {
        "total": 5,
        "by_role": {"Data Scientist": 3, "DevOps Engineer": 2},
        "by_experience_band": {"0-2": 2, "3-5": 1, "6-10": 1, "10+": 1},
    }


def test_summarise_handles_an_empty_dataset():
    summary = ResumeGenerator.summarise([])
    assert summary["total"] == 0
    assert summary["by_role"] == {}
    assert sum(summary["by_experience_band"].values()) == 0
