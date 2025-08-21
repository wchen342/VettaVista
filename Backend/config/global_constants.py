"""
Configuration settings for job filtering.
"""

from enum import Enum

# Thresholds for determining match status
HIGH_THRESHOLD = 0.8  # For "likely_match"
LOW_THRESHOLD = 0.45   # For "possible_match"

# Title matching settings
TITLE_MATCH_SETTINGS = {
    'model_name': 'intfloat/multilingual-e5-large',  # Model for semantic similarity
    'cache_size': 1000,  # Number of title embeddings to cache
}

# Storage settings
STORAGE_SETTINGS = {
    'blacklist_key': 'blacklisted_companies',
    'rejected_key': 'rejected_jobs',
    'sync_interval': 300,
    'history_file': 'job_history.csv',
    'blacklist_file': 'blacklist.csv',
    'backup_interval': 86400,
}

# Application status definitions
class ApplicationStatus(str, Enum):
    NEW = 'new'                    # Just found
    APPLIED = 'applied'            # Application submitted
    REJECTED = 'rejected'          # Received rejection
    IN_PROGRESS = 'in_progress'    # In process
    OFFER = 'offer'                # Received offer
    ACCEPTED = 'accepted'          # Accepted offer
    DECLINED = 'declined'          # User declined offer
    NOT_INTERESTED = 'not_interested' # User not interested
    NO_RESPONSE = 'no_response'     # No response after user-determined time

# Job match status definitions
class JobStatus(str, Enum):
    UNKNOWN = 'unknown'
    LIKELY_MATCH = 'likely_match'
    POSSIBLE_MATCH = 'possible_match'
    NOT_LIKELY = 'not_likely'
    CONFIRMED_MATCH = 'confirmed_match'
    CONFIRMED_NO_MATCH = 'confirmed_no_match'
    ERROR = 'error'

# Claude Model strings
claude_3_7_sonnet_model = "claude-3-7-sonnet-20250219"
claude_4_0_sonnet_model = "claude-sonnet-4-20250514"
claude_4_1_opus_model = "claude-opus-4-1-20250805"


VERSION = "0.0.1"
APP_NAME = "VettaVista"