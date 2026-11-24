from sqlalchemy.exc import IntegrityError

from orgbrain.db import SlackEvent


async def first_time(sessions, event_id: str) -> bool:
    try:
        async with sessions.begin() as s:
            s.add(SlackEvent(event_id=event_id))
        return True
    except IntegrityError:
        return False
