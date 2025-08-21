from typing import Dict, Any, List
from config import ResumeModel, ProjectEntry, ExperienceEntry
from datetime import datetime, date

def create_test_resume(**kwargs) -> ResumeModel:
    """Create a ResumeModel instance with test data"""
    defaults = {
        'skills': {
            'Programming Languages': ['Python', 'JavaScript'],
            'Frameworks': ['FastAPI', 'React'],
            'Tools': ['Git', 'Docker']
        },
        'experience': [
            ExperienceEntry(
                title="Software Engineer",
                organization="Test Company",
                start=datetime(2020, 1, 1),
                end=datetime.max,
                location="Remote",
                details=["Led development of test project", "Implemented test features"]
            )
        ],
        'projects': [
            ProjectEntry(
                name="Test Project",
                details=["Developed test functionality", "Implemented test features"]
            )
        ],
        'preferred_titles': ['Software Engineer', 'Developer'],
        'bad_words': [],
        'skip_required_skill': [],
        'highest_degree': 'Bachelor',
        'educations': [
            {
                'degree': 'Bachelor of Science',
                'major': 'Computer Science',
                'school': 'Test University',
                'graduation': date(2020, 1, 1)
            }
        ],
        'did_masters': False,
        'cover_letter_template': 'Dear Hiring Manager,\n\nTest template.'
    }
    defaults.update(kwargs)
    return ResumeModel(**defaults) 