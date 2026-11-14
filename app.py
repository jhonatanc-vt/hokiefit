import os
import uuid
from functools import wraps

import psycopg
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from psycopg import sql
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_conn

app = Flask(__name__)
# The secret key signs the login cookie. It lives in .env so it is not on GitHub.
app.secret_key = os.getenv("SECRET_KEY") or "dev-only-change-me"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # other sites can't submit the admin forms as a logged-in user

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

SQL_USER_LOGIN = """
SELECT u.user_id, u.email, u.role, l.password_hash
FROM gym_user u
JOIN user_login l ON l.user_id = u.user_id
WHERE lower(u.email) = lower(%(email)s);   -- emails are not case-sensitive
"""

SQL_UPDATE_LAST_LOGIN = """
UPDATE user_login
SET last_login_at = now(), updated_at = now()
WHERE user_id = %(user_id)s;
"""

SQL_USER_ROLE = """
SELECT role FROM gym_user WHERE user_id = %(user_id)s;
"""

SQL_ADMIN_USERS = """
SELECT u.user_id, u.first_name, u.last_name, u.email, u.role,
       l.user_id IS NOT NULL AS has_login,
       l.last_login_at
FROM gym_user u
LEFT JOIN user_login l ON l.user_id = u.user_id
ORDER BY u.last_name, u.first_name;
"""

SQL_CREATE_ADMIN = """
INSERT INTO gym_user (first_name, last_name, email, phone_number, role)
VALUES (%(first_name)s, %(last_name)s, %(email)s, %(phone_number)s, 'staff')
RETURNING user_id;
"""

# Also creates the login if this user doesn't have one yet
SQL_EMAIL_TAKEN = """
SELECT 1 FROM gym_user WHERE lower(email) = lower(%(email)s);
"""

# New members sign up as regular gym users
SQL_CREATE_MEMBER = """
INSERT INTO gym_user (first_name, last_name, email, phone_number, role)
VALUES (%(first_name)s, %(last_name)s, %(email)s, %(phone_number)s, 'gym_user')
RETURNING user_id, email, role;
"""

SQL_MY_ACCOUNT = """
SELECT u.first_name, u.last_name, u.email, u.phone_number, u.role, u.date_joined,
       l.password_hash, l.last_login_at
FROM gym_user u
JOIN user_login l ON l.user_id = u.user_id
WHERE u.user_id = %(user_id)s;
"""

SQL_SET_PASSWORD = """
INSERT INTO user_login (user_id, password_hash)
VALUES (%(user_id)s, %(password_hash)s)
ON CONFLICT (user_id) DO UPDATE
SET password_hash = EXCLUDED.password_hash, updated_at = now();
"""

SQL_USER_LOGIN = """
SELECT u.user_id, u.email, u.role, l.password_hash
FROM gym_user u
JOIN user_login l ON l.user_id = u.user_id
WHERE u.email = %(email)s;
"""

SQL_UPDATE_LAST_LOGIN = """
UPDATE user_login
SET last_login_at = now(), updated_at = now()
WHERE user_id = %(user_id)s;
"""

SQL_USER_ROLE = """
SELECT role FROM gym_user WHERE user_id = %(user_id)s;
"""

SQL_ADMIN_USERS = """
SELECT u.user_id, u.first_name, u.last_name, u.email, u.role,
       l.user_id IS NOT NULL AS has_login,
       l.last_login_at
FROM gym_user u
LEFT JOIN user_login l ON l.user_id = u.user_id
ORDER BY u.last_name, u.first_name;
"""

SQL_CREATE_ADMIN = """
INSERT INTO gym_user (first_name, last_name, email, phone_number, role)
VALUES (%(first_name)s, %(last_name)s, %(email)s, %(phone_number)s, 'staff')
RETURNING user_id;
"""

# Also creates the login if this user doesn't have one yet
SQL_SET_PASSWORD = """
INSERT INTO user_login (user_id, password_hash)
VALUES (%(user_id)s, %(password_hash)s)
ON CONFLICT (user_id) DO UPDATE
SET password_hash = EXCLUDED.password_hash, updated_at = now();
"""

# One row per activity. signed_up counts its registrations; is_registered says
# whether the logged-in user is one of them.
SQL_ACTIVITIES = """
SELECT
    a.activity_id,
    a.name,
    a.description,
    a.start_time,
    a.end_time,
    a.capacity,
    g.name                                              AS group_name,
    l.name                                              AS location_name,
    l.address,
    COUNT(r.user_id)                                    AS signed_up,
    COALESCE(BOOL_OR(r.user_id = %(user_id)s::uuid), false) AS is_registered,
    a.start_time <= (now() AT TIME ZONE %(tz)s)         AS has_started
FROM activity a
JOIN gym_group g ON g.group_id = a.group_id
JOIN location l  ON l.location_id = a.location_id
LEFT JOIN registration r ON r.activity_id = a.activity_id
GROUP BY a.activity_id, g.name, l.name, l.address
ORDER BY a.start_time DESC;
"""

# FOR UPDATE locks the activity row until commit, so two people can't both
# take the last spot.
SQL_ACTIVITY_FOR_REGISTER = """
SELECT
    a.capacity,
    a.start_time <= (now() AT TIME ZONE %(tz)s) AS has_started,
    (SELECT COUNT(*) FROM registration r WHERE r.activity_id = a.activity_id) AS signed_up
FROM activity a
WHERE a.activity_id = %(activity_id)s::uuid
FOR UPDATE;
"""

SQL_REGISTER = """
INSERT INTO registration (user_id, activity_id)
VALUES (%(user_id)s::uuid, %(activity_id)s::uuid)
ON CONFLICT DO NOTHING;
"""

SQL_UNREGISTER = """
DELETE FROM registration
WHERE user_id = %(user_id)s::uuid AND activity_id = %(activity_id)s::uuid;
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


@app.before_request
def require_login():
    # Everything needs a session except the login page and its static files
    if request.endpoint in ("login", "signup", "static") or "user_id" in session:
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Login required"), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("home"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(SQL_USER_LOGIN, {"email": email})
        user = cur.fetchone()

        # Same message for both failures, so the form doesn't reveal which emails exist
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html", email=email), 401

        conn.execute(SQL_UPDATE_LAST_LOGIN, {"user_id": user["user_id"]})

    session.clear()
    session["user_id"] = str(user["user_id"])
    session["email"] = user["email"]
    session["role"] = user["role"]  # only decides whether the nav shows Admin; see staff_required
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def staff_required(view):
    # Checks the database each time, so a role change applies straight away
    @wraps(view)
    def wrapped(*args, **kwargs):
        with get_conn() as conn:
            row = conn.execute(SQL_USER_ROLE, {"user_id": session["user_id"]}).fetchone()
        if row is None or row[0] != "staff":
            flash("Only staff can open that page.", "error")
            return redirect(url_for("show_locations"))
        return view(*args, **kwargs)
    return wrapped


MIN_PASSWORD_LENGTH = 8


def read_new_password():
    """Returns the submitted password, or None after flashing what's wrong with it."""
    password = request.form.get("password", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        return None
    if password != request.form.get("confirm_password", ""):
        flash("Passwords do not match.", "error")
        return None
    return password


@app.route("/admin")
@staff_required
def admin():
    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(SQL_ADMIN_USERS)
        users = cur.fetchall()
    return render_template("admin.html", users=users)


@app.post("/admin/create")
@staff_required
def admin_create():
    params = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone_number": request.form.get("phone_number", "").strip() or None,
    }
    if not (params["first_name"] and params["last_name"] and params["email"]):
        flash("First name, last name and email are required.", "error")
        return redirect(url_for("admin"))
    if email_taken(params["email"]):
        flash(f"A user with email {params['email']} already exists.", "error")
        return redirect(url_for("admin"))

    password = read_new_password()
    if password is None:
        return redirect(url_for("admin"))

    try:
        # One transaction, so a failure can't leave a user without a login
        with get_conn() as conn:
            user_id = conn.execute(SQL_CREATE_ADMIN, params).fetchone()[0]
            conn.execute(SQL_SET_PASSWORD, {"user_id": user_id,
                                            "password_hash": generate_password_hash(password)})
        flash(f"Created admin {params['email']}.", "ok")
    except psycopg.errors.UniqueViolation:
        flash(f"A user with email {params['email']} already exists.", "error")
    except psycopg.Error as e:
        flash(f"Create failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("admin"))


@app.post("/admin/password")
@staff_required
def admin_password():
    password = read_new_password()
    if password is None:
        return redirect(url_for("admin"))

    try:
        with get_conn() as conn:
            conn.execute(SQL_SET_PASSWORD, {"user_id": request.form.get("user_id", ""),
                                            "password_hash": generate_password_hash(password)})
        flash("Password updated.", "ok")
    except psycopg.Error as e:
        flash(f"Password change failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("admin"))


@app.route("/")
def home():
    # Staff land on the tables; everyone else lands on the locations page
    if session.get("role") == "staff":
        return redirect(url_for("show_table", name="gym_user"))
    return redirect(url_for("show_locations"))


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


@app.route("/activities")
def show_activities():
    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(SQL_ACTIVITIES, {"user_id": session["user_id"], "tz": GYM_TZ})
        activities = cur.fetchall()
    return render_template("activities.html", activities=activities)


@app.post("/activities/<uuid:activity_id>/register")
def register_activity(activity_id):
    params = {"user_id": session["user_id"], "activity_id": activity_id, "tz": GYM_TZ}
    try:
        with get_conn() as conn:
            cur = conn.cursor(row_factory=dict_row)
            activity = cur.execute(SQL_ACTIVITY_FOR_REGISTER, params).fetchone()
            if activity is None:
                flash("That activity no longer exists.", "error")
            elif activity["has_started"]:
                flash("That activity has already started.", "error")
            elif activity["signed_up"] >= activity["capacity"]:
                flash("That activity is full.", "error")
            elif conn.execute(SQL_REGISTER, params).rowcount == 0:
                flash("You are already registered for that activity.", "ok")
            else:
                flash("You are registered.", "ok")
    except psycopg.Error as e:
        flash(f"Registration failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("show_activities"))


@app.post("/activities/<uuid:activity_id>/unregister")
def unregister_activity(activity_id):
    try:
        with get_conn() as conn:
            conn.execute(SQL_UNREGISTER, {"user_id": session["user_id"], "activity_id": activity_id})
        flash("Your registration was cancelled.", "ok")
    except psycopg.Error as e:
        flash(f"Cancel failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
    return redirect(url_for("show_activities"))


@app.route("/table/<name>")
@staff_required
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
@staff_required
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
@staff_required
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


# ---------------------------------------------------------------------
# Sign up and "My account" (Jhonatan - Phase 3 checkpoint 2)
# ---------------------------------------------------------------------
def email_taken(email):
    with get_conn() as conn:
        return conn.execute(SQL_EMAIL_TAKEN, {"email": email}).fetchone() is not None


def start_session(user):
    session.clear()
    session["user_id"] = str(user["user_id"])
    session["email"] = user["email"]
    session["role"] = user["role"]


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("home"))
        return render_template("signup.html", form={})

    form = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone_number": request.form.get("phone_number", "").strip() or None,
    }
    if not (form["first_name"] and form["last_name"] and form["email"]):
        flash("First name, last name and email are required.", "error")
        return render_template("signup.html", form=form), 400
    password = read_new_password()
    if password is None:
        return render_template("signup.html", form=form), 400
    if email_taken(form["email"]):
        flash("An account with that email already exists. Try logging in.", "error")
        return render_template("signup.html", form=form), 400

    try:
        # One transaction: the gym_user row and its login are saved together or not at all
        with get_conn() as conn:
            cur = conn.cursor(row_factory=dict_row)
            user = cur.execute(SQL_CREATE_MEMBER, form).fetchone()
            cur.execute(SQL_SET_PASSWORD, {"user_id": user["user_id"],
                                           "password_hash": generate_password_hash(password)})
            cur.execute(SQL_UPDATE_LAST_LOGIN, {"user_id": user["user_id"]})
    except psycopg.Error as e:
        flash(f"Sign up failed: {e.diag.message_primary}. {e.diag.message_detail or ''}", "error")
        return render_template("signup.html", form=form), 400

    start_session(user)  # log them in straight away
    flash(f"Welcome to HokieFit, {form['first_name']}! Your account was created.", "ok")
    return redirect(url_for("home"))


@app.route("/account", methods=["GET", "POST"])
def account():
    with get_conn() as conn:
        cur = conn.cursor(row_factory=dict_row)
        me = cur.execute(SQL_MY_ACCOUNT, {"user_id": session["user_id"]}).fetchone()
    if me is None:  # the user or their login was deleted
        session.clear()
        flash("Your account no longer exists. Please log in again.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        # Users must type their current password to change it
        if not check_password_hash(me["password_hash"], request.form.get("current_password", "")):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("account"))
        password = read_new_password()
        if password is None:
            return redirect(url_for("account"))
        with get_conn() as conn:
            conn.execute(SQL_SET_PASSWORD, {"user_id": session["user_id"],
                                            "password_hash": generate_password_hash(password)})
        flash("Your password was changed.", "ok")
        return redirect(url_for("account"))

    return render_template("account.html", me=me)


if __name__ == "__main__":
    app.run(debug=True)
