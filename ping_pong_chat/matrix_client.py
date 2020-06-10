from matrix_client.errors import MatrixRequestError
from raiden.network.transport.matrix import make_client, login
from raiden.network.transport.matrix.client import GMatrixClient
from raiden.utils.signer import LocalSigner

from ping_pong_chat.communication import matrix_to_aio_queue, SERVER_URL


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
        for call_event in [call_event for call_event in call_events if user_id != call_event["sender"]]:
            if call_event["type"] == "m.call.invite":
                print("Received Offer via MATRIX")
                offer = call_event["content"]["offer"]
                matrix_to_aio_queue.put(offer)
            if call_event["type"] == "m.call.answer":
                print("Received Answer via MATRIX")
                answer = call_event["content"]["answer"]
                matrix_to_aio_queue.put(answer)
