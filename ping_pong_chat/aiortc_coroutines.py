import asyncio
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE
from ping_pong_chat import aiogevent
from ping_pong_chat.communication import (
    output_message_queue,
    aio_to_matrix_queue,
    matrix_to_aio_queue,
    received_event,
    input_message_queue
)


def channel_log(channel, t, message):
    print("channel(%s) %s %s" % (channel.label, t, message))


def current_stamp():
    global time_start

    if time_start is None:
        time_start = time.time()
        return 0
    else:
        return int((time.time() - time_start) * 1000000)


async def run_caller_rtc(pc):

    channel = pc.createDataChannel("matrix-webRTC-ping-pong-chat")
    channel_log(channel, "-", "created by local party")

    async def send_message():
        while True:
            message = await output_message_queue.aget()
            channel.send(message)
            print("waiting for message...")

    @channel.on("open")
    def on_open():
        print()
        print()
        print("----------WebRTC Connection Established--------------")
        print()
        received_event.set()
        asyncio.ensure_future(send_message())

    @channel.on("message")
    async def on_message(message):
        await input_message_queue.aput(message)

    # send offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await aio_to_matrix_queue.aput(pc.localDescription)

    answer = await matrix_to_aio_queue.aget()
    rtc_description = RTCSessionDescription(answer['sdp'], answer['type'])
    await pc.setRemoteDescription(rtc_description)


async def run_callee_rtc(pc):

    @pc.on("datachannel")
    def on_datachannel(channel):
        #channel_log(channel, "-", "created by remote party")
        print()
        print()
        print("----------WebRTC Connection Established--------------")
        print()
        print("waiting for message...")

        @channel.on("message")
        async def on_message(message):
            channel_log(channel, "<", message)
            await input_message_queue.aput(message)

        async def send_message():
            while True:
                message = await output_message_queue.aget()
                channel.send(message)
                print("waiting for message...")

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


def aio_loop(args):
    pc = RTCPeerConnection()

    if args.role == "caller":
        coro = run_caller_rtc(pc)
    else:
        coro = run_callee_rtc(pc)

    asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    try:
        asyncio.ensure_future(coro)
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())