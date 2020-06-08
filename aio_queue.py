import asyncio

import aiogevent
import gevent
from gevent.queue import Queue


asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())


def make_wrapped_greenlet(target, *args, **kwargs):
    glet = gevent.Greenlet(target, *args, **kwargs)
    wrapped_glet = aiogevent.wrap_greenlet(glet)
    glet.start()
    return wrapped_glet


class AGQueue(Queue):
    async def aget(self):
        return await make_wrapped_greenlet(self.get)

    async def aput(self, thing):
        await make_wrapped_greenlet(self.put, thing)


async def print_dummy():
    while True:
        print(1)
        await asyncio.sleep(.2)


async def aconsumer(queue: AGQueue):
    while True:
        i = await queue.aget()
        print(f"Got {i}, {type(i)}")
        if i == 0:
            break
        if isinstance(i, int):
            print(f"Putting x {i}")
            await queue.aput(f"x {i}")
            print(f"Done putting 'x {i}'")
    print("Stop")
    asyncio.get_event_loop().stop()


def producer(queue: AGQueue):
    for i in range(10, -1, -1):
        print(f"Put: {i}")
        queue.put(i)
        gevent.sleep(1)


def run_aioloop():
    loop = asyncio.get_event_loop()
    loop.run_forever()
    loop.close()


def main():
    aioloop_glet = gevent.spawn(run_aioloop)
    queue = AGQueue()
    asyncio.ensure_future(aconsumer(queue))
    asyncio.ensure_future(print_dummy())
    producer_glet = gevent.spawn(producer, queue)
    gevent.joinall([aioloop_glet, producer_glet])


if __name__ == "__main__":
    main()