"""
Human-like delay simulation tool.

Provides realistic response delays to simulate human typing/response times.
"""

import random
import time
import asyncio
from typing import Optional, Callable


class HumanLikeDelay:
    """Simulate human-like response delays."""
    
    # Typing speed: characters per minute
    TYPING_SPEED_SLOW = 150    # ~2.5 chars/sec
    TYPING_SPEED_NORMAL = 300  # ~5 chars/sec
    TYPING_SPEED_FAST = 450    # ~7.5 chars/sec
    
    # Base response delays in seconds
    BASE_DELAY_MIN = 1.0
    BASE_DELAY_MAX = 3.0
    
    def __init__(self, typing_speed: str = "normal"):
        """
        Initialize delay simulator.
        
        Args:
            typing_speed: "slow", "normal", or "fast"
        """
        speed_map = {
            "slow": self.TYPING_SPEED_SLOW,
            "normal": self.TYPING_SPEED_NORMAL,
            "fast": self.TYPING_SPEED_FAST
        }
        self.chars_per_minute = speed_map.get(typing_speed, self.TYPING_SPEED_NORMAL)
        self.chars_per_second = self.chars_per_minute / 60.0
    
    def calculate_typing_delay(self, text_length: int) -> float:
        """
        Calculate typing delay based on text length.
        
        Args:
            text_length: Number of characters to "type"
            
        Returns:
            Delay in seconds
        """
        base_delay = text_length / self.chars_per_second
        # Add randomness (±20%)
        variation = random.uniform(0.8, 1.2)
        return base_delay * variation
    
    def get_response_delay(self, min_seconds: Optional[float] = None,
                          max_seconds: Optional[float] = None) -> float:
        """
        Get a random response delay.
        
        Args:
            min_seconds: Minimum delay (default: 1.0)
            max_seconds: Maximum delay (default: 3.0)
            
        Returns:
            Random delay in seconds
        """
        min_sec = min_seconds if min_seconds is not None else self.BASE_DELAY_MIN
        max_sec = max_seconds if max_seconds is not None else self.BASE_DELAY_MAX
        return random.uniform(min_sec, max_sec)
    
    def delay(self, seconds: Optional[float] = None):
        """
        Synchronous delay.
        
        Args:
            seconds: Delay duration (random 1-3s if not specified)
        """
        delay_time = seconds if seconds is not None else self.get_response_delay()
        time.sleep(delay_time)
    
    async def delay_async(self, seconds: Optional[float] = None):
        """
        Asynchronous delay.
        
        Args:
            seconds: Delay duration (random 1-3s if not specified)
        """
        delay_time = seconds if seconds is not None else self.get_response_delay()
        await asyncio.sleep(delay_time)
    
    def simulate_typing(self, text: str, on_progress: Optional[Callable[[str], None]] = None):
        """
        Simulate typing with realistic delays.
        
        Args:
            text: Text being "typed"
            on_progress: Optional callback called with partial text
        """
        delay_per_char = 1.0 / self.chars_per_second
        
        for i, char in enumerate(text):
            time.sleep(delay_per_char * random.uniform(0.8, 1.3))
            if on_progress:
                on_progress(text[:i + 1])
    
    async def simulate_typing_async(self, text: str,
                                    on_progress: Optional[Callable[[str], None]] = None):
        """
        Async simulate typing with realistic delays.
        
        Args:
            text: Text being "typed"
            on_progress: Optional callback called with partial text
        """
        delay_per_char = 1.0 / self.chars_per_second
        
        for i, char in enumerate(text):
            await asyncio.sleep(delay_per_char * random.uniform(0.8, 1.3))
            if on_progress:
                on_progress(text[:i + 1])


# Convenience functions
def delay(seconds: Optional[float] = None):
    """Simple delay function (1-3 seconds if not specified)."""
    simulator = HumanLikeDelay()
    simulator.delay(seconds)


async def delay_async(seconds: Optional[float] = None):
    """Simple async delay function (1-3 seconds if not specified)."""
    simulator = HumanLikeDelay()
    await simulator.delay_async(seconds)


def with_delay(min_seconds: float = 1.0, max_seconds: float = 3.0):
    """Decorator to add delay before function execution."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay_time = random.uniform(min_seconds, max_seconds)
            time.sleep(delay_time)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_typing_delay(typing_speed: str = "normal"):
    """Decorator to simulate typing delay based on response length."""
    simulator = HumanLikeDelay(typing_speed)
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, str):
                delay_time = simulator.calculate_typing_delay(len(result))
                time.sleep(delay_time)
            return result
        return wrapper
    return decorator


# Example usage
if __name__ == "__main__":
    print("Testing human-like delays...")
    
    simulator = HumanLikeDelay("normal")
    
    # Test 1: Simple delay
    print("\n1. Testing simple delay (1-3 seconds)...")
    simulator.delay()
    print("   Done!")
    
    # Test 2: Typing delay calculation
    test_text = "Hello, this is a test message!"
    delay_time = simulator.calculate_typing_delay(len(test_text))
    print(f"\n2. Typing delay for {len(test_text)} chars: {delay_time:.2f}s")
    
    # Test 3: Response delay
    response_delay = simulator.get_response_delay()
    print(f"\n3. Random response delay: {response_delay:.2f}s")
    
    print("\nAll tests completed!")
