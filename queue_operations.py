
class Queue:
    def __init__(self):
        self.items = []

    def is_empty(self):
        return len(self.items) == 0

    def enqueue(self, item):
        self.items.append(item)
        print(f"Enqueued: {item}. Queue: {self.items}")

    def dequeue(self):
        if self.is_empty():
            print("Queue is empty, cannot dequeue.")
            return None
        item = self.items.pop(0)
        print(f"Dequeued: {item}. Queue: {self.items}")
        return item

    def peek(self):
        if self.is_empty():
            print("Queue is empty, no front item.")
            return None
        print(f"Front item: {self.items[0]}")
        return self.items[0]

    def size(self):
        current_size = len(self.items)
        print(f"Queue size: {current_size}")
        return current_size

# Example Usage:
if __name__ == "__main__":
    my_queue = Queue()

    my_queue.size()
    my_queue.is_empty()

    my_queue.enqueue(10)
    my_queue.enqueue(20)
    my_queue.enqueue(30)

    my_queue.peek()
    my_queue.size()

    my_queue.dequeue()
    my_queue.peek()
    my_queue.dequeue()
    my_queue.dequeue()

    my_queue.is_empty()
    my_queue.dequeue()
