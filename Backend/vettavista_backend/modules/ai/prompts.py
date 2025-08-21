from vettavista_backend.config import ai_settings, ai_prompts
from vettavista_backend.modules.models.services import JobDetailedInfo
from vettavista_backend.modules.utils import parse_employee_count


# Claude Prompts
# Combine all rules and format with job description
def create_extraction_prompt(job_description: str) -> str:
    return (f"{ai_prompts.claude_extraction_prompt_base}\n"
            f"{ai_prompts.claude_experience_rules}\n"
            f"{ai_prompts.claude_skills_rules}\n"
            f"{ai_prompts.claude_visa_rules}\n"
            f"{ai_prompts.claude_scoring_rules}\n\n"
            f"INPUT:\n{job_description}")

def get_cultural_context(job_info: JobDetailedInfo) -> str:
    """Get cultural context based on job location and company.

    Args:
        job_info: Job information including location and company size

    Returns:
        Formatted cultural context string based on location and company size
    """
    # Extract country from location (usually last part after comma)
    country = job_info.location.split(',')[-1].strip()

    # Parse company size
    size_ranges = {
        (1, 50): "Early-stage Startup",
        (51, 200): "Growing Startup",
        (201, 1000): "Mid-size Company",
        (1001, 5000): "Large Company",
        (5001, float('inf')): "Enterprise"
    }

    # Use utility function to parse employee count
    min_employees, _ = parse_employee_count(job_info.companySize)
    employee_count = min_employees  # Use lower bound for company type determination

    company_type = "Unknown Size"
    for (min_size, max_size), type_name in size_ranges.items():
        if min_size <= employee_count <= max_size:
            company_type = type_name
            break

    # Default context for unknown countries
    default_context = {
        "language": "English",
        "work_culture": [
            "Professional environment",
            "Team collaboration",
            "Clear communication",
            "Result-oriented approach"
        ],
        "business_practices": [
            "International standards",
            "Quality focus",
            "Customer orientation",
            "Professional development"
        ]
    }

    # Get context for country or use default
    context = ai_prompts.claude_cultural_contexts_dict.get(country, default_context)

    company_size_context = f"""- {company_type} environment
    - {"Rapid growth and adaptation" if employee_count < 200 else "Established processes"}
    - {"Flexible roles and responsibilities" if employee_count < 200 else "Specialized roles"}
    - {"Direct access to leadership" if employee_count < 200 else "Structured hierarchy"}"""

    cultural_context_prompt = ai_prompts.claude_cultural_context.format(
        country=country,
        company_type=company_type,
        company_size=job_info.companySize or "Unknown",
        working_language=context['language'],
        work_culture=chr(10).join(f'   - {item}' for item in context['work_culture']),
        business_context=chr(10).join(f'   - {item}' for item in context['business_practices']),
        company_size_context=company_size_context
    )

    return cultural_context_prompt

# System Messages (Claude)
claude_system_messages = {
    "extract_requirements": "You are a precise job requirements analyzer that performs independent analysis of different aspects. When analyzing multiple requirements, you must analyze each aspect separately and independently, without letting the analysis of one aspect influence another. Your responses must be valid JSON matching the specified format for each aspect.",
    "answer_question": "You are a job applicant. Provide direct, professional answers.",
    "customize_resume": "You are a professional resume consultant with expertise in international markets. Help customize this resume to highlight the most relevant qualifications for the target role. Focus on matching skills and experiences without fabricating information. Maintain conversation context and build upon previous exchanges. Pay special attention to cultural context and technical domain integrity.",
    "generate_cover_letter": "You are a cover letter specialist crafting technically-grounded narratives that integrate professional, cultural, and career elements while maintaining natural sentence structure."
}
