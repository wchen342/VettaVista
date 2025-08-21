"""
Claude integration for job application processing.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Union, AsyncGenerator, Tuple, List, Any

import demjson3
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from anthropic._exceptions import ServiceUnavailableError, OverloadedError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from vettavista_backend.config import resume, ResumeModel, DynamicConfig, global_constants, ai_prompts
from vettavista_backend.modules.ai import ClaudeServiceProtocol
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.business.utils.language_detector import HybridLanguageDetector
from vettavista_backend.modules.utils import DataClassJSONEncoder

logger = logging.getLogger(__name__)

# Import settings from config
from vettavista_backend.config import secrets, ai_settings
from vettavista_backend.modules.ai.prompts import claude_system_messages, create_extraction_prompt, get_cultural_context
from vettavista_backend.modules.models.services import JobDetailedInfo, JobAnalysisInfo, VisaSupport
from vettavista_backend.config.models import ExperienceEntry, ProjectEntry

class ClaudeResponseError(Exception):
    """Raised when Claude's response doesn't meet our requirements."""
    pass

class ClaudeService(ClaudeServiceProtocol):
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=secrets.claude_api_key, http_client=DefaultAioHttpClient())

        # The sdk needs to be re-initialized if secrets changed
        secrets.register_listener(self.on_secrets_changed)

        self.api_semaphore = asyncio.Semaphore(2)  # Allow max 2 concurrent API calls

    def config_thinking_temperature(self, high_temperature=False):
        """
        Decide which group of parameters to use based on if thinking is enabled
        :param high_temperature: Whether using the higher temperature
        :return:
        """
        if ai_settings.claude_thinking:
            return {
                'thinking': {
                    "type": "enabled",
                    "budget_tokens": ai_settings.claude_thinking_budget_tokens
                }
            }
        else:
            return {
                'temperature': ai_settings.claude_customization_temperature if high_temperature
                else ai_settings.claude_extraction_temperature,
            }

    def validate_and_clean_skills_dict(self, skills_dict: Dict) -> Dict:
        """
        Validate and clean the skills dictionary.
        Ensures all required keys exist and values are lists of strings.
        """
        required_keys = [
            "programming languages",
            "frameworks",
            "mobile development",
            "other technical",
            "soft skills"
        ]

        # Create default structure
        clean_dict = {
            key: [] for key in required_keys
        }
        clean_dict["languages"] = {
            "required": [],
            "preferred": []
        }

        if not isinstance(skills_dict, dict):
            logger.error("Skills data is not a dictionary")
            return clean_dict

        # Clean and validate each category
        for key in required_keys:
            if key in skills_dict and isinstance(skills_dict[key], list):
                # Clean each skill: remove duplicates, empty strings, and ensure strings
                skills = []
                seen = set()
                for skill in skills_dict[key]:
                    if not skill or not isinstance(skill, str):
                        continue
                    skill_clean = skill.strip()
                    if not skill_clean or skill_clean.lower() in seen:
                        continue
                    seen.add(skill_clean.lower())
                    skills.append(skill_clean)
                clean_dict[key] = skills

        # Handle language requirements separately
        if "languages" in skills_dict:
            lang_reqs = skills_dict["languages"]
            if isinstance(lang_reqs, dict):
                for key in ["required", "preferred"]:
                    if key in lang_reqs and isinstance(lang_reqs[key], list):
                        clean_dict["languages"][key] = [
                            lang.strip().upper()
                            for lang in lang_reqs[key]
                            if isinstance(lang, str) and lang.strip()
                        ]

        return clean_dict

    def extract_json_from_response(self, text: str) -> Dict:
        """
        Extract and parse JSON from Claude's response.
        Handles various formats and common issues.
        """
        # Remove any markdown formatting
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        # Clean up the text
        text = text.strip()

        try:
            # Try parsing the cleaned text
            return demjson3.decode(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ClaudeResponseError("Failed to parse JSON response")
        except UnicodeDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ClaudeResponseError("Failed to parse JSON response")

    def process_language_requirements(self, post_lang: str, skill_dict: Dict):
        # Handle language requirements separately
        claude_langs = skill_dict.get('languages', {})
        if not claude_langs.get('required'):
            # If Claude didn't find explicit requirements, assume the post's language is required
            skill_dict['languages'] = {
                'required': [post_lang],
                'preferred': []
            }
            logger.info(f"No explicit language requirements found, using post language: {post_lang}")
        else:
            logger.info(f"Found explicit language requirements: {claude_langs['required']}")
            if post_lang not in claude_langs['required']:
                logger.info(
                    f"Note: Job post language {post_lang} differs from required languages {claude_langs['required']}")
        # Add post language to the response for reference
        skill_dict['post_language'] = post_lang

    def validate_experience_dict(self, experience_dict):
        # Validate structure
        required_keys = ["years", "months", "is_minimum", "context"]
        if not all(key in experience_dict for key in required_keys):
            raise ClaudeResponseError("Missing required keys in response")
        logger.info("Successfully extracted experience requirements")

    async def stream_response(self, stream) -> AsyncGenerator[str, None]:
        """
        Stream Claude's response chunk by chunk.
        """
        full_text = ""
        async for message in stream:
            if not message.delta.text:
                continue
            chunk = message.delta.text
            full_text += chunk
            yield chunk
        yield full_text  # Yield complete response at the end

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        retry=retry_if_exception_type((ClaudeResponseError, ServiceUnavailableError, OverloadedError))
    )
    async def answer_question(self, question: str, user_info: str) -> Union[str, AsyncGenerator[str, None]]:
        """
        Answer job application questions using Claude.
        Returns a string with the answer, or a stream of responses if stream=True.
        """
        try:
            # Format prompt with question and user info
            prompt = ai_settings.claude_answer_question.format(
                question=question,
                user_info=user_info
            )

            async with self.anthropic.messages.stream(
                    model=global_constants.claude_4_0_sonnet_model,
                    max_tokens=ai_settings.claude_max_tokens,
                    **self.config_thinking_temperature(high_temperature=True),
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt,
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ]
                        }
                    ],
                    system=[
                        {
                            "type": "text",
                            "text": claude_system_messages["answer_question"],
                            "cache_control": {"type": "ephemeral", "ttl": "1h"}
                        }
                    ],
            ) as stream:
                message = await stream.get_final_message()


            if ai_settings.claude_thinking:
                answer = message.content[1].text.strip()
            else:
                answer = message.content[0].text.strip()
            if not answer:
                raise ClaudeResponseError("Empty response received")

            logger.info("Successfully generated answer")
            return answer

        except Exception as e:
            if isinstance(e, ClaudeResponseError):
                raise  # Let retry handle these
            logger.error(f"Error answering question: {str(e)}")
            return ""

    def validate_red_flags(self, red_flags_dict: Dict) -> Dict:
        """Validate and clean the red flags dictionary.
        
        Args:
            red_flags_dict: Raw red flags data from Claude
            
        Returns:
            Dict with validated score and reasons
        """
        clean_dict = {
            "score": 0,
            "reasons": []
        }
        
        if not isinstance(red_flags_dict, dict):
            logger.error("Red flags data is not a dictionary")
            return clean_dict
        
        # Validate score
        score = red_flags_dict.get("score")
        if isinstance(score, (int, float)) and 0 <= score <= 100:
            clean_dict["score"] = int(score)
        else:
            logger.error(f"Invalid red flags score: {score}")
        
        # Validate reasons
        reasons = red_flags_dict.get("reasons", [])
        if isinstance(reasons, list):
            clean_dict["reasons"] = [
                str(reason).strip() 
                for reason in reasons 
                if isinstance(reason, str) and reason.strip()
            ]
        else:
            logger.error(f"Invalid red flags reasons: {reasons}")
        
        return clean_dict

    def validate_visa_support(self, support_status: str) -> VisaSupport:
        """Validate and clean the visa support status.
        
        Args:
            support_status: Raw visa support status from Claude
            
        Returns:
            VisaSupport enum value (SUPPORTED/UNSUPPORTED/UNKNOWN)
        """
        try:
            # Convert input to uppercase string and try to create enum
            status = str(support_status).strip().upper()
            return VisaSupport(status)
        except (ValueError, AttributeError):
            logger.error(f"Invalid visa support status: {support_status}")
            return VisaSupport.UNKNOWN

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        retry=retry_if_exception_type((ClaudeResponseError, ServiceUnavailableError, OverloadedError))
    )
    async def batch_extract_job_info(self, job_description: str, post_lang: str) -> Tuple[Dict, Dict, Dict, VisaSupport]:
        """
        Extract job information in a single Claude call to reduce API latency.
        
        Args:
            job_description: The job posting text
            post_lang: Language of the job post
            
        Returns:
            Tuple containing:
            - skills_dict: Dictionary of extracted skills
            - exp_dict: Dictionary of experience requirements
            - red_flags_dict: Dictionary with red flags score and reasons
            - visa_support: Visa support status string
        """
        try:
            async with self.api_semaphore:
                # Combine both prompts into a single request
                prompt = create_extraction_prompt(job_description)
                async with self.anthropic.messages.stream(
                        model=global_constants.claude_4_0_sonnet_model,
                        max_tokens=ai_settings.claude_max_tokens,
                        **self.config_thinking_temperature(high_temperature=False),
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": prompt,
                                        "cache_control": {"type": "ephemeral"}
                                    }
                                ]
                            }
                        ],
                        system=[
                            {
                                "type": "text",
                                "text": claude_system_messages["extract_requirements"],
                                "cache_control": {"type": "ephemeral", "ttl": "1h"}
                            }
                        ],  # Use unified extraction system message
                ) as stream:
                    message = await stream.get_final_message()

                # Extract and validate JSON
                if ai_settings.claude_thinking:
                    response_text = message.content[1].text
                else:
                    response_text = message.content[0].text

                # Parse JSON and validate structure
                response_dict = self.extract_json_from_response(response_text)
                print(response_dict)

                # Extract and validate skills part
                skills_dict = self.validate_and_clean_skills_dict(response_dict.get('skills', {}))

                # Process language requirements from job description
                self.process_language_requirements(post_lang, skills_dict)

                # Verify we got some data
                if not any(skills_dict.values()):
                    raise ClaudeResponseError("No skills extracted")

                # Extract and validate experience part
                exp_dict = response_dict.get('experience', {})
                self.validate_experience_dict(exp_dict)

                # Extract and validate new fields
                red_flags_dict = self.validate_red_flags(response_dict.get('red_flags', {}))
                visa_support = self.validate_visa_support(response_dict.get('supports_visa', 'UNKNOWN'))

                return skills_dict, exp_dict, red_flags_dict, visa_support

        except ServiceUnavailableError as e:
            logger.warning(f"Claude service unavailable: {str(e)}")
            raise  # Let retry handle it
        except OverloadedError as e:
            logger.warning(f"Claude overloaded: {str(e)}")
            raise  # Let retry handle it
        except Exception as e:
            if isinstance(e, ClaudeResponseError):
                raise  # Let retry handle these
            logger.error(f"Error in batch extraction: {str(e)}")
            raise

    def validate_resume_skills(self, skills_json: Dict) -> Dict:
        """Validate and clean the skills JSON to match resume config structure.
        
        Args:
            skills_json: Skills data from Claude
            
        Returns:
            Cleaned skills dict preserving Claude's categories and recommendations
        """
        if not isinstance(skills_json, dict):
            logger.error("Skills data is not a dictionary")
            return {"Recommended Skills": []}
        
        # Get original skills as a case-insensitive set for reference
        original_skills = {str(skill).strip().lower(): str(skill).strip() 
                          for category in resume.skills.values() 
                          for skill in category}
        
        clean_dict = {}
        
        # Process each category from Claude's response
        for category, skills in skills_json.items():
            if not isinstance(skills, list):
                continue
            
            # Clean and validate skills in this category
            valid_skills = []
            for skill in skills:
                if not isinstance(skill, str):
                    continue
                
                skill_clean = skill.strip()
                if not skill_clean:
                    continue
                
                skill_lower = skill_clean.lower()
                # If skill exists in original resume, use that capitalization
                if skill_lower in original_skills:
                    # Use the original capitalization from the resume
                    valid_skills.append(original_skills[skill_lower])
                else:
                    # For new skills (including recommendations), keep Claude's version
                    valid_skills.append(skill_clean)
                
            if valid_skills:  # Only include non-empty categories
                clean_dict[category] = valid_skills
                
        return clean_dict

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        retry=retry_if_exception_type((ClaudeResponseError, ServiceUnavailableError, OverloadedError))
    )
    async def customize_resume(self, job_info: JobDetailedInfo, job_cache_service: JobCacheService) -> Tuple[ResumeModel, ResumeModel]:
        """Customize resume based on job requirements using Claude.
        
        Uses a conversational approach to:
        1. Initialize context with job and resume data
        2. Optimize skills section
        3. Tailor experience entries
        4. Adapt projects section
        
        Args:
            job_info: Detailed job information including description and requirements
            job_cache_service: Service for caching job analysis results
        
        Returns:
            Tuple[ResumeModel, ResumeModel]: A tuple containing (original_resume, customized_resume)
        """
        try:
            async with self.api_semaphore:
            # Check cache first
                cached_resume = await job_cache_service.get_customized_resume(job_info.jobId)
                if cached_resume:
                    logger.info(f"Using cached customized resume for job {job_info.jobId}")
                    # Return both original and cached resume
                    return resume, cached_resume

                # Get cached analysis results
                cached_analysis = await job_cache_service.get_job_analysis(job_info.jobId)
                if not cached_analysis:
                    logger.warning(f"No cached analysis found for job {job_info.jobId}, performing new analysis")
                    post_lang, _ = HybridLanguageDetector().detect_language(job_info.description)
                    post_lang = post_lang if post_lang else 'ENGLISH'
                    skills_dict, exp_dict, red_flags_dict, visa_support = await self.batch_extract_job_info(job_info.description, post_lang)
                    analysis_info = JobAnalysisInfo(
                        skills_dict=skills_dict,
                        experience_dict=exp_dict,
                        red_flags_dict=red_flags_dict,
                        visa_support=visa_support,
                        post_language=post_lang
                    )
                    await job_cache_service.set_job_analysis(job_info.jobId, analysis_info)
                else:
                    logger.info(f"Using cached analysis for job {job_info.jobId}")
                    skills_dict = cached_analysis.skills_dict
                    exp_dict = cached_analysis.experience_dict

                # Prepare resume data with IDs
                experiences_with_ids = []
                for i, exp in enumerate(resume.experience):
                    # Create a copy of the experience
                    exp_copy = ExperienceEntry(
                        title=exp.title,
                        organization=exp.organization,
                        start=exp.start,
                        end=exp.end,
                        location=exp.location,
                        details=exp.details
                    )
                    # Set the ID using the property
                    exp_copy.set_id(str(i))
                    experiences_with_ids.append(exp_copy)

                projects_with_ids = []
                for i, proj in enumerate(resume.projects):
                    # Create a copy of the project
                    proj_copy = ProjectEntry(
                        name=proj.name,
                        details=proj.details
                    )
                    # Set the ID using the property
                    proj_copy.set_id(str(i))
                    projects_with_ids.append(proj_copy)

                # Create resume data with typed objects
                resume_data = {
                    "skills": resume.skills,
                    "experience": experiences_with_ids,
                    "projects": projects_with_ids
                }

                # Create previous analysis dict
                job_post_analysis = {
                    "skills": skills_dict,
                    "experience": exp_dict
                }

                # Get cultural context based on job location/company
                cultural_context = get_cultural_context(job_info)
                
                try:
                    # Initialize conversation with context
                    logger.info("\n=== Starting Conversation with Claude ===")
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": ai_prompts.claude_resume_init.format(
                                        job_description=job_info.description,
                                        resume_data=resume_data,
                                        job_post_analysis=json.dumps(job_post_analysis, indent=2),
                                        cultural_context=cultural_context
                                    ),
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ]
                        }
                    ]
                    
                    # Log initial prompt
                    logger.info("\nInitial Prompt:")
                    logger.info(messages[0]["content"])
                    
                    # Get initial understanding confirmation
                    async with self.anthropic.messages.stream(
                            model=global_constants.claude_4_0_sonnet_model,
                            max_tokens=ai_settings.claude_max_tokens,
                            **self.config_thinking_temperature(high_temperature=True),
                            messages=messages,
                            system=[
                                {
                                    "type": "text",
                                    "text": claude_system_messages["customize_resume"],
                                    "cache_control": {"type": "ephemeral", "ttl": "1h"}
                                }
                            ],
                    ) as stream:
                        response = await stream.get_final_message()

                    logger.info("\nClaude's Initial Response:")
                    if ai_settings.claude_thinking:
                        logger.info(response.content[1].text)
                    else:
                        logger.info(response.content[0].text)
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # Optimize skills section
                    logger.info("\n=== Skills Section Optimization ===")
                    # Remove previous cache checkpoints
                    for message in messages:
                        if message.get('content', None):
                            for content in message['content']:
                                if isinstance(content,dict) and 'content' in content:
                                    del content['cache_control']
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ai_prompts.claude_resume_skills,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })

                    async with self.anthropic.messages.stream(
                            model=global_constants.claude_4_0_sonnet_model,
                            max_tokens=ai_settings.claude_max_tokens,
                            **self.config_thinking_temperature(high_temperature=True),
                            messages=messages,
                            system=[
                                {
                                    "type": "text",
                                    "text": claude_system_messages["customize_resume"],
                                }
                            ],
                    ) as stream:
                        response = await stream.get_final_message()

                    if ai_settings.claude_thinking:
                        skills_response = response.content[1].text
                    else:
                        skills_response = response.content[0].text
                    logger.info("\nClaude's Skills Response:")
                    logger.info(skills_response)
                    skills_json = self.extract_json_from_response(skills_response)
                    skills_json = self.validate_resume_skills(skills_json)
                    logger.info("\nValidated Skills JSON:")
                    logger.info(json.dumps(skills_json, indent=2))
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # Tailor experience section
                    logger.info("\n=== Experience Section Customization ===")
                    # Remove previous cache checkpoints
                    for message in messages:
                        if message.get('content', None):
                            for content in message['content']:
                                if isinstance(content, dict) and 'content' in content:
                                    del content['cache_control']
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ai_prompts.claude_resume_experience,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })
                    async with self.anthropic.messages.stream(
                            model=global_constants.claude_4_0_sonnet_model,
                            max_tokens=ai_settings.claude_max_tokens,
                            **self.config_thinking_temperature(high_temperature=True),
                            messages=messages,
                            system=[
                                {
                                    "type": "text",
                                    "text": claude_system_messages["customize_resume"],
                                }
                            ],
                    ) as stream:
                        response = await stream.get_final_message()

                    if ai_settings.claude_thinking:
                        experience_response = response.content[1].text
                    else:
                        experience_response = response.content[0].text
                    logger.info("\nClaude's Experience Response:")
                    logger.info(experience_response)
                    experience_json = self.extract_json_from_response(experience_response)
                    experience_json = self.validate_resume_experience(experience_json, resume_data["experience"])
                    logger.info("\nValidated Experience JSON:")
                    logger.info(json.dumps(experience_json, cls=DataClassJSONEncoder, indent=2))
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # Adapt projects section
                    logger.info("\n=== Projects Section Adaptation ===")
                    # Remove previous cache checkpoints
                    for message in messages:
                        if message.get('content', None):
                            for content in message['content']:
                                if isinstance(content, dict) and 'content' in content:
                                    del content['cache_control']
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ai_prompts.claude_resume_projects,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })
                    async with self.anthropic.messages.stream(
                            model=global_constants.claude_4_0_sonnet_model,
                            max_tokens=ai_settings.claude_max_tokens,
                            **self.config_thinking_temperature(high_temperature=True),
                            messages=messages,
                            system=[
                                {
                                    "type": "text",
                                    "text": claude_system_messages["customize_resume"],
                                }
                            ],
                    ) as stream:
                        response = await stream.get_final_message()

                    if ai_settings.claude_thinking:
                        projects_response = response.content[1].text
                    else:
                        projects_response = response.content[0].text
                    logger.info("\nClaude's Projects Response:")
                    logger.info(projects_response)
                    projects_json = self.extract_json_from_response(projects_response)
                    projects_json = self.validate_resume_projects(projects_json, resume_data["projects"])
                    logger.info("\nValidated Projects JSON:")
                    logger.info(json.dumps(projects_json, cls=DataClassJSONEncoder, indent=2))

                    # Create ResumeModel directly
                    customized = ResumeModel(
                        website=resume.website,
                        linkedIn=resume.linkedIn,
                        skills=skills_json,
                        experience=experience_json,
                        projects=projects_json,
                        educations=resume.educations,
                        did_masters=resume.did_masters,
                        highest_degree=resume.highest_degree,
                        cover_letter_template=resume.cover_letter_template
                    )
                    
                    logger.info("\n=== Resume Customization Complete ===")
                    logger.info("\nFinal Customized Resume:")
                    logger.info(json.dumps(customized, cls=DataClassJSONEncoder, indent=2))

                    # Reconstruct ResumeModel from resume_data for type safety
                    original_resume_data = ResumeModel(
                        website=resume.website,
                        linkedIn=resume.linkedIn,
                        skills=resume.skills,
                        experience=experiences_with_ids,
                        projects=projects_with_ids,
                        educations=resume.educations,
                        did_masters=resume.did_masters,
                        highest_degree=resume.highest_degree,
                        cover_letter_template=resume.cover_letter_template
                    )
                        
                    # Cache the customized resume before returning
                    await job_cache_service.set_customized_resume(job_info.jobId, customized)
                    return original_resume_data, customized
                    
                except Exception as e:
                    logger.error(f"Error customizing resume: {str(e)}")
                    raise

        except Exception as e:
            logger.error(f"Error customizing resume: {str(e)}")
            raise

    def validate_resume_experience(self, experience_json: Dict[str, Any], original_experiences: List[ExperienceEntry]) -> List[ExperienceEntry]:
        """Validate and convert experience JSON to typed ExperienceEntry objects.
        
        Args:
            experience_json: Raw JSON response from Claude
            original_experiences: List of original ExperienceEntry objects
            
        Returns:
            List of validated ExperienceEntry objects with optimized achievements
        """
        # First ensure we have the correct structure
        if not isinstance(experience_json, dict):
            logger.error("Experience data is not a dictionary")
            return []
        
        # Get the experience array
        experience_list = experience_json.get("optimized_experience", [])
        if not isinstance(experience_list, list):
            logger.error("optimized_experience is not a list")
            return []
        
        # Create mapping of IDs to original experiences
        exp_map = {exp.exp_id: exp for exp in original_experiences if exp.exp_id is not None}
        
        validated_experiences: List[ExperienceEntry] = []
        for exp in experience_list:
            try:
                if not isinstance(exp, dict):
                    logger.error(f"Invalid experience entry format: {exp}")
                    continue
                
                exp_id = exp.get("exp_id")
                if not exp_id or exp_id not in exp_map:
                    logger.error(f"Invalid or missing exp_id: {exp_id}")
                    continue
                
                original = exp_map[exp_id]
                
                # Validate achievements
                achievements = exp.get("achievements", [])
                if not isinstance(achievements, list):
                    logger.error(f"Invalid achievements format for experience {exp_id}")
                    continue
                
                clean_achievements = []
                for achievement in achievements:
                    if not isinstance(achievement, dict):
                        continue
                    
                    if not all(k in achievement for k in ["text", "is_critical", "domain", "relevance_score"]):
                        logger.error(f"Missing required fields in achievement: {achievement}")
                        continue
                    
                    # Type validation and normalization
                    if not isinstance(achievement["text"], str):
                        continue
                    
                    clean_achievements.append(achievement["text"].strip())
                
                # Warn about minimum achievements
                if len(clean_achievements) < 2:
                    logger.warning(f"Less than 2 achievements for experience: {exp_id}")
                
                # Create typed ExperienceEntry using original data + cleaned achievements
                validated_exp = ExperienceEntry(
                    title=original.title,
                    organization=original.organization,
                    start=original.start,
                    end=original.end,
                    location=original.location,
                    details=clean_achievements,
                )
                
                # Copy over the ID from original
                validated_exp.set_id(original.exp_id)
                
                validated_experiences.append(validated_exp)
                
            except (KeyError, TypeError, ValueError) as e:
                logger.error(f"Error validating experience: {str(e)}")
                continue
            
        return validated_experiences

    def validate_resume_projects(self, projects_json: Dict[str, Any], original_projects: List[ProjectEntry]) -> List[ProjectEntry]:
        """Validate and convert projects JSON to typed ProjectEntry objects.
        
        Args:
            projects_json: Raw JSON response from Claude
            original_projects: List of original ProjectEntry objects
            
        Returns:
            List of validated ProjectEntry objects with optimized details
        """
        # First ensure we have the correct structure
        if not isinstance(projects_json, dict):
            logger.error("Projects data is not a dictionary")
            return []
        
        projects_list = projects_json.get("optimized_projects", [])
        if not isinstance(projects_list, list):
            logger.error("optimized_projects is not a list")
            return []
        
        # Create mapping of IDs to original projects
        proj_map = {proj.proj_id: proj for proj in original_projects if proj.proj_id is not None}
        
        validated_projects: List[ProjectEntry] = []
        for proj in projects_list:
            try:
                if not isinstance(proj, dict):
                    logger.error(f"Invalid project entry format: {proj}")
                    continue
                
                proj_id = proj.get("proj_id")
                if not proj_id or proj_id not in proj_map:
                    logger.error(f"Invalid or missing proj_id: {proj_id}")
                    continue
                
                original = proj_map[proj_id]
                
                # Validate achievements/details
                details = proj.get("achievements", [])
                if not isinstance(details, list):
                    logger.error(f"Invalid details format for project {proj_id}")
                    continue
                
                clean_details = []
                for detail in details:
                    if not isinstance(detail, dict):
                        continue
                    
                    if not all(k in detail for k in ["text", "domain"]):
                        logger.error(f"Missing required fields in detail: {detail}")
                        continue
                    
                    if not isinstance(detail["text"], str):
                        continue
                    
                    clean_details.append(detail["text"].strip())
                
                # Create typed ProjectEntry using original data + cleaned details
                validated_proj = ProjectEntry(
                    name=original.name,
                    details=clean_details
                )

                # Copy over the ID from original
                validated_proj.set_id(original.proj_id)
                
                validated_projects.append(validated_proj)
                
            except (KeyError, TypeError, ValueError) as e:
                logger.error(f"Error validating project: {str(e)}")
                continue
            
        return validated_projects

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        retry=retry_if_exception_type((ClaudeResponseError, ServiceUnavailableError, OverloadedError))
    )
    async def customize_cover_letter(self, resume_latex: str, job_info: JobDetailedInfo, job_cache_service: JobCacheService) -> str:
        """Customize cover letter using Claude"""
        try:
            async with self.api_semaphore:
                # Format prompt with resume and job description
                current_date = datetime.now().strftime("%B %Y")
                prompt = ai_prompts.claude_cover_letter.format(
                    resume_content=resume_latex,
                    job_description=job_info.description,
                    current_date=current_date,
                    cover_letter_template=resume.cover_letter_template
                )

                async with self.anthropic.messages.stream(
                        model=global_constants.claude_4_0_sonnet_model,
                        max_tokens=ai_settings.claude_max_tokens,
                        **self.config_thinking_temperature(high_temperature=True),
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": prompt,
                                        "cache_control": {"type": "ephemeral"}
                                    }
                                ]
                            }
                        ],
                        system=[
                            {
                                "type": "text",
                                "text": claude_system_messages["generate_cover_letter"],
                                "cache_control": {"type": "ephemeral", "ttl": "1h"}
                            }
                        ],
                ) as stream:
                    message = await stream.get_final_message()

                if ai_settings.claude_thinking:
                    cover_letter = message.content[1].text.strip()
                else:
                    cover_letter = message.content[0].text.strip()
                if not cover_letter:
                    raise ClaudeResponseError("Empty response received")

                await job_cache_service.set_cover_letter(job_info.jobId, cover_letter)
                logger.info("Successfully generated cover letter")
                return cover_letter

        except Exception as e:
            logger.error(f"Error generating cover letter: {str(e)}")
            raise

    def on_secrets_changed(self, new_secrets: DynamicConfig):
        logger.info(f"Secrets changes detected, re-initializing Anthropics SDK.")
        self.anthropic = AsyncAnthropic(api_key=new_secrets.claude_api_key, http_client=DefaultAioHttpClient())

    def cleanup(self):
        # Remove listener
        secrets.unregister_listener(self.on_secrets_changed)