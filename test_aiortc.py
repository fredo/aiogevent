from gevent.event import Event
from gevent.monkey import patch_all
import gevent

from aio_queue import AGQueue
from test_aio_greenlet import spawn_greenlets

patch_all()


import aiogevent
import argparse
import asyncio
import logging
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling


received_event = Event()
input_queue = AGQueue()
received_queue = AGQueue()

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

        @channel.on("message")
        def on_message(message):
            channel_log(channel, "<", message)
            received_queue.aput(message)

        async def send_message():
            while True:
                message = await input_queue.aget()
                channel_send(channel, message)

        asyncio.ensure_future(send_message())

    await consume_signaling(pc, signaling)


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
        asyncio.ensure_future(send_message())

    @channel.on("message")
    async def on_message(message):

        channel_log(channel, "<", message)
        await received_queue.aput(message)


    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)
    await consume_signaling(pc, signaling)


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
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
        loop.run_until_complete(signaling.close())


def input_message(queue):

    while True:
        received_event.wait()
        received_event.clear()
        message = input("type in your message: ")
        queue.put(message)


def print_receive(queue):

    while True:

        print("waiting for incoming message")
        received_message = queue.get()
        print(f"received: {received_message}")
        received_event.set()




def main():
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")
    add_signaling_arguments(parser)

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)


    greenlet_input = gevent.spawn(input_message, queue=input_queue)
    greenlet_received = gevent.spawn(print_receive, queue=input_queue)

    greenlets_gevent_sleep = spawn_greenlets(3)
    greenlets_gevent_sleep.append(gevent.spawn(aio_loop, args=args))

    if args.role == "offer":
        received_event.set()
    gevent.joinall(greenlets_gevent_sleep)


if __name__ == "__main__":
    main()

