from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

@app.get("/")
def health():
    return "OK", 200

@app.post("/sms")
def sms_reply():
    body = (request.form.get("Body") or "").strip().upper()
    resp = MessagingResponse()
    if body == "NEXT":
        resp.message("Your next load: 4200 diesel / 3600 gas. Drop at Stroud.")
    elif body.startswith("ISSUE"):
        resp.message("Issue logged. Dispatch will review.")
    else:
        resp.message("Command not recognized. Reply NEXT or ISSUE.")
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
