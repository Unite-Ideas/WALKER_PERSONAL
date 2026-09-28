#!/usr/bin/env python3
"""
Weekly "Plan of Attack" briefing for Jen.

Every Sunday evening this builds a clear, graphical week-ahead for both boys —
day by day, plus the memory verses / spelling / vocab we have, plus a look-ahead
at dated items coming in the next few weeks (book reports, field trips, region
quizzes, picture day) — and emails it (with a printable one-page PDF) to Jen,
CC'ing Sean.

Data sources:
  * each boy's Google Calendar (the dated backbone: tests, trips, recurring cadence)
  * the latest 2nd- and 4th-grade newsletters + their linked Google Docs
    (for the memory verse text and any spelling/vocab words)
Claude stitches those into a clean per-boy plan; we render + send it.

Auth/config come from environment + config/*.yaml (same as run.py). Style rule:
NO em dashes or en dashes anywhere in the output — use "to" for ranges.
"""

import base64
import os
import json
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import run  # reuse google_services(), _enrich_with_linked_docs(), load_yaml(), MODEL
from anthropic import Anthropic

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

# `or` (not a .get default): unset GitHub secrets arrive as empty strings.
TO = os.environ.get("WEEKLY_TO") or "jenniferwalker1108@gmail.com"
CC = os.environ.get("WEEKLY_CC") or "sean@uniteideas.com"
NO_DASH = str.maketrans({"—": ", ", "–": " to "})  # belt-and-suspenders


def _clean(s):
    return (s or "").translate(NO_DASH)


# ---------- gather ----------
def week_bounds(today):
    """Upcoming school week: Monday .. Friday of the week that starts next."""
    # If today is Sat/Sun, target the coming Mon; otherwise this week's Mon.
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:            # Sat/Sun -> next week
        monday = monday + timedelta(days=7)
    friday = monday + timedelta(days=4)
    return monday, friday


def cal_events(cal, calendar_id, start, end):
    resp = cal.events().list(
        calendarId=calendar_id, timeMin=start.isoformat() + "Z",
        timeMax=end.isoformat() + "Z", singleEvents=True, orderBy="startTime",
        maxResults=100,
    ).execute()
    out = []
    for ev in resp.get("items", []):
        if ev.get("status") == "cancelled":
            continue
        s = ev.get("start", {})
        date = s.get("date") or (s.get("dateTime", "")[:10])
        out.append({
            "date": date,
            "summary": (ev.get("summary") or "").replace("[reston]", "").replace("[hudson]", "").strip(" []"),
            "description": (ev.get("description") or "").split("\n\n—")[0].strip(),
        })
    return out


def recent_newsletter(gmail, sender):
    q = "from:%s newer_than:9d" % sender
    resp = gmail.users().messages().list(userId="me", q=q, maxResults=5).execute()
    best = ""
    for m in resp.get("messages", []):
        full = gmail.users().messages().get(userId="me", id=m["id"], format="full").execute()
        body = run._extract_body(full["payload"])[:12000]
        body += run._enrich_with_linked_docs(body)
        if len(body) > len(best):
            best = body
    return best[:16000]


# ---------- synthesize with Claude ----------
def build_plan(client, today, mon, fri, cals_by_child, newsletters):
    schema = (
        '{"week_label":"Mon date to Fri date, e.g. Sept 28 to Oct 2",'
        '"intro":"one short family-facing sentence about the week",'
        '"reston":[{"day":"Mon 9/28","text":"what is due / happening that day, or \\"Nothing scheduled\\""}],'
        '"hudson":[{"day":"Mon 9/28","text":"..."}],'
        '"verses":{"reston":{"ref":"","text":"","words":"actual spelling/vocab words if in the newsletter, else a short note"},'
        '"hudson":{"ref":"","text":"","words":"..."}},'
        '"horizon":[{"date":"Mon 10/5","who":"Reston|Hudson|Both","text":"dated item coming after this week"}]}'
    )
    system = (
        "You prepare a weekly school briefing for the Walker parents about their two boys, "
        "Reston (4th grade) and Hudson (2nd grade), and return STRICT JSON only. Use the "
        "calendars as the backbone for what is due each day, and the newsletters for the "
        "memory verse text and any spelling/vocabulary words. Cover Monday through Friday for "
        "each boy (use every weekday; 'Nothing scheduled' if truly empty). The horizon lists "
        "DATED items that fall AFTER this week (book reports, Bible book reports, field trips, "
        "region quizzes, picture day, quarter end) so nothing is a surprise; do not put next "
        "week's spelling or memory verse in the horizon (we do not know them yet). "
        "CRITICAL STYLE: never use em dashes or en dashes; write ranges as 'to'. Only state "
        "facts present in the calendars or newsletters; never invent dates or words."
    )
    user = (
        "TODAY: %s\nThis week: %s to %s\n\n"
        "RESTON CALENDAR:\n%s\n\nHUDSON CALENDAR:\n%s\n\n"
        "4TH GRADE NEWSLETTER (Reston):\n%s\n\n2ND GRADE NEWSLETTER (Hudson):\n%s\n\n"
        "Return ONLY JSON in this shape (no prose, no code fences):\n%s"
    ) % (
        today.strftime("%A, %Y-%m-%d"), mon.strftime("%b %-d"), fri.strftime("%b %-d"),
        json.dumps(cals_by_child["reston"], indent=1), json.dumps(cals_by_child["hudson"], indent=1),
        newsletters["reston"], newsletters["hudson"], schema,
    )
    msg = client.messages.create(
        model=run.MODEL, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


# ---------- render ----------
RESTON_C, HUDSON_C, NAVY_C, TEAL_C = "#d9791f", "#0e9e9c", "#24506b", "#0e7c7b"


def _rows_html(rows, bg, border, daycol="96px"):
    out = []
    for i, r in enumerate(rows):
        shade = bg if i % 2 == 0 else "#ffffff"
        out.append(
            '<tr style="background:%s;"><td style="padding:8px 10px;font-weight:700;width:%s;border:1px solid %s;vertical-align:top;">%s</td>'
            '<td style="padding:8px 10px;border:1px solid %s;">%s</td></tr>'
            % (shade, daycol, border, _clean(r.get("day") or r.get("date") or ""), border, _clean(r["text"]))
        )
    return "".join(out)


def render_html(d):
    def sec(title, color):
        return '<div style="font-size:16px;font-weight:800;color:%s;margin:0 0 6px;">%s</div>' % (color, title)

    def table(inner):
        return '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:20px;font-size:14px;">%s</table>' % inner

    v = d.get("verses", {})
    vr, vh = v.get("reston", {}), v.get("hudson", {})
    verse_rows = (
        '<tr><td style="padding:8px 10px;font-weight:800;color:%s;width:96px;border:1px solid #e6e7e2;vertical-align:top;">Reston</td>'
        '<td style="padding:8px 10px;border:1px solid #e6e7e2;"><strong>Memory verse</strong> (%s): "%s"<br><span style="color:#6b6f71;font-size:13px;"><strong>Spelling &amp; vocabulary:</strong> %s</span></td></tr>'
        '<tr style="background:#fafafa;"><td style="padding:8px 10px;font-weight:800;color:%s;border:1px solid #e6e7e2;vertical-align:top;">Hudson</td>'
        '<td style="padding:8px 10px;border:1px solid #e6e7e2;"><strong>Memory verse</strong> (%s): "%s"<br><span style="color:#6b6f71;font-size:13px;"><strong>Spelling:</strong> %s</span></td></tr>'
    ) % (RESTON_C, _clean(vr.get("ref", "")), _clean(vr.get("text", "")), _clean(vr.get("words", "")),
         HUDSON_C, _clean(vh.get("ref", "")), _clean(vh.get("text", "")), _clean(vh.get("words", "")))

    horizon = "".join(
        '<tr style="background:%s;"><td style="padding:8px 10px;font-weight:700;width:92px;border:1px solid #dde5ea;vertical-align:top;">%s</td>'
        '<td style="padding:8px 10px;border:1px solid #dde5ea;"><strong>%s:</strong> %s</td></tr>'
        % ("#eef2f5" if i % 2 == 0 else "#ffffff", _clean(h.get("date", "")), _clean(h.get("who", "")), _clean(h.get("text", "")))
        for i, h in enumerate(d.get("horizon", []))
    )

    return (
        '<div style="max-width:640px;margin:0 auto;padding:20px 16px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;color:#211f1b;">'
        '<div style="border-bottom:3px solid %s;padding-bottom:12px;margin-bottom:18px;">'
        '<div style="font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:%s;">Walker Family &middot; School Week</div>'
        '<div style="font-size:24px;font-weight:800;line-height:1.1;margin-top:3px;">Plan of Attack: %s</div></div>'
        '<p style="font-size:15px;line-height:1.5;margin:0 0 18px;">Hi Jen, %s</p>'
        '%s%s%s%s%s%s%s%s'
        '<p style="font-size:13px;line-height:1.5;color:#9a9e9d;margin:14px 0 0;border-top:1px solid #e6e7e2;padding-top:10px;">A printable one-page version is attached. Love you!</p>'
        '</div>'
    ) % (
        TEAL_C, TEAL_C, _clean(d.get("week_label", "")), _clean(d.get("intro", "")),
        sec("Reston &middot; 4th grade", RESTON_C), table(_rows_html(d.get("reston", []), "#faf3ea", "#eadfce")),
        sec("Hudson &middot; 2nd grade", HUDSON_C), table(_rows_html(d.get("hudson", []), "#eafafa", "#d7eeed")),
        sec("Verses &amp; words to practice", TEAL_C), table(verse_rows),
        (sec("On the horizon", NAVY_C) + table(horizon)) if horizon else "",
        "",  # placeholder to keep %-count aligned
    )


def render_pdf(d, path):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=19, leading=22,
                        textColor=colors.HexColor("#211f1b"), spaceAfter=2, alignment=TA_LEFT)
    eb = ParagraphStyle("eb", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.HexColor(TEAL_C), spaceAfter=1)
    intro = ParagraphStyle("in", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#6b6f71"), spaceAfter=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], fontSize=11.5, leading=13, spaceBefore=5, spaceAfter=3)
    cell = ParagraphStyle("cl", parent=styles["Normal"], fontSize=8.7, leading=11, textColor=colors.HexColor("#211f1b"))
    foot = ParagraphStyle("ft", parent=styles["Normal"], fontSize=7.6, leading=10, textColor=colors.HexColor("#6b6f71"))

    def P(t, s=cell):
        return Paragraph(_clean(t).replace("<br>", "<br/>"), s)

    def tbl(rows, bg, w0=0.95):
        data = [[P("<b>%s</b>" % (r.get("day") or r.get("date") or "")), P(r["text"])] for r in rows]
        t = Table(data, colWidths=[w0 * inch, (6.5 - w0) * inch])
        st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e6e7e2")),
              ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
              ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7)]
        for i in range(len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(bg)))
        t.setStyle(TableStyle(st))
        return t

    v = d.get("verses", {})
    vr, vh = v.get("reston", {}), v.get("hudson", {})
    verse_rows = [
        {"day": "Reston", "text": '<b>Memory verse</b> (%s): “%s”<br/><font color="#6b6f71"><b>Spelling &amp; vocabulary:</b> %s</font>'
         % (vr.get("ref", ""), vr.get("text", ""), vr.get("words", ""))},
        {"day": "Hudson", "text": '<b>Memory verse</b> (%s): “%s”<br/><font color="#6b6f71"><b>Spelling:</b> %s</font>'
         % (vh.get("ref", ""), vh.get("text", ""), vh.get("words", ""))},
    ]

    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.45 * inch, bottomMargin=0.45 * inch)
    E = [P("WALKER FAMILY &middot; SCHOOL WEEK", eb), P("Plan of Attack: " + d.get("week_label", ""), h1),
         P(d.get("intro", ""), intro)]
    E.append(P('<font color="%s">&#9679;</font> <b>Reston &middot; 4th grade</b>' % RESTON_C, sec))
    E.append(tbl(d.get("reston", []), "#faf3ea")); E.append(Spacer(1, 8))
    E.append(P('<font color="%s">&#9679;</font> <b>Hudson &middot; 2nd grade</b>' % HUDSON_C, sec))
    E.append(tbl(d.get("hudson", []), "#eafafa")); E.append(Spacer(1, 8))
    E.append(P('<font color="%s">&#9679;</font> <b>Verses &amp; words to practice</b>' % TEAL_C, sec))
    E.append(tbl(verse_rows, "#f2faf9")); E.append(Spacer(1, 8))
    if d.get("horizon"):
        E.append(P('<font color="%s">&#9679;</font> <b>On the horizon</b>' % NAVY_C, sec))
        E.append(tbl([{"day": h.get("date", ""), "text": "<b>%s:</b> %s" % (h.get("who", ""), h.get("text", ""))}
                      for h in d["horizon"]], "#eef2f5"))
    doc.build(E)


# ---------- send ----------
def send(gmail, subject, html, pdf_path):
    msg = MIMEMultipart("mixed")
    msg["To"] = TO
    if CC:
        msg["Cc"] = CC
    msg["Subject"] = _clean(subject)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Your weekly school briefing is attached and shown below.", "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)
    with open(pdf_path, "rb") as f:
        att = MIMEApplication(f.read(), _subtype="pdf")
    att.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
    msg.attach(att)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


def main():
    calendars_cfg = run.load_yaml("calendars.yaml")
    cals = {name: c["id"] for name, c in calendars_cfg["calendars"].items() if c.get("id") and c["id"] != "TODO"}
    gmail, cal = run.google_services()
    today = datetime.now()
    mon, fri = week_bounds(today)
    horizon_end = mon + timedelta(days=28)
    win_start = datetime(mon.year, mon.month, mon.day)

    cals_by_child = {
        "reston": cal_events(cal, cals["Reston"], win_start, datetime(horizon_end.year, horizon_end.month, horizon_end.day)),
        "hudson": cal_events(cal, cals["Hudson"], win_start, datetime(horizon_end.year, horizon_end.month, horizon_end.day)),
    }
    newsletters = {
        "reston": recent_newsletter(gmail, "rflatness@newcovenant.net"),
        "hudson": recent_newsletter(gmail, "cl2b@newcovenant.net"),
    }

    client = Anthropic()
    plan = build_plan(client, today, mon, fri, cals_by_child, newsletters)

    html = render_html(plan)
    import tempfile
    pdf_path = os.path.join(tempfile.gettempdir(), "jen_week.pdf")
    render_pdf(plan, pdf_path)
    subject = "Walker School Week: " + plan.get("week_label", mon.strftime("%b %-d"))
    send(gmail, subject, html, pdf_path)
    print("Sent weekly briefing to %s (cc %s): %s" % (TO, CC, subject))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FATAL: %s" % e, file=sys.stderr)
        sys.exit(1)
