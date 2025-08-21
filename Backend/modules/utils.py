import json
import re
from dataclasses import is_dataclass, asdict, fields
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Type, TypeVar


def parse_employee_count(size_str: str) -> tuple[int, int]:
    """Parse employee count range from string like '201-500 employees' or '10,001+ employees'
    
    Args:
        size_str: Company size string (e.g. "201-500 employees", "10,001+ employees")
        
    Returns:
        Tuple of (min_employees, max_employees)
    """
    if not size_str:
        return 0, 0
            
    # Extract numbers using regex, now supporting commas and looking for + suffix
    number_strings = re.findall(r'\d{1,3}(?:,\d{3})*', size_str)
    if not number_strings:
        return 0, 0
            
    # Remove commas and convert to integers
    numbers = [int(n.replace(',', '')) for n in number_strings]
    
    if len(numbers) == 1:
        # Single number like "500 employees" or "10,001+ employees"
        if '+' in size_str:
            # For cases like "10,001+", return (10001, max_int)
            return numbers[0], 2 ** 31 - 1  # Using max 32-bit integer
        return numbers[0], numbers[0]
    elif len(numbers) == 2:
        # Range like "201-500 employees"
        return numbers[0], numbers[1]
            
    return 0, 0

def block_base_methods(blocked_methods=None, allowed_methods=None):
    """
    Decorator to manage access to base class methods.
    Args:
        blocked_methods: List of method names to block. If None and allowed_methods is None, blocks all base methods.
        allowed_methods: List of method names to allow. Takes precedence over blocked_methods.
    """
    # Handle case when decorator is used without parentheses
    if isinstance(blocked_methods, type):
        cls = blocked_methods
        blocked_methods = None
        allowed_methods = None
        return _block_base_methods(cls, None, None)

    # Normal case when decorator is used with parameters
    def decorator(cls):
        return _block_base_methods(cls, blocked_methods, allowed_methods)

    return decorator


def _block_base_methods(cls, blocked_methods, allowed_methods):
    """Implementation of the decorator logic"""
    original_getattribute = cls.__getattribute__

    # Get all base classes in the inheritance chain
    def get_all_bases(c):
        bases = set()
        for base in c.__bases__:
            bases.add(base)
            bases.update(get_all_bases(base))
        return bases

    base_classes = get_all_bases(cls)

    # Get all base methods if no specific methods provided
    all_base_methods = set()
    for base in base_classes:
        all_base_methods.update(
            name for name, attr in base.__dict__.items()
            if callable(attr) and not name.startswith('_')
        )

    # Determine which methods to block based on parameters
    if allowed_methods is not None:
        # If allowed_methods is specified, block everything except those methods
        blocked_methods = all_base_methods - set(allowed_methods)
    elif blocked_methods is not None:
        # If only blocked_methods is specified, block just those methods
        blocked_methods = set(blocked_methods)
    else:
        # If neither is specified, block all base methods
        blocked_methods = all_base_methods

    def __getattribute__(self, name):
        if name.startswith('_'):
            return original_getattribute(self, name)

        attr = original_getattribute(self, name)

        # Check if it's an external call
        import inspect
        frame = inspect.currentframe()
        is_internal = frame.f_back.f_locals.get('self', None) is self

        # Block if it's an external call to a blocked base method
        if not is_internal:
            is_base_method = any(hasattr(base, name) for base in base_classes)
            if (callable(attr) and
                    is_base_method and
                    name in blocked_methods and
                    not name in cls.__dict__):
                raise AttributeError(
                    f"Cannot call base class method '{name}' directly"
                )

        return attr

    cls.__getattribute__ = __getattribute__
    cls._blocked_methods = blocked_methods
    return cls

class DataClassJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

T = TypeVar('T')

def decode_dataclass(cls: Type[T], data: Dict[str, Any]) -> T:
    """Recursively decode dictionary into dataclass instance"""
    if not is_dataclass(cls):
        return data
        
    fieldtypes = {f.name: f.type for f in fields(cls)}
    decoded_data = {}
    
    for key, value in data.items():
        if key not in fieldtypes:
            continue
            
        field_type = fieldtypes[key]
        
        # Handle nested dataclasses
        if is_dataclass(field_type) and isinstance(value, dict):
            decoded_data[key] = decode_dataclass(field_type, value)
        # Handle enums
        elif isinstance(field_type, type) and issubclass(field_type, Enum) and isinstance(value, str):
            decoded_data[key] = field_type(value)
        # Handle datetime
        elif field_type == datetime and isinstance(value, str):
            decoded_data[key] = datetime.fromisoformat(value)
        else:
            decoded_data[key] = value
            
    return cls(**decoded_data)