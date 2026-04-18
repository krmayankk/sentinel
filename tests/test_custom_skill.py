"""Tests for sentinel.skills.custom — loading custom skill prompts."""
import os
import tempfile

from sentinel.skills.custom import load_custom_skills


def test_load_custom_skills():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)

        with open(os.path.join(skills_dir, "cost_check.md"), "w") as f:
            f.write("Check that all AWS resources have a cost_center tag.")

        with open(os.path.join(skills_dir, "api_versioning.md"), "w") as f:
            f.write("Check API version bumps on breaking changes.")

        skills = load_custom_skills(d)
        names = [s.name for s in skills]
        assert "cost_check" in names
        assert "api_versioning" in names
        assert len(skills) == 2


def test_load_no_skills_dir():
    with tempfile.TemporaryDirectory() as d:
        skills = load_custom_skills(d)
        assert skills == []


def test_load_empty_file_skipped():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)

        with open(os.path.join(skills_dir, "empty.md"), "w") as f:
            f.write("")

        skills = load_custom_skills(d)
        assert len(skills) == 0


def test_non_md_files_ignored():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)

        with open(os.path.join(skills_dir, "notes.txt"), "w") as f:
            f.write("This is not a skill.")

        with open(os.path.join(skills_dir, "real_skill.md"), "w") as f:
            f.write("Check something important.")

        skills = load_custom_skills(d)
        assert len(skills) == 1
        assert skills[0].name == "real_skill"


def test_custom_skill_name_from_filename():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".sentinel", "skills")
        os.makedirs(skills_dir)

        with open(os.path.join(skills_dir, "my_team_check.md"), "w") as f:
            f.write("Check team-specific conventions.")

        skills = load_custom_skills(d)
        assert skills[0].name == "my_team_check"
