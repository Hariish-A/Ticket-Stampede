from .counter import CounterAllocator
from .naive import NaiveAllocator
from .serializable import SerializableAllocator
from .skiplocked import SkipLockedAllocator

ALLOCATORS = {
    cls.name: cls for cls in (NaiveAllocator, SkipLockedAllocator, CounterAllocator, SerializableAllocator)
}


def get(name: str):
    try:
        return ALLOCATORS[name]()
    except KeyError:
        raise ValueError(f"unknown ALLOCATOR {name!r}; choose from {sorted(ALLOCATORS)}") from None
