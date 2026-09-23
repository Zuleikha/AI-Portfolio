"""Synthetic resume and job-posting generator.

Every record this produces is fabricated. No real candidate data enters the
repository, which is what makes it safe to commit fixtures and to publish
fairness experiments run against them.

The generator is seedable. It draws from a private ``random.Random`` instance
rather than the global ``random`` module, so seeding it is genuinely
reproducible and does not perturb any other caller's random state.
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Names are drawn from a deliberately broad pool. The point is not realism for
# its own sake: fairness checks need group variation in the test data, and a
# monocultural name pool would make every parity metric look perfect.
FIRST_NAMES = [
    "Alex",
    "Maria",
    "James",
    "Sarah",
    "Michael",
    "Jennifer",
    "David",
    "Lisa",
    "Robert",
    "Emily",
    "William",
    "Jessica",
    "John",
    "Ashley",
    "Daniel",
    "Amanda",
    "Carlos",
    "Isabella",
    "Roberto",
    "Sofia",
    "Diego",
    "Camila",
    "Luis",
    "Valentina",
    "Wei",
    "Li",
    "Hiroshi",
    "Yuki",
    "Raj",
    "Priya",
    "Kenji",
    "Sakura",
    "Chen",
    "Ming",
    "Ahmed",
    "Fatima",
    "Hassan",
    "Aisha",
    "Omar",
    "Layla",
    "Khalid",
    "Noor",
    "Kwame",
    "Amara",
    "Kofi",
    "Nia",
    "Sekou",
    "Zara",
    "Malik",
    "Kaia",
    "Dmitri",
    "Anya",
    "Gustav",
    "Ingrid",
    "Marco",
    "Elena",
    "Pietro",
    "Sophia",
    "Arjun",
    "Maya",
    "Olumide",
    "Grace",
    "Tariq",
    "Zoe",
    "Ravi",
    "Chloe",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Davis",
    "Wilson",
    "Anderson",
    "Taylor",
    "Thomas",
    "Jackson",
    "White",
    "Thompson",
    "Robinson",
    "Lewis",
    "Walker",
    "Hall",
    "Rodriguez",
    "Martinez",
    "Garcia",
    "Lopez",
    "Gonzalez",
    "Hernandez",
    "Perez",
    "Sanchez",
    "Kim",
    "Lee",
    "Park",
    "Chen",
    "Zhang",
    "Wang",
    "Liu",
    "Yang",
    "Patel",
    "Singh",
    "Kumar",
    "Sharma",
    "Gupta",
    "Tanaka",
    "Suzuki",
    "Sato",
    "Yamamoto",
    "Hassan",
    "Ali",
    "Ahmad",
    "Mohamed",
    "Ibrahim",
    "Mahmoud",
    "Al-Rashid",
    "Okafor",
    "Adebayo",
    "Mensah",
    "Diallo",
    "Kone",
    "Traore",
    "Mueller",
    "Schmidt",
    "Johansson",
    "Nielsen",
    "Rossi",
    "Ferrari",
    "O'Connor",
    "Murphy",
]

SKILLS_BY_ROLE: dict[str, dict[str, list[str]]] = {
    "Software Engineer": {
        "primary": ["Python", "Java", "JavaScript", "C++", "Go", "Rust"],
        "secondary": ["React", "Node.js", "Angular", "Vue.js", "Spring Boot", "Django"],
        "tools": ["Git", "Docker", "Jenkins", "JIRA", "VS Code", "IntelliJ"],
    },
    "Data Scientist": {
        "primary": ["Python", "R", "SQL", "Scala", "Julia"],
        "secondary": ["Pandas", "NumPy", "Scikit-learn", "TensorFlow", "PyTorch", "Keras"],
        "tools": ["Jupyter", "Tableau", "Power BI", "Apache Spark", "Databricks", "MLflow"],
    },
    "DevOps Engineer": {
        "primary": ["Python", "Bash", "Go", "YAML", "Terraform"],
        "secondary": ["AWS", "Azure", "GCP", "Kubernetes", "Docker", "Ansible"],
        "tools": ["Jenkins", "GitLab CI", "Prometheus", "Grafana", "Helm", "Istio"],
    },
    "Frontend Developer": {
        "primary": ["JavaScript", "TypeScript", "HTML", "CSS"],
        "secondary": ["React", "Vue.js", "Angular", "Svelte", "Next.js", "Nuxt.js"],
        "tools": ["Webpack", "Vite", "Sass", "Tailwind CSS", "Figma", "Chrome DevTools"],
    },
    "Backend Developer": {
        "primary": ["Python", "Java", "Node.js", "C#", "PHP", "Go"],
        "secondary": ["Django", "Flask", "Spring Boot", "Express.js", "Laravel", "Gin"],
        "tools": ["PostgreSQL", "MongoDB", "Redis", "RabbitMQ", "Docker", "AWS"],
    },
    "Full Stack Developer": {
        "primary": ["JavaScript", "Python", "TypeScript", "Java"],
        "secondary": ["React", "Node.js", "Django", "PostgreSQL", "MongoDB", "Express.js"],
        "tools": ["Git", "Docker", "AWS", "Heroku", "Netlify", "Vercel"],
    },
}

COMPANIES = [
    "TechCorp",
    "DataSoft",
    "CloudInc",
    "DevCompany",
    "InnovateLabs",
    "NextGen Systems",
    "AgileWorks",
    "ScaleUp Tech",
    "QuantumSoft",
    "ByteForge",
    "CodeCraft",
    "DataFlow Inc",
    "CloudNine Solutions",
    "FinanceFirst",
    "Capital Solutions",
    "InvestPro",
    "BankTech Corp",
    "MedTech Solutions",
    "HealthCare Plus",
    "BioInnovate",
    "MedFlow",
    "ShopTech",
    "Commerce Cloud",
    "RetailFlow",
    "MarketPlace Inc",
    "ConsultPro",
    "Strategy Plus",
    "BusinessFlow",
    "ServiceTech",
    "StartupLab",
    "VentureFlow",
    "InnovateCorp",
    "DisruptTech",
]

DEGREE_FIELDS: dict[str, list[str]] = {
    "Software Engineer": ["Computer Science", "Software Engineering", "Information Technology"],
    "Data Scientist": ["Data Science", "Statistics", "Mathematics", "Computer Science"],
    "DevOps Engineer": ["Computer Science", "Information Systems", "Engineering"],
    "Frontend Developer": ["Computer Science", "Web Development", "Design"],
    "Backend Developer": ["Computer Science", "Software Engineering", "Information Technology"],
    "Full Stack Developer": ["Computer Science", "Software Engineering", "Web Development"],
}

EDUCATION_LEVELS = ["Bachelor's", "Master's", "PhD"]

UNIVERSITIES = [
    "State University",
    "Tech Institute",
    "City College",
    "Metro University",
    "Valley Tech",
    "Riverside University",
    "Mountain State",
    "Coastal College",
]

CITIES = [
    "San Francisco, CA",
    "New York, NY",
    "Seattle, WA",
    "Boston, MA",
    "Austin, TX",
    "Denver, CO",
    "Atlanta, GA",
    "Chicago, IL",
    "Los Angeles, CA",
    "Portland, OR",
    "Miami, FL",
    "Detroit, MI",
    "Toronto, Canada",
    "London, UK",
    "Berlin, Germany",
    "Amsterdam, Netherlands",
    "Sydney, Australia",
    "Tokyo, Japan",
    "Singapore",
    "Dublin, Ireland",
]

BENEFITS = [
    "Health Insurance",
    "401k Matching",
    "Remote Work",
    "Flexible Hours",
    "Professional Development",
    "Stock Options",
    "Paid Time Off",
    "Gym Membership",
    "Free Lunch",
    "Learning Budget",
]

BASE_SALARY: dict[str, int] = {
    "Software Engineer": 85_000,
    "Data Scientist": 95_000,
    "DevOps Engineer": 90_000,
    "Frontend Developer": 80_000,
    "Backend Developer": 85_000,
    "Full Stack Developer": 88_000,
}

SALARY_BANDS: dict[str, tuple[int, int]] = {
    "Software Engineer": (75_000, 180_000),
    "Data Scientist": (85_000, 200_000),
    "DevOps Engineer": (80_000, 190_000),
    "Frontend Developer": (70_000, 160_000),
    "Backend Developer": (75_000, 170_000),
    "Full Stack Developer": (78_000, 175_000),
}

MAX_JOBS_IN_HISTORY = 4


class ResumeGenerator:
    """Produce synthetic candidate and job records.

    Args:
        seed: Seeds a private RNG. Pass an int for reproducible output; leave
            as None for fresh randomness each run.
        now: Fixes "today" so generated dates are stable under a given seed.
            Defaults to the current time.
    """

    def __init__(self, seed: int | None = None, now: datetime | None = None) -> None:
        self._rng = random.Random(seed)
        self._now = now or datetime.now()
        self.roles: list[str] = list(SKILLS_BY_ROLE)

    # --- candidates --------------------------------------------------------

    def generate_skills(self, role: str, experience_years: int) -> list[str]:
        """Pick a skill set sized to the candidate's seniority.

        Args:
            role: One of :data:`SKILLS_BY_ROLE`.
            experience_years: Years of experience; more experience yields a
                broader skill list.

        Returns:
            Skill names, primary first.

        Raises:
            KeyError: If ``role`` is not a known role.
        """
        pools = SKILLS_BY_ROLE[role]
        if experience_years <= 2:
            counts = (self._rng.randint(1, 2), self._rng.randint(1, 2), self._rng.randint(2, 3))
        elif experience_years <= 5:
            counts = (self._rng.randint(2, 3), self._rng.randint(2, 4), self._rng.randint(3, 4))
        else:
            counts = (self._rng.randint(3, 4), self._rng.randint(3, 5), self._rng.randint(4, 6))

        skills: list[str] = []
        for key, count in zip(("primary", "secondary", "tools"), counts, strict=True):
            pool = pools[key]
            skills.extend(self._rng.sample(pool, min(count, len(pool))))
        return skills

    def generate_work_history(self, role: str, experience_years: int) -> list[dict[str, Any]]:
        """Build a back-to-back employment history covering the stated years."""
        if experience_years < 1:
            return []

        history: list[dict[str, Any]] = []
        remaining = experience_years
        cursor = self._now

        while remaining > 0 and len(history) < MAX_JOBS_IN_HISTORY:
            duration = min(self._rng.randint(1, 4), remaining)
            end_date = cursor
            start_date = cursor - timedelta(days=duration * 365)

            title = role if self._rng.random() < 0.7 else self._rng.choice(self.roles)
            served = experience_years - remaining + duration
            if served >= 5:
                title = f"{self._rng.choice(['Senior', 'Lead', 'Principal'])} {title}"
            elif served >= 2 and self._rng.random() < 0.3:
                title = f"Junior {title}"

            history.append(
                {
                    "title": title,
                    "company": self._rng.choice(COMPANIES),
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "duration_years": duration,
                }
            )
            remaining -= duration
            cursor = start_date - timedelta(days=30)

        return history

    def generate_resume(self) -> dict[str, Any]:
        """Generate one candidate record.

        Contact fields are flat (``name``, ``email``, ``phone``, ``location``)
        rather than nested, so the same key works in JSON, in a DataFrame and
        in the ranking pipeline without a reshaping step.
        """
        first = self._rng.choice(FIRST_NAMES)
        last = self._rng.choice(LAST_NAMES)
        role = self._rng.choice(self.roles)
        experience_years = self._rng.randint(0, 15)

        email = self._rng.choice(
            [
                f"{first.lower()}.{last.lower()}@example.com",
                f"{first.lower()}{last.lower()[:3]}@example.net",
                f"{first[:1].lower()}{last.lower()}@example.org",
            ]
        ).replace("'", "")

        multiplier = 1 + experience_years * 0.08
        expected_salary = int(BASE_SALARY[role] * multiplier * self._rng.uniform(0.9, 1.1))

        return {
            "id": str(uuid.UUID(int=self._rng.getrandbits(128), version=4)),
            "name": f"{first} {last}",
            "email": email,
            "phone": f"({self._rng.randint(200, 999)}) "
            f"{self._rng.randint(200, 999)}-{self._rng.randint(1000, 9999)}",
            "location": self._rng.choice(CITIES),
            "role_category": role,
            "experience_years": experience_years,
            "skills": self.generate_skills(role, experience_years),
            "education": {
                "level": self._rng.choice(EDUCATION_LEVELS),
                "field": self._rng.choice(DEGREE_FIELDS[role]),
                "institution": self._rng.choice(UNIVERSITIES),
                "graduation_year": self._now.year - experience_years - self._rng.randint(0, 4),
            },
            "work_history": self.generate_work_history(role, experience_years),
            "expected_salary": expected_salary,
            "availability": self._rng.choice(["Immediate", "2 weeks", "1 month"]),
            "remote_preference": self._rng.choice(["Remote", "Hybrid", "On-site", "No preference"]),
        }

    # --- jobs --------------------------------------------------------------

    def generate_job(self) -> dict[str, Any]:
        """Generate one job posting.

        Experience bounds are emitted as flat ``min_experience`` /
        ``max_experience`` keys — the shape the ranking and feature code reads.
        """
        role = self._rng.choice(self.roles)
        min_exp = self._rng.randint(0, 3)
        max_exp = min_exp + self._rng.randint(2, 8)

        salary_min, salary_max = SALARY_BANDS[role]
        exp_multiplier = 1 + min_exp * 0.1

        pools = SKILLS_BY_ROLE[role]
        required_pool = pools["primary"] + pools["secondary"][:3]
        preferred_pool = pools["secondary"] + pools["tools"]

        if min_exp >= 5:
            title = f"{self._rng.choice(['Senior', 'Lead', 'Principal'])} {role}"
        elif min_exp <= 1 and self._rng.random() < 0.4:
            title = f"Junior {role}"
        else:
            title = role

        return {
            "id": str(uuid.UUID(int=self._rng.getrandbits(128), version=4)),
            "title": title,
            "company": self._rng.choice(COMPANIES),
            "location": self._rng.choice(CITIES),
            "role_category": role,
            "min_experience": min_exp,
            "max_experience": max_exp,
            "required_skills": self._rng.sample(
                required_pool, min(self._rng.randint(3, 5), len(required_pool))
            ),
            "preferred_skills": self._rng.sample(
                preferred_pool, min(self._rng.randint(2, 4), len(preferred_pool))
            ),
            "salary_min": int(salary_min * exp_multiplier),
            "salary_max": int(salary_max * exp_multiplier * 0.8),
            "currency": "USD",
            "employment_type": self._rng.choice(["Full-time", "Contract", "Part-time"]),
            "remote_policy": self._rng.choice(["Remote", "Hybrid", "On-site"]),
            "benefits": self._rng.sample(BENEFITS, self._rng.randint(3, 7)),
            "posted_date": (self._now - timedelta(days=self._rng.randint(1, 30))).strftime(
                "%Y-%m-%d"
            ),
        }

    # --- datasets ----------------------------------------------------------

    def generate_resumes(self, count: int = 50) -> list[dict[str, Any]]:
        """Generate ``count`` candidate records."""
        if count < 0:
            raise ValueError(f"count must be non-negative, got {count}")
        return [self.generate_resume() for _ in range(count)]

    def generate_jobs(self, count: int = 20) -> list[dict[str, Any]]:
        """Generate ``count`` job postings."""
        if count < 0:
            raise ValueError(f"count must be non-negative, got {count}")
        return [self.generate_job() for _ in range(count)]

    # --- text rendering ----------------------------------------------------

    @staticmethod
    def render_resume_text(resume: dict[str, Any]) -> str:
        """Render a candidate record as the plain-text resume the ranker reads."""
        history = "\n".join(
            f"{job['title']} at {job['company']} ({job['start_date']} - {job['end_date']})"
            for job in resume["work_history"]
        )
        education = resume["education"]
        return (
            f"{resume['name']}\n"
            f"{resume['email']} | {resume['phone']}\n"
            f"{resume['location']}\n\n"
            f"PROFESSIONAL SUMMARY\n"
            f"{resume['role_category']} with {resume['experience_years']} years of experience\n\n"
            f"SKILLS\n{', '.join(resume['skills'])}\n\n"
            f"EDUCATION\n"
            f"{education['level']} in {education['field']}\n"
            f"{education['institution']} ({education['graduation_year']})\n\n"
            f"EXPERIENCE\n{history}\n"
        )

    @staticmethod
    def render_job_text(job: dict[str, Any]) -> str:
        """Render a job record as a plain-text job description."""
        return (
            f"{job['title']} at {job['company']}\n"
            f"Location: {job['location']}\n\n"
            f"We are seeking a {job['role_category']} with "
            f"{job['min_experience']}-{job['max_experience']} years of experience.\n\n"
            f"Required Skills: {', '.join(job['required_skills'])}\n"
            f"Preferred Skills: {', '.join(job['preferred_skills'])}\n\n"
            f"Salary: ${job['salary_min']:,} - ${job['salary_max']:,} {job['currency']}\n"
            f"Benefits: {', '.join(job['benefits'])}\n"
        )

    # --- persistence -------------------------------------------------------

    def save(self, records: list[dict[str, Any]], path: Path | str, kind: str) -> Path:
        """Write records to ``path`` as JSON with a metadata envelope.

        Args:
            records: The records to write.
            path: Destination file. Parent directories are created.
            kind: Plural noun used as the payload key, e.g. ``"resumes"``.

        Returns:
            The path written to.
        """
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metadata": {
                "generated_at": self._now.isoformat(),
                "count": len(records),
                "generator": type(self).__name__,
            },
            kind: records,
        }
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote %d %s to %s", len(records), kind, destination)
        return destination

    @staticmethod
    def summarise(resumes: list[dict[str, Any]]) -> dict[str, Any]:
        """Return dataset statistics as data.

        Returned rather than printed so callers can assert on it, log it, or
        render it however they need.
        """
        roles: dict[str, int] = {}
        bands = {"0-2": 0, "3-5": 0, "6-10": 0, "10+": 0}
        for resume in resumes:
            roles[resume["role_category"]] = roles.get(resume["role_category"], 0) + 1
            years = resume["experience_years"]
            if years <= 2:
                bands["0-2"] += 1
            elif years <= 5:
                bands["3-5"] += 1
            elif years <= 10:
                bands["6-10"] += 1
            else:
                bands["10+"] += 1
        return {"total": len(resumes), "by_role": roles, "by_experience_band": bands}
