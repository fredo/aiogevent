from gevent.event import Event
from gevent.queue import Queue
from ping_pong_chat.aio_queue import AGQueue

received_event = Event()
leave_rooms_event = Event()
exit_event = Event()
output_message_queue = AGQueue()
input_message_queue = AGQueue()

matrix_to_aio_queue = AGQueue()
aio_to_matrix_queue = AGQueue()
sync_to_matrix_queue = Queue()

SERVER_URL = "https://transport.transport01.raiden.network"
