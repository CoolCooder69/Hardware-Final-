import os, hmac
from flask import request, Response

def install(app):
    user = os.environ.get("FEEDER_USER", "admin")
    pw = os.environ.get("FEEDER_PASS")
    if not pw:
        return          # no password set -> open (home Wi-Fi only!)

    @app.before_request
    def check():
        a = request.authorization
        if (a and hmac.compare_digest(a.username or "", user)
                and hmac.compare_digest(a.password or "", pw)):
            return None
        return Response("Login required", 401,
                        {"WWW-Authenticate": 'Basic realm="Pet Feeder"'})
