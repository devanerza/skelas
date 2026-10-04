"""
Utility functions for scheduling
"""
from typing import List, Tuple


def generate_consecutive_blocks(credits: int, total_slots: int = 9) -> List[List[int]]:
    """
    Generate all valid consecutive slot blocks for a course with given credits.

    Slots 1..total_slots form ONE consecutive run — no break gap enforced
    (classes/lecturers handle their own break times).

    Args:
        credits: Number of credits (2-4)
        total_slots: Total number of slots per day (default 9)

    Returns:
        List of valid consecutive slot blocks

    Example:
        For 4 credits:
        [[1,2,3,4], [2,3,4,5], [3,4,5,6], [4,5,6,7], [5,6,7,8], [6,7,8,9]]
    """
    if credits < 2 or credits > 4:
        raise ValueError(f"Credits must be 2-4, got {credits}")

    slots = list(range(1, total_slots + 1))
    return [slots[s:s + credits]
            for s in range(len(slots) - credits + 1)]


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
