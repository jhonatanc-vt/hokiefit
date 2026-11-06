import uuid

import psycopg
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from psycopg import sql
from psycopg.rows import dict_row

from db import get_conn

app = Flask(__name__)
app.secret_key = "cs4604-group 12"

TABLES = {
    "gym_user": {
        "pk": ["user_id"],
        "fields": [("first_name", "text"), ("last_name", "text"), ("email", "email"),
                   ("phone_number", "text"), ("date_joined", "date"), ("role", "text")],
    },
    "location": {
        "pk": ["location_id"],
        "fields": [("name", "text"), ("address", "text"), ("capacity", "number")],
    },
    "location_hours": {
        "pk": ["location_id", "day_of_week"],
        "fields": [("location_id", "fk:location"), ("day_of_week", "text"), ("open_time", "time"),
                   ("close_time", "time"), ("is_closed", "bool")],
    },
    "gym_group": {
        "pk": ["group_id"],
        "fields": [("instructor_id", "fk:gym_user"), ("name", "text"), ("description", "text"),
                   ("start_date", "date")],
    },
    "gym_group_membership": {
        "pk": ["group_id", "user_id"],
        "fields": [("group_id", "fk:gym_group"), ("user_id", "fk:gym_user"), ("joined_date", "date")],
    },
    "activity": {
        "pk": ["activity_id"],
        "fields": [("group_id", "fk:gym_group"), ("location_id", "fk:location"), ("name", "text"),
                   ("description", "text"), ("start_time", "datetime"), ("end_time", "datetime"),
                   ("capacity", "number")],
    },
    "registration": {
        "pk": ["user_id", "activity_id"],
        "fields": [("user_id", "fk:gym_user"), ("activity_id", "fk:activity"), ("registration_date", "date")],
    },
    "subscription": {
        "pk": ["subscription_id"],
        "fields": [("user_id", "fk:gym_user"), ("subscription_type", "text"), ("start_date", "date"),
                   ("end_date", "date"), ("status", "text"), ("price", "number")],
    },
    "session": {
        "pk": ["session_id"],
        "fields": [("user_id", "fk:gym_user"), ("location_id", "fk:location"), ("date", "date"),
                   ("check_in", "datetime"), ("check_out", "datetime"), ("is_active", "bool")],
    },
}

# How to show each table in a dropdown: (id column, label)
DROPDOWN = {
    "gym_user": ("user_id", "first_name || ' ' || last_name"),
    "location": ("location_id", "name"),
    "gym_group": ("group_id", "name"),
    "activity": ("activity_id", "name"),
}

GYM_TZ = "America/New_York"

DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
             "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}

SQL_LOCATIONS = """
SELECT
    l.location_id,
    l.name,
    l.address,
    l.capacity,
    COALESCE(occ.no_checked_in, 0)                                   AS no_checked_in,
    ROUND(100.0 * COALESCE(occ.no_checked_in, 0) / l.capacity, 1)    AS percent_full,
    h.open_time                                                      AS today_open_time,
    h.close_time                                                     AS today_close_time,
    COALESCE(h.is_closed, true)                                      AS closed_today,
    COALESCE(
        NOT h.is_closed
        AND n.ts::time >= h.open_time
        AND n.ts::time <  h.close_time,
        false
    )                                                                AS is_open_now
FROM location l
CROSS JOIN (SELECT now() AT TIME ZONE %(tz)s AS ts) n
LEFT JOIN (
    SELECT location_id, COUNT(*) AS no_checked_in
    FROM session
    WHERE is_active
    GROUP BY location_id
) occ ON occ.location_id = l.location_id
LEFT JOIN location_hours h
       ON h.location_id = l.location_id
      AND h.day_of_week = to_char(n.ts, 'dy')      -- 'mon'..'sun'
ORDER BY l.name;
"""

SQL_LOCATION_EXISTS = """
SELECT 1 FROM location WHERE location_id = %(location_id)s::uuid;
"""

SQL_LOCATION_HOURS = """
SELECT day_of_week, open_time, close_time, is_closed
FROM location_hours
WHERE location_id = %(location_id)s::uuid
ORDER BY array_position(
    ARRAY['mon','tue','wed','thu','fri','sat','sun']::varchar[],
    day_of_week
);
"""


def fetch_locations():
    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(SQL_LOCATIONS, {"tz": GYM_TZ})
        return cur.fetchall()


def format_hours(row):
    if row["is_closed"] or row["open_time"] is None or row["close_time"] is None:
        return "Closed"
    opens, closes = (t.strftime("%I:%M %p").lstrip("0") for t in (row["open_time"], row["close_time"]))
    return f"{opens} - {closes}"


def dropdown_options(table):
    id_col, label = DROPDOWN[table]
    query = sql.SQL("SELECT {id}::text, " + label + " FROM {t} ORDER BY 2").format(
        id=sql.Identifier(id_col), t=sql.Identifier(table))
    with get_conn() as conn:
        return conn.execute(query).fetchall()


@app.route("/")
def home():
    return redirect(url_for("show_table", name="gym_user"))


@app.route("/locations")
def show_locations():
    locations = fetch_locations()
    with get_conn() as conn:
        version = conn.execute("SHOW server_version").fetchone()[0].split(" ")[0]
    return render_template("locations.html", locations=locations, version=version)


@app.route("/api/locations/status")
def locations_status():
    return jsonify([
        {"location_id": str(loc["location_id"]),
         "percent_full": float(loc["percent_full"]),
         "is_open_now": loc["is_open_now"]}
        for loc in fetch_locations()
    ])


@app.route("/api/locations/<uuid:location_id>/hours")
def location_hours(location_id):
    params = {"location_id": location_id}
    with get_conn() as conn:
        if conn.execute(SQL_LOCATION_EXISTS, params).fetchone() is None:
            return jsonify(error="Unknown location"), 404
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(SQL_LOCATION_HOURS, params)
        rows = cur.fetchall()
    return jsonify([
        {"day": DAY_NAMES.get(row["day_of_week"], row["day_of_week"]), "hours": format_hours(row)}
        for row in rows
    ])


@app.route("/table/<name>")
def show_table(name):
    if name not in TABLES:
        return "Unknown table", 404
    table = TABLES[name]

    # Get the rows (SELECT)
    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(sql.SQL("SELECT * FROM {} LIMIT 300").format(sql.Identifier(name)))
        rows = cur.fetchall()
        columns = [c.name for c in cur.description]
        version = conn.execute("SHOW server_version").fetchone()[0].split(" ")[0]

    # Dropdown choices for foreign keys
    options = {}
    for field, ftype in table["fields"]:
        if ftype.startswith("fk:"):
            options[field] = dropdown_options(ftype[3:])

    return render_template("table.html", name=name, tables=TABLES, table=table,
                           rows=rows, columns=columns, options=options, version=version)


@app.post("/table/<name>/insert")
def insert_row(name):
    table = TABLES[name]
    cols, values = [], []

    # A single-column primary key gets a new UUID made here
    if len(table["pk"]) == 1 and table["pk"][0] not in [f for f, _ in table["fields"]]:
        cols.append(table["pk"][0])
        values.append(str(uuid.uuid4()))

    # Only send the fields that were filled in (blank ones use the database default)
    for field, _ in table["fields"]:
        value = request.form.get(field, "").strip()
        if value != "":
            cols.append(field)
            values.append(value)

    query = sql.SQL("INSERT INTO {t} ({c}) VALUES ({v})").format(
        t=sql.Identifier(name),
        c=sql.SQL(", ").join(map(sql.Identifier, cols)),
        v=sql.SQL(", ").join(sql.Placeholder() * len(cols)))
    try:
        with get_conn() as conn:
            conn.execute(query, values)
        flash(f"Inserted 1 row into {name}.", "ok")
    except psycopg.Error as e:
        flash(f"Insert failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("show_table", name=name))

@app.post("/table/<name>/delete")
def delete_row(name):
    table = TABLES[name]
    where = sql.SQL(" AND ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in table["pk"])
    values = [request.form[c] for c in table["pk"]]
    try:
        with get_conn() as conn:
            cur = conn.execute(sql.SQL("DELETE FROM {} WHERE ").format(sql.Identifier(name)) + where, values)
        flash(f"Deleted {cur.rowcount} row from {name}.", "ok")
    except psycopg.Error as e:
        # Usually: another table still uses this row (foreign key)
        flash(f"Delete failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("show_table", name=name))


if __name__ == "__main__":
    app.run(debug=True)
