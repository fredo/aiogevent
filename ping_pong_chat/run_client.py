from gevent.monkey import patch_all
patch_all()

import logging
import sys
import argparse
import gevent

from ping_pong_chat.communication import (
    received_event,
    leave_rooms_event,
    exit_event,
    aio_to_matrix_queue,
    output_message_queue,
    input_message_queue, SERVER_URL
)
from ping_pong_chat.matrix_client import run_sync_loop, _setup_client
from urllib.parse import urlparse
from raiden.utils.signer import LocalSigner
from aiortc.contrib.signaling import add_signaling_arguments
from ping_pong_chat.aiortc_coroutines import aio_loop

time_start = None


def ginput( prompt ):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    gevent.select.select([sys.stdin], [], [])
    return sys.stdin.readline()


def input_message(queue):
    while True:
        received_event.wait()
        received_event.clear()
        message = ginput("type your message:\t\t")
        queue.put(message)


def print_receive(queue):
    while True:
        message_received = queue.get()
        print(f"Message received:\t\t{message_received}")
        received_event.set()


def send_offer(client, room_id, offer):
    call_id = "12345"
    version = 0
    lifetime = 60000

    print(room_id)

    offer_message = {
        "sdp": offer.sdp,
        "type": offer.type
    }

    content = {
        "call_id": call_id,
        "version": version,
        "lifetime": lifetime,
        "offer": offer_message
    }

    client.api.send_message_event(room_id, "m.call.invite", content)


def send_answer(client, room_id, answer):
    call_id = "12345"
    version = 0

    answer_message = {
        "sdp": answer.sdp,
        "type": answer.type
    }

    content = {
        "call_id": call_id,
        "version": version,
        "answer": answer_message
    }
    client.api.send_message_event(room_id, "m.call.answer", content)


def run_matrix_client(args):

    def leave_rooms(client):
        leave_rooms_event.wait()
        for room in list(client.rooms.values()):
            print(f"leaving room: {room.room_id}")
            room.leave()
        exit_event.set()

    if args.role == "caller":
        client = _setup_client(0)
        gevent.spawn(leave_rooms, client)
        run_matrix_caller(client)

    else:
        client = _setup_client(1)
        gevent.spawn(leave_rooms, client)
        run_matrix_callee(client)


def run_matrix_caller(client):

    gevent.spawn(run_sync_loop, client=client)

    # create room
    partner_private_key = format(1, ">032").encode()
    partner_signer = LocalSigner(partner_private_key)
    partner_address = partner_signer.address_hex
    partner_user_id = f"@{partner_address}:{urlparse(SERVER_URL).netloc}"
    room = client.create_room(invitees=[partner_user_id])
    room_id = room.room_id
    # send offer
    offer = aio_to_matrix_queue.get()
    send_offer(client, room_id, offer)


def run_matrix_callee(client):
    gevent.spawn(run_sync_loop, client=client)

    while not client.rooms:
        gevent.sleep(0.1)

    room_id = list(client.rooms.keys())[0]
    answer = aio_to_matrix_queue.get()
    send_answer(client, room_id, answer)


def run_client():

    try:
        parser = argparse.ArgumentParser(description="Data channels ping/pong")
        parser.add_argument("role", choices=["caller", "callee"])
        parser.add_argument("--verbose", "-v", action="count")
        add_signaling_arguments(parser)

        args = parser.parse_args()

        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)

        gevent.spawn(input_message, queue=output_message_queue)
        gevent.spawn(print_receive, queue=input_message_queue)
        greenlet_matrix = gevent.spawn(run_matrix_client, args=args)
        greenlet_aio = gevent.spawn(aio_loop, args=args)

        gevent.joinall([greenlet_aio, greenlet_matrix])

    except KeyboardInterrupt:
        leave_rooms_event.set()
        exit_event.wait()


