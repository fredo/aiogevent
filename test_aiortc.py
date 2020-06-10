from gevent.monkey import patch_all
from gevent.queue import Queue
from matrix_client.errors import MatrixRequestError

patch_all()
from gevent import greenlet
from gevent.event import Event

import gevent
from raiden.network.transport.matrix import login, make_client
from raiden.network.transport.matrix.client import GMatrixHttpApi, GMatrixClient
from raiden.utils.signer import LocalSigner

from aio_queue import AGQueue
from test_aio_greenlet import spawn_greenlets




import aiogevent
import argparse
import asyncio
import logging
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling

from matrix_client.client import MatrixHttpApi


received_event = Event()
leave_rooms_event = Event()
exit_event = Event()
input_queue = AGQueue()
received_queue = AGQueue()

matrix_to_aio_queue = AGQueue()
aio_to_matrix_queue = AGQueue()

SERVER_URL= "https://transport.transport01.raiden.network"

sync_to_matrix_queue = Queue()

def channel_log(channel, t, message):
    print("channel(%s) %s %s" % (channel.label, t, message))


def channel_send(channel, message):
    channel_log(channel, ">", message)
    channel.send(message)


async def consume_signaling(pc, signaling):
    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            await pc.addIceCandidate(obj)
        elif obj is BYE:
            print("Exiting")
            break


time_start = None




def current_stamp():
    global time_start

    if time_start is None:
        time_start = time.time()
        return 0
    else:
        return int((time.time() - time_start) * 1000000)


async def run_answer(pc, signaling):
    await signaling.connect()



    @pc.on("datachannel")
    def on_datachannel(channel):
        channel_log(channel, "-", "created by remote party")
        print()
        print()
        print("----------WebRTC Connection Established--------------")
        print()

        @channel.on("message")
        async def on_message(message):
            channel_log(channel, "<", message)
            await received_queue.aput(message)

        async def send_message():
            while True:
                message = await input_queue.aget()
                channel_send(channel, message)

        asyncio.ensure_future(send_message())

    obj = await matrix_to_aio_queue.aget()
    obj = RTCSessionDescription(obj['sdp'], obj['type'])

    if isinstance(obj, RTCSessionDescription):
        await pc.setRemoteDescription(obj)

        if obj.type == "offer":
            # send answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await aio_to_matrix_queue.aput(pc.localDescription)

    elif isinstance(obj, RTCIceCandidate):
        await pc.addIceCandidate(obj)
    elif obj is BYE:
        print("Exiting")




async def run_offer(pc, signaling):
    await signaling.connect()

    channel = pc.createDataChannel("chat")
    channel_log(channel, "-", "created by local party")

    async def send_message():
        while True:
            message = await input_queue.aget()
            channel_send(channel, message)

    @channel.on("open")
    def on_open():
        print()
        print()
        print("----------WebRTC Connection Established--------------")
        print()
        asyncio.ensure_future(send_message())

    @channel.on("message")
    async def on_message(message):

        channel_log(channel, "<", message)
        await received_queue.aput(message)


    # send offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    from pprint import pprint

    pprint(offer)
    pprint(pc.localDescription)

    await aio_to_matrix_queue.aput(pc.localDescription)

    answer = await matrix_to_aio_queue.aget()
    rtc_description = RTCSessionDescription(answer['sdp'], answer['type'])
    await pc.setRemoteDescription(rtc_description)
    #await signaling.send(pc.localDescription)
    #await consume_signaling(pc, signaling)


def aio_loop(args):
    signaling = create_signaling(args)

    pc = RTCPeerConnection()

    if args.role == "offer":
        coro = run_offer(pc, signaling)
    else:
        coro = run_answer(pc, signaling)

    asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    try:
        asyncio.ensure_future(coro)
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
        loop.run_until_complete(signaling.close())


def input_message(queue, role):

    while True:
        received_event.wait()
        received_event.clear()
        message = f"Message of {role}"
        gevent.sleep(1)
        queue.put(message)


def print_receive(queue):

    while True:
        received_message = queue.get()
        received_event.set()



def send_offer(client, room_id, offer):
    call_id = "12345"
    version = 0
    lifetime = 60000

    print(room_id)

    offer_message = {
        "sdp": offer.sdp,
        "type": "offer"

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
        print(client.rooms.values())
        for room in list(client.rooms.values()):
            print(f"left_room: {room.room_id}")
            room.leave()
        exit_event.set()

    if args.role == "offer":
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
    partner_user_id = f"@{partner_address}:transport.transport01.raiden.network"
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

def _setup_client(key_number):

    private_key = format(key_number, ">032").encode()
    signer = LocalSigner(private_key)
    client = make_client(None, None, [SERVER_URL])
    login(client, signer)
    return client


def run_sync_loop(client: GMatrixClient):

    sync_token = None

    while True:

        response = client.api.sync(since=sync_token)
        sync_token = response["next_batch"]
        if response:

            for room_id, invite_room in response["rooms"]["invite"].items():

                try:
                    print(f"joining room: {room_id}")
                    client.join_room(room_id)
                except MatrixRequestError:
                    room_to_leave = client._mkroom(room_id)
                    room_to_leave.leave()





            for room_id, sync_room in response["rooms"]["join"].items():
                if room_id not in client.rooms:
                    client._mkroom(room_id)

                room = client.rooms[room_id]

                for event in sync_room["state"]["events"]:
                    event["room_id"] = room_id
                    room._process_state_event(event)
                for event in sync_room["timeline"]["events"]:
                    event["room_id"] = room_id
                    room._put_event(event)

                call_events = list()
                call_events.append(
                    (
                        room,
                        [
                            message
                            for message in sync_room["timeline"]["events"]
                            if message["type"] in ["m.call.invite", "m.call.answer", "m.call.candidates"]
                        ],
                    )
                )
                handle_call_events(client, call_events)


def handle_call_events(client, events):

    user_id = client.user_id

    for room, call_events in events:
        for call_event in call_events:
            if user_id == call_event["sender"]:
                continue

            if call_event["type"] == "m.call.invite":
                print("Received Offer via MATRIX")
                offer = call_event["content"]["offer"]
                matrix_to_aio_queue.put(offer)
            if call_event["type"] == "m.call.answer":
                print("Received Answer via MATRIX")
                answer = call_event["content"]["answer"]
                matrix_to_aio_queue.put(answer)


def main():


    try:
        parser = argparse.ArgumentParser(description="Data channels ping/pong")
        parser.add_argument("role", choices=["offer", "answer"])
        parser.add_argument("--verbose", "-v", action="count")
        add_signaling_arguments(parser)

        args = parser.parse_args()

        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)

        greenlet_input = gevent.spawn(input_message, queue=input_queue, role=args.role)
        greenlet_received = gevent.spawn(print_receive, queue=received_queue)
        greenlet_matrix = gevent.spawn(run_matrix_client, args=args)
        greenlet_aio = gevent.spawn(aio_loop, args=args)

        if args.role == "offer":
            received_event.set()
        gevent.joinall([greenlet_aio, greenlet_matrix])
    except KeyboardInterrupt:
        leave_rooms_event.set()
        exit_event.wait()



if __name__ == "__main__":
    main()

