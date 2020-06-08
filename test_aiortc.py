from gevent.monkey import patch_all
import gevent

from test_aio_greenlet import spawn_greenlets

patch_all()


import aiogevent
import argparse
import asyncio
import logging
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling


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

            if isinstance(message, str) and message.startswith("ping"):
                # reply
                channel_send(channel, "pong" + message[4:])

    await consume_signaling(pc, signaling)


async def run_offer(pc, signaling):
    await signaling.connect()

    channel = pc.createDataChannel("chat")
    channel_log(channel, "-", "created by local party")

    async def send_pings():
        while True:
            channel_send(channel, "ping %d" % current_stamp())
            await asyncio.sleep(1)

    @channel.on("open")
    def on_open():
        asyncio.ensure_future(send_pings())

    @channel.on("message")
    def on_message(message):
        channel_log(channel, "<", message)

        if isinstance(message, str) and message.startswith("pong"):
            elapsed_ms = (current_stamp() - int(message[5:])) / 1000
            print(" RTT %.2f ms" % elapsed_ms)

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


def input_message():
    message = input("type in your message: ")


def main():
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")
    add_signaling_arguments(parser)

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    greenlets_gevent_sleep = spawn_greenlets(3)
    greenlets_gevent_sleep.append(gevent.spawn(aio_loop, args=args))
    gevent.joinall(greenlets_gevent_sleep)


if __name__ == "__main__":
    main()

