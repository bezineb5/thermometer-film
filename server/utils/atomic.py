import queue
import threading


class AtomicThreadLocalQueuesList:
    """A thread-safe list of thread-local queues."""

    def __init__(self):
        self._list = []
        self._thread_local_queue = threading.local()
        self._lock = threading.Lock()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self) -> queue.SimpleQueue:
        new_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread_local_queue.queue = new_queue
        with self._lock:
            self._list.append(new_queue)
        return new_queue

    def release(self):
        with self._lock:
            self._list.remove(self._thread_local_queue.queue)
        del self._thread_local_queue.queue

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._list) == 0

    def broadcast(self, payload):
        with self._lock:
            for q in self._list:
                q.put(payload)


class AtomicRef:
    def __init__(self, value=None):
        self._value = value
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = value
