import uuid

import psycopg
from flask import Flask, flash, redirect, render_template, request, url_for
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


def dropdown_options(table):
    id_col, label = DROPDOWN[table]
    query = sql.SQL("SELECT {id}::text, " + label + " FROM {t} ORDER BY 2").format(
        id=sql.Identifier(id_col), t=sql.Identifier(table))
    with get_conn() as conn:
        return conn.execute(query).fetchall()


@app.route("/")
def home():
    return redirect(url_for("show_table", name="gym_user"))


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
