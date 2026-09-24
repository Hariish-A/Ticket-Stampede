from .naive import NaiveAllocator
from .skiplocked import SkipLockedAllocator

ALLOCATORS = {
    NaiveAllocator.name: NaiveAllocator,
    SkipLockedAllocator.name: SkipLockedAllocator,
}


def get(name: str):
    try:
        return ALLOCATORS[name]()
    except KeyError:
        raise ValueError(f"unknown ALLOCATOR {name!r}; choose from {sorted(ALLOCATORS)}") from None
