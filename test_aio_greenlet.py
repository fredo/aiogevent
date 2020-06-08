from gevent.monkey import patch_all
patch_all()

import aiogevent
import asyncio
import gevent

# -------------GEVENT----------------


def g_sleep(delay, id):
    gevent.sleep(delay)
    while True:
        print(f"greenlet {id}")
        gevent.sleep(5)


def spawn_greenlets(amount):
    greenlets = []
    delay = 1
    for i in range(amount):
        greenlets.append(gevent.spawn(g_sleep, delay, delay))
        delay += 2
    return greenlets


# -------------------ASYNCIO--------------


async def aio_sleep(delay, id):
    await asyncio.sleep(delay)
    while True:
        print(f"coroutine {id}")
        await asyncio.sleep(5)


def aio_loop(coroutines):

    asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())

    for coroutine in coroutines:
        asyncio.ensure_future(coroutine)

    loop = asyncio.get_event_loop()
    loop.run_forever()
    loop.close()


def main():

    greenlets_gevent_sleep = spawn_greenlets(3)
    greenlet_aio = gevent.spawn(aio_loop, coroutines=[aio_sleep(2,2), aio_sleep(4,4)])
    gevent.joinall(greenlets_gevent_sleep.append(greenlet_aio))


main()
