from .naive import NaiveAllocator

ALLOCATORS = {
    NaiveAllocator.name: NaiveAllocator,
}


def get(name: str):
    try:
        return ALLOCATORS[name]()
    except KeyError:
        raise ValueError(f"unknown ALLOCATOR {name!r}; choose from {sorted(ALLOCATORS)}") from None
