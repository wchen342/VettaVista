import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, Any
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable, Union
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
from sklearn.metrics.pairwise import cosine_similarity


def calculate_date_posted(time_string: str) -> datetime | None | ValueError:
    """
    Function to calculate date posted from string.
    Returns datetime object | None if unable to calculate | ValueError if time_string is invalid
    Valid time string examples:
    * 10 seconds ago
    * 15 minutes ago
    * 2 hours ago
    * 1 hour ago
    * 1 day ago
    * 10 days ago
    * 1 week ago
    * 1 month ago
    * 1 year ago
    """
    time_string = time_string.strip()
    # print_lg(f"Trying to calculate date job was posted from '{time_string}'")
    now = datetime.now()
    if "second" in time_string:
        seconds = int(time_string.split()[0])
        date_posted = now - timedelta(seconds=seconds)
    elif "minute" in time_string:
        minutes = int(time_string.split()[0])
        date_posted = now - timedelta(minutes=minutes)
    elif "hour" in time_string:
        hours = int(time_string.split()[0])
        date_posted = now - timedelta(hours=hours)
    elif "day" in time_string:
        days = int(time_string.split()[0])
        date_posted = now - timedelta(days=days)
    elif "week" in time_string:
        weeks = int(time_string.split()[0])
        date_posted = now - timedelta(weeks=weeks)
    elif "month" in time_string:
        months = int(time_string.split()[0])
        date_posted = now - timedelta(days=months * 30)
    elif "year" in time_string:
        years = int(time_string.split()[0])
        date_posted = now - timedelta(days=years * 365)
    else:
        date_posted = None
    return date_posted


def batch_encode_strings(
    texts: List[str],
    model: SentenceTransformer,
    embedding_cache: Optional[Dict[str, np.ndarray]] = None
) -> Dict[str, np.ndarray]:
    """Batch encode strings to normalized embeddings with caching."""
    if embedding_cache is None:
        embedding_cache = {}
    
    # Find texts that need encoding
    texts_to_encode = [t for t in texts if t not in embedding_cache]
    
    if texts_to_encode:
        # Batch encode new texts
        embeddings = model.encode(texts_to_encode)
        # Normalize embeddings
        embeddings = normalize(embeddings)
        # Update cache
        embedding_cache.update(dict(zip(texts_to_encode, embeddings)))
    
    # Return embeddings for all texts
    return {text: embedding_cache[text] for text in texts}

def batch_encode_grouped_strings(
    text_groups: Dict[str, List[str]],
    model: SentenceTransformer,
    embedding_cache: Optional[Dict[str, np.ndarray]] = None
) -> Dict[str, np.ndarray]:
    """Batch encode groups of strings to mean embeddings with caching."""
    if embedding_cache is None:
        embedding_cache = {}
    
    # Find groups that need encoding
    groups_to_encode = {
        key: texts for key, texts in text_groups.items() 
        if key not in embedding_cache
    }
    
    if groups_to_encode:
        # Concatenate all texts for batch encoding
        all_texts = []
        key_indices = {}  # Track which embeddings belong to which key
        current_idx = 0
        
        for key, texts in groups_to_encode.items():
            key_indices[key] = (current_idx, current_idx + len(texts))
            all_texts.extend(texts)
            current_idx += len(texts)
        
        # Batch encode all texts at once
        if all_texts:
            all_embeddings = model.encode(all_texts)
            all_embeddings = normalize(all_embeddings)
            
            # Calculate mean embeddings for each group
            for key, (start_idx, end_idx) in key_indices.items():
                group_embeddings = all_embeddings[start_idx:end_idx]
                mean_embedding = np.mean(group_embeddings, axis=0)
                # Normalize mean embedding
                mean_embedding = normalize(mean_embedding.reshape(1, -1))[0]
                embedding_cache[key] = mean_embedding
    
    # Return embeddings for all groups
    return {key: embedding_cache[key] for key in text_groups.keys()}

def get_from_cache_symmetric(cache: Dict, key: Tuple[str, str]) -> Optional[Any]:
    """Get value from cache checking both (a,b) and (b,a) keys."""
    if cache is None:
        return None
    
    # Try both orderings for cache lookup
    reverse_key = (key[1], key[0])
    return cache.get(key) or cache.get(reverse_key)

def find_best_match_from_cache(cache: Dict[Tuple[str, str], float], key: str, key_list: List[str]) -> tuple[
    float, str | None]:
    """Get the match from cache with the highest score. Only applicable when cache is using this specific format"""
    best_score = 0.0
    best_match = None
    for key2 in key_list:
        score = get_from_cache_symmetric(cache, (key, key2))
        if score and score > best_score:
            best_score = float(score)
            best_match = key2

    return best_score, best_match

def calculate_pairwise_similarities(
    embeddings1: Dict[str, np.ndarray],
    embeddings2: Dict[str, np.ndarray],
    element_wise_fn: Optional[Callable[[float], float]] = None,
    matrix_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    similarity_cache: Optional[Dict[Tuple[str, str], float]] = None
) -> Dict[Tuple[str, str], float]:
    """Calculate pairwise similarities between two sets of embeddings with caching."""
    if similarity_cache is None:
        similarity_cache = {}
    
    # Initialize result dictionary
    result = {}
    
    # Check cache and collect pairs that need computation
    uncached_indices = []  # List of (i, j) for uncached pairs
    keys1 = list(embeddings1.keys())
    keys2 = list(embeddings2.keys())
    
    for i, key1 in enumerate(keys1):
        for j, key2 in enumerate(keys2):
            cache_key = (key1, key2)
            cached_value = get_from_cache_symmetric(similarity_cache, cache_key)
            
            if cached_value is not None:
                result[cache_key] = cached_value
            else:
                uncached_indices.append((i, j))
    
    # If there are uncached pairs, compute them
    if uncached_indices:
        # Convert embeddings to matrices
        matrix1 = np.stack([embeddings1[k] for k in keys1])
        matrix2 = np.stack([embeddings2[k] for k in keys2])
        
        # Calculate all similarities
        similarities = cosine_similarity(matrix1, matrix2)
        
        # Apply matrix function if provided
        if matrix_fn is not None:
            similarities = matrix_fn(similarities)
        
        # Process uncached pairs
        for i, j in uncached_indices:
            sim = float(similarities[i, j])
            if element_wise_fn is not None:
                sim = element_wise_fn(sim)
            
            # Store in result and cache
            cache_key = (keys1[i], keys2[j])
            result[cache_key] = sim
            similarity_cache[cache_key] = sim
    
    return result


def load_model_prefer_cache(model_name, cache_dir=None):
    # Get default cache dir if not specified
    if cache_dir is None:
        cache_dir = os.path.expanduser('~/.cache/huggingface/hub')

    # Convert model name to cache folder format
    if not model_name.startswith('models--'):
        cache_name = f"models--{model_name.replace('/', '--')}"
    else:
        cache_name = model_name

    model_path = Path(cache_dir) / cache_name / 'snapshots'

    # Find the snapshot directory (usually contains a hash)
    if model_path.exists():
        snapshot_dirs = list(model_path.iterdir())
        if snapshot_dirs:
            actual_model_path = snapshot_dirs[0]  # Use the first snapshot
            print(f"Loading model from cache: {actual_model_path}")
            return SentenceTransformer(str(actual_model_path))

    print(f"Model not found in cache, downloading: {model_name}")
    return SentenceTransformer(model_name)