from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
import os
import re

app = Flask(__name__)

@app.get("/")
def health():
    return "OK", 200


# ---- stub data you'd replace with your DB/Google Sheet/Airtable ----
DRIVERS = {
    # phone_number: driver_id
    "+11234567890": {"driver_id": "phil", "current_load": "28137"},
}
LOADS = {
    "28137": {
        "planned_diesel": 4200,
        "planned_gas": 3600,
        "status": "PLANNED",
        "notes": "Stroud Construction - use south gate",
    }
}

HELP_TEXT = (
    "Commands:\n"
    "NEXT\n"
    "START <load>\n"
    "DELIVERED <load> diesel=<gal> gas=<gal> trailer=<cap>\n"
    "COMPLETE <load>\n"
    "ISSUE <truck> <free text>\n"
    "HELP"
)

def upsert_delivery(load_id, diesel, gas, trailer_cap):
    # TODO: replace with Google Sheets/Airtable/TMS write
    load = LOADS.get(load_id, {"status": "UNKNOWN"})
    load["delivered_diesel"] = diesel
    load["delivered_gas"] = gas
    load["trailer_cap"] = trailer_cap
    load["status"] = "DELIVERED"
    LOADS[load_id] = load

def mark_status(load_id, status):
    if load_id not in LOADS:
        LOADS[load_id] = {}
    LOADS[load_id]["status"] = status

@app.route("/sms", methods=["POST"])
def sms_webhook():
    # Optional: verify Twilio signature for security
    # See https://www.twilio.com/docs/usage/security#validating-requests

    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()

    resp = MessagingResponse()
    msg = resp.message()

    # Safety: allow STOP/HELP compliance
    if body.upper() in ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"]:
        msg.body("You’re opted out. Reply START to opt back in.")
        return str(resp)
    if body.upper() in ["HELP", "INFO"]:
        msg.body(HELP_TEXT)
        return str(resp)

    driver = DRIVERS.get(from_number)
    if not driver:
        msg.body("Your number isn’t recognized. Reply HELP for commands or contact dispatch.")
        return str(resp)

    # Parse commands
    up = body.upper()

    # NEXT
    if up == "NEXT":
        load_id = driver.get("current_load")
        if not load_id or load_id not in LOADS:
            msg.body("No active load on file. Contact dispatch.")
            return str(resp)
        load = LOADS[load_id]
        msg.body(
            f"Load #{load_id}\n"
            f"- Planned: {load.get('planned_diesel',0)} diesel / {load.get('planned_gas',0)} gas\n"
            f"- Notes: {load.get('notes','')}\n"
            f"Reply START {load_id} when rolling."
        )
        return str(resp)

    # START <load>
    m = re.match(r"^START\s+(\d+)$", up)
    if m:
        load_id = m.group(1)
        mark_status(load_id, "IN_TRANSIT")
        msg.body(f"Load {load_id} marked IN_TRANSIT. Drive safe. Reply DELIVERED {load_id} ... when done.")
        return str(resp)

    # DELIVERED <load> diesel=#### gas=#### trailer=####
    m = re.match(
        r"^DELIVERED\s+(\d+)\s+.*?DIESEL\s*=\s*([0-9.]+)\s+.*?GAS\s*=\s*([0-9.]+)\s+.*?TRAILER\s*=\s*([0-9.]+)",
        up
    )
    if m:
        load_id = m.group(1)
        diesel = float(m.group(2))
        gas = float(m.group(3))
        trailer = float(m.group(4))

        # Simple validations
        planned_diesel = LOADS.get(load_id, {}).get("planned_diesel", 0.0)
        planned_gas = LOADS.get(load_id, {}).get("planned_gas", 0.0)
        planned_total = planned_diesel + planned_gas
        reported_total = diesel + gas

        warnings = []
        # Example tolerance check: ±0.5%
        tol = 0.005 * planned_total if planned_total else 999999
        if planned_total and abs(reported_total - planned_total) > tol:
            warnings.append(f"Totals off vs plan (reported {reported_total}, planned {planned_total}).")

        # (Add your compartment-size checks here if you store them)
        # e.g., max_compartment = trailer (simplified)
        if diesel > trailer or gas > trailer:
            warnings.append("Reported gallons exceed trailer compartment value provided.")

        upsert_delivery(load_id, diesel, gas, trailer)

        if warnings:
            msg.body(
                "Delivery recorded, but please recheck:\n- " + "\n- ".join(warnings) +
                f"\nReply COMPLETE {load_id} to finalize or re-send corrected DELIVERED."
            )
        else:
            msg.body(
                f"Delivery recorded for load {load_id}.\n"
                f"Diesel: {diesel} | Gas: {gas}\n"
                f"Reply COMPLETE {load_id} to finalize."
            )
        return str(resp)

    # COMPLETE <load>
    m = re.match(r"^COMPLETE\s+(\d+)$", up)
    if m:
        load_id = m.group(1)
        mark_status(load_id, "DELIVERED")
        msg.body(f"Load {load_id} closed out. Thank you.")
        return str(resp)

    # ISSUE <truck> <free text>
    m = re.match(r"^ISSUE\s+([A-Z0-9\-]+)\s+(.+)$", body, re.IGNORECASE)
    if m:
        truck = m.group(1)
        text = m.group(2)
        # TODO: write a maintenance ticket in your system/Sheet
        msg.body(f"Issue logged for truck {truck}: {text}\nDispatch will follow up.")
        return str(resp)

    msg.body("Didn’t catch that. Reply HELP for the command list.")
    return str(resp)

if __name__ == "__main__":
    # Run:  FLASK_APP=app.py flask run --port=5000
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
