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