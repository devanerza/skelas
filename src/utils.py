"""
Utility functions for scheduling
"""
from typing import List, Tuple


def generate_consecutive_blocks(credits: int, total_slots: int = 9) -> List[List[int]]:
    """
    Generate all valid consecutive slot blocks for a course with given credits.
    
    Important: Slots 1-5 are consecutive (morning), slots 6-9 are consecutive (afternoon).
    Slots 5->6 are NOT consecutive (lunch break).
    
    Args:
        credits: Number of credits (2-4)
        total_slots: Total number of slots per day (default 9)
    
    Returns:
        List of valid consecutive slot blocks
        
    Example:
        For 4 credits:
        [[1,2,3,4], [2,3,4,5], [6,7,8,9]]
        
        NOT valid: [3,4,5,6] (crosses lunch break)
    """
    if credits < 2 or credits > 4:
        raise ValueError(f"Credits must be 2-4, got {credits}")
    
    # Define consecutive ranges (lunch break between slot 5 and 6)
    morning_range = list(range(1, 6))  # [1,2,3,4,5]
    afternoon_range = list(range(6, 10))  # [6,7,8,9]
    
    blocks = []
    
    # Generate blocks from morning range
    for start in range(len(morning_range)):
        if start + credits <= len(morning_range):
            block = morning_range[start:start + credits]
            blocks.append(block)
    
    # Generate blocks from afternoon range
    for start in range(len(afternoon_range)):
        if start + credits <= len(afternoon_range):
            block = afternoon_range[start:start + credits]
            blocks.append(block)
    
    return blocks


def slots_overlap(block1: List[int], block2: List[int]) -> bool:
    """
    Check if two slot blocks overlap.
    
    Args:
        block1: First slot block
        block2: Second slot block
        
    Returns:
        True if blocks overlap, False otherwise
    """
    set1 = set(block1)
    set2 = set(block2)
    return len(set1 & set2) > 0
