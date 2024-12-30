from typing import Annotated

import starlette.status
from fastapi import Depends, FastAPI, HTTPException

from fastapi_derive_responses import AutoDeriveResponsesAPIRoute

app = FastAPI()
app.router.route_class = AutoDeriveResponsesAPIRoute

statuses = {1: "admin", 2: "moderator", 3: "user"}  # user id X role
banlist = [4, 5, 6]  # banned user ids
ROLES = ("admin", "moderator", "user")


def auth_user(token: int) -> int:
    """
    Authenticate user

    :raises HTTPException: 401 Invalid token
     (less than 100)
    :raises HTTPException: 403 You are banned
    :raise HTTPException: 404 Your user not found

    :param token: User token
    :return: User id
    """
    if token < 100:
        raise HTTPException(401, detail="Invalid token")
    user_id = token - 100
    if user_id not in statuses:
        raise HTTPException(404, detail="Your user not found")
    if user_id in banlist:
        raise HTTPException(403, detail="You are banned")
    return user_id


@app.get("/")
def add_user(current_user_id: Annotated[int, Depends(auth_user)], new_user_id: int, user_role: str) -> None:
    if statuses[current_user_id] not in ("admin", "moderator"):
        raise HTTPException(403, detail="Only admins and moderators are allowed")
    if new_user_id in statuses:
        raise HTTPException(400, "User already exists")
    if user_role not in ROLES:
        raise HTTPException(status_code=starlette.status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    statuses[new_user_id] = user_role
    return None
