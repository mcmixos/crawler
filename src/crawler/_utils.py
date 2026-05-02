from collections import OrderedDict


class BoundedDict(OrderedDict):
    """OrderedDict with FIFO eviction once size exceeds max_size.

    Updates to an existing key keep the original position (do not refresh recency).
    Use this when you need to cap memory growth and oldest entries are safe to drop.
    """

    def __init__(self, max_size: int) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        super().__init__()
        self._max_size = max_size

    def __setitem__(self, key, value) -> None:
        if key not in self and len(self) >= self._max_size:
            self.popitem(last=False)
        super().__setitem__(key, value)
