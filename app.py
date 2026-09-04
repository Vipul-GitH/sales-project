from datetime import date, datetime, timedelta
import calendar
import json
import os
from pathlib import Path
from uuid import uuid4
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
import csv
from io import StringIO
from werkzeug.utils import secure_filename
from database import execute, fetch_all, fetch_one

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("REFERRAL_SECRET_KEY", "local-development-only-change-me")
UPLOAD_DIR = Path(app.root_path) / "static" / "uploads" / "demo"

TODAY = date.today()
ADDITIONAL_SALES_USER_NAMES = {"dr vishu bhasin", "dr vipul bhasin"}


def database_users():
    try:
        rows = fetch_all("SELECT id, name, role, status, designation FROM users ORDER BY name")
        return [{"id": r["id"], "name": r["name"], "role": r["role"],
                 "initials": "".join(x[0] for x in r["name"].split()[:2]), "active": r["status"] == "Active",
                 "designation": r["designation"] or ""} for r in rows]
    except Exception:
        return []


def sales_suggestion_users(users=None):
    """Active Marketing users plus the two explicitly approved administrators."""
    users = users if users is not None else database_users()
    return [
        user for user in users
        if user["active"] and (
            user["designation"].strip().lower() == "marketing"
            or user["name"].strip().lower() in ADDITIONAL_SALES_USER_NAMES
        )
    ]


def task_snapshot(task_id):
    return fetch_one("""SELECT t.title, COALESCE(a.entity_name,'Internal task') AS account,
        t.task_type, t.details, assigner.name AS assigned_by, assignee.name AS assigned_to,
        t.due_at, t.original_due_at, t.revised_due_at, t.priority, t.status,
        t.completed_at, t.completion_notes, t.cancelled_reason
        FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id
        JOIN users assigner ON assigner.id=t.assigned_by_id
        JOIN users assignee ON assignee.id=t.assigned_to_id WHERE t.id=%s""", (task_id,))


def activity_snapshot(activity_id):
    return fetch_one("""SELECT a.activity_type, ac.entity_name AS account, a.interaction_at,
        a.notes, u.name AS entered_by, a.entered_at, a.next_action,
        a.delayed_entry_reason, a.no_action_reason, a.edited_at
        FROM activities a JOIN accounts ac ON ac.id=a.account_id
        JOIN users u ON u.id=a.entered_by_id WHERE a.id=%s""", (activity_id,))


def audit_json(values):
    return json.dumps(dict(values), default=str, ensure_ascii=False) if values else None


def log_task_audit(task_id, action, old_values=None, new_values=None):
    execute("INSERT INTO task_audit_logs (task_id,action,performed_by_id,old_values,new_values) VALUES (%s,%s,%s,%s,%s)",
            (task_id, action, session["user_id"], audit_json(old_values), audit_json(new_values)))


def log_activity_audit(activity_id, action, old_values=None, new_values=None):
    execute("INSERT INTO activity_audit_logs (activity_id,action,performed_by_id,old_values,new_values) VALUES (%s,%s,%s,%s,%s)",
            (activity_id, action, session["user_id"], audit_json(old_values), audit_json(new_values)))


def prepare_audit_rows(rows):
    labels = {"assigned_to": "Assigned to", "assigned_by": "Assigned by", "due_at": "Due date",
              "task_type": "Task type", "completion_notes": "Completion notes",
              "cancelled_reason": "Cancellation reason", "interaction_at": "Activity date/time",
              "entered_by": "Entered by", "next_action": "Next action", "no_action_reason": "No-action reason",
              "delayed_entry_reason": "Delayed-entry reason"}
    prepared = []
    for row in rows:
        old = json.loads(row.get("old_values") or "{}")
        new = json.loads(row.get("new_values") or "{}")
        changes = []
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changes.append({"label": labels.get(key, key.replace("_", " ").title()),
                                "old": old.get(key), "new": new.get(key)})
        item = dict(row)
        item["changes"] = changes
        prepared.append(item)
    return prepared


def database_accounts():
    try:
        rows = fetch_all("""SELECT a.id, a.entity_name, a.account_type, a.entity_category, a.area,
            u.name AS owner, a.lead_temperature, a.lifecycle_status, a.next_follow_up_date,
            MAX(ac.interaction_at) AS last_activity
            FROM accounts a JOIN users u ON u.id=a.owner_id
            LEFT JOIN activities ac ON ac.account_id=a.id
            GROUP BY a.id, u.name ORDER BY a.id""")
        return [{"id": r["id"], "name": r["entity_name"], "type": r["account_type"], "category": r["entity_category"],
                 "area": r["area"], "owner": r["owner"], "temp": r["lead_temperature"] or "", "status": r["lifecycle_status"],
                 "followup": r["next_follow_up_date"].strftime("%d %b") if r["next_follow_up_date"] else "—",
                 "last": r["last_activity"].strftime("%d %b") if r["last_activity"] else "No activity"} for r in rows]
    except Exception:
        return []


def database_tasks():
    try:
        rows = fetch_all("""SELECT t.*, a.entity_name AS account, assignee.name AS assignee,
            assigner.name AS assigned_by FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id
            JOIN users assignee ON assignee.id=t.assigned_to_id JOIN users assigner ON assigner.id=t.assigned_by_id
            ORDER BY t.due_at""")
        output = []
        for r in rows:
            overdue = max(0, (TODAY - r["due_at"].date()).days) if r["status"] == "Pending" else 0
            output.append({"id": r["id"], "title": r["title"], "account": r["account"] or "Internal task", "type": r["task_type"],
                           "assignee": r["assignee"], "assigned_by": r["assigned_by"], "due": r["due_at"].strftime("%d %b, %I:%M %p"),
                           "priority": r["priority"], "status": r["status"], "overdue": overdue,
                           "original": r["original_due_at"].strftime("%d %b") if r["revised_due_at"] else None,
                           "recurring": (r["recurrence_type"] + " · " + (r["recurrence_value"] or "")) if r["recurrence_type"] else None})
        return output
    except Exception:
        return []

def selected_filters():
    return {key: request.args.get(key, "").strip() for key in ("q", "owner", "status", "type")}

def return_to(default_endpoint="my_tasks"):
    target = request.form.get("next") or request.args.get("next")
    return redirect(target) if target and target.startswith("/") else redirect(url_for(default_endpoint))

def is_admin():
    return role() == "Admin"

def has_management_scope():
    return role() in {"Admin", "Team Leader"}

def owns_account(account_id):
    account = fetch_one("SELECT owner_id FROM accounts WHERE id=%s", (account_id,))
    return bool(account and (has_management_scope() or account["owner_id"] == session["user_id"]))

def manages_task(task_id):
    task = fetch_one("SELECT assigned_by_id,assigned_to_id FROM tasks WHERE id=%s", (task_id,))
    return bool(task and (has_management_scope() or session["user_id"] in (task["assigned_by_id"], task["assigned_to_id"])))

def can_work_on_account(account_id):
    if has_management_scope():
        return True
    row = fetch_one("""SELECT a.id FROM accounts a
        WHERE a.id=%s AND (a.owner_id=%s OR EXISTS (
            SELECT 1 FROM tasks t WHERE t.account_id=a.id AND (t.assigned_by_id=%s OR t.assigned_to_id=%s)
        ))""", (account_id, session["user_id"], session["user_id"], session["user_id"]))
    return bool(row)

def can_access_activity(activity_id):
    if has_management_scope():
        return True
    row = fetch_one("""SELECT ac.id FROM activities ac JOIN accounts a ON a.id=ac.account_id
        WHERE ac.id=%s AND (ac.entered_by_id=%s OR a.owner_id=%s OR EXISTS (
            SELECT 1 FROM tasks t WHERE t.account_id=a.id AND (t.assigned_by_id=%s OR t.assigned_to_id=%s)
        ))""", (activity_id, session["user_id"], session["user_id"], session["user_id"], session["user_id"]))
    return bool(row)

def deny_access():
    flash("You do not have permission to access that record.", "danger")
    return redirect(url_for("dashboard"))


@app.before_request
def require_login():
    allowed = {"login", "forgot_password", "static"}
    if request.endpoint not in allowed and "user_id" not in session:
        return redirect(url_for("login"))

@app.before_request
def authorize_record_access():
    if "user_id" not in session:
        return None
    endpoint = request.endpoint or ""
    if endpoint == "users_page" and not is_admin():
        return deny_access()
    if endpoint == "archived_accounts" and not is_admin():
        return deny_access()
    if has_management_scope():
        return None
    account_endpoints = {"account_detail", "account_form", "update_contact", "archive_contact", "archive_file"}
    if endpoint in account_endpoints and request.view_args and request.view_args.get("account_id") and not owns_account(request.view_args["account_id"]):
        return deny_access()
    task_endpoints = {"task_detail", "task_form", "complete_task", "cancel_task", "record_scheduled_activity"}
    task_id = (request.view_args or {}).get("task_id")
    if endpoint in task_endpoints and task_id and not manages_task(task_id):
        return deny_access()
    if endpoint in {"activity_form", "activity_detail"} and request.view_args and request.view_args.get("activity_id"):
        if not can_access_activity(request.view_args["activity_id"]):
            return deny_access()

def role(): return session.get("role", "Executive")
def nav_role_url(endpoint, **values):
    # Older templates use the former shared task-list endpoint. Keep those
    # links safe while all task views use explicit endpoints.
    if endpoint == "task_list":
        endpoint = "my_tasks"
        values.pop("task_id", None)
    return url_for(endpoint, role=role(), **values)

def save_attachments(account_id=None, activity_id=None, task_id=None):
    """Store optional activity/task uploads while keeping the app's simple file table."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for uploaded in request.files.getlist("attachments"):
        if uploaded and uploaded.filename:
            original = secure_filename(uploaded.filename)
            stored = f"{uuid4().hex}_{original}"
            uploaded.save(UPLOAD_DIR / stored)
            execute("INSERT INTO files (account_id,activity_id,task_id,original_name,stored_name,caption,uploaded_by_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (account_id, activity_id, task_id, original, stored, request.form.get("file_caption") or None, session["user_id"]))

@app.context_processor
def inject_globals():
    users = database_users()
    suggestion_users = sales_suggestion_users(users)
    accounts = database_accounts()
    if "user_id" in session and not has_management_scope():
        accounts = [account for account in accounts if can_work_on_account(account["id"])]
    return dict(role=role(), users=suggestion_users, marketing_users=suggestion_users, suggestion_users=suggestion_users, all_users=users, accounts=accounts, tasks=database_tasks(), today=TODAY.strftime("%d %b %Y"), today_iso=date.today().isoformat(), nav_role_url=nav_role_url)

@app.route("/")
def index(): return redirect(url_for("dashboard", role="Executive"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        candidates = fetch_all("SELECT id, name, role, status, dob FROM users WHERE name=%s", (request.form.get("login_id", "").strip(),))
        entered_password = request.form.get("password", "").strip()
        user = next((candidate for candidate in candidates if (candidate["dob"] or "").replace("/", "") == entered_password), None)
        if user and user["status"] == "Active":
            session.clear()
            session.update(user_id=user["id"], user_name=user["name"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid user ID or password.", "danger")
    return render_template("auth/login.html", standalone=True, login_users=sales_suggestion_users())

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    if request.method == "POST": flash("If this were live, a reset link would be sent to the registered address.", "success")
    return render_template("auth/forgot_password.html", standalone=True)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    all_tasks = database_tasks()
    open_tasks = [t for t in all_tasks if t["status"] == "Pending" and (has_management_scope() or session.get("user_name") in (t["assignee"], t["assigned_by"]))]
    accounts_for_user = [a for a in database_accounts() if has_management_scope() or a["owner"] == session.get("user_name")]
    overdue = sum(1 for t in open_tasks if t["overdue"])
    visits_today = sum(1 for t in open_tasks if "Visit" in t["type"] and t["due"].startswith(TODAY.strftime("%d %b")))
    metrics = [(len(open_tasks), "Open tasks", "teal"), (overdue, "Overdue", "red"), (visits_today, "Today's visits", "mint"), (sum(1 for a in accounts_for_user if a["temp"] == "Hot"), "Hot leads", "amber"), (len(accounts_for_user), "Accounts", "blue"), (sum(1 for u in database_users() if u["active"]), "Active users", "grey")]
    return render_template("dashboard/index.html", open_tasks=open_tasks, hot_accounts=[a for a in accounts_for_user if a["temp"] == "Hot"], metrics=metrics)

@app.route("/accounts")
def account_list():
    filters = selected_filters()
    accounts_for_view = database_accounts()
    if not has_management_scope():
        accounts_for_view = [a for a in accounts_for_view if a["owner"] == session.get("user_name")]
    query = filters["q"].lower()
    if query:
        accounts_for_view = [a for a in accounts_for_view if query in " ".join(str(a.get(k, "")) for k in ("name", "area", "category", "owner")).lower()]
    if filters["owner"]:
        accounts_for_view = [a for a in accounts_for_view if a["owner"] == filters["owner"]]
    if filters["status"]:
        accounts_for_view = [a for a in accounts_for_view if a["status"] == filters["status"]]
    return render_template("accounts/list.html", accounts_for_view=accounts_for_view, filters=filters)

@app.route("/accounts/<int:account_id>")
def account_detail(account_id):
    account = fetch_one("""SELECT a.*, u.name AS owner FROM accounts a JOIN users u ON u.id=a.owner_id WHERE a.id=%s""", (account_id,))
    if not account:
        flash("Account not found.", "danger"); return redirect(url_for("account_list"))
    contacts = fetch_all("SELECT * FROM contacts WHERE account_id=%s AND is_archived=0 ORDER BY is_primary DESC,id", (account_id,))
    activities = fetch_all("SELECT activity_type,interaction_at,notes,entered_at FROM activities WHERE account_id=%s AND is_archived=0 ORDER BY interaction_at DESC", (account_id,))
    tasks_for_account = fetch_all("SELECT title,task_type,due_at,priority,status FROM tasks WHERE account_id=%s ORDER BY due_at", (account_id,))
    files = fetch_all("SELECT id,original_name,stored_name,caption,uploaded_at FROM files WHERE account_id=%s AND is_archived=0 ORDER BY uploaded_at DESC", (account_id,))
    ownership = fetch_all("""SELECT p.name previous_owner,n.name new_owner,c.name changed_by,h.reason,h.changed_at FROM ownership_history h JOIN users p ON p.id=h.previous_owner_id JOIN users n ON n.id=h.new_owner_id JOIN users c ON c.id=h.changed_by_id WHERE h.account_id=%s ORDER BY h.changed_at DESC""", (account_id,))
    return render_template("accounts/detail.html", account=account, contacts=contacts, activities=activities, tasks_for_account=tasks_for_account, files=files, ownership=ownership)

@app.route("/accounts/add", methods=["GET","POST"])
@app.route("/accounts/<int:account_id>/edit", methods=["GET","POST"])
def account_form(account_id=None):
    if request.method == "POST":
        entity_name = request.form.get("entity_name", "").strip()
        owner_id = request.form.get("owner_id") or session.get("user_id")
        if not has_management_scope():
            owner_id = session["user_id"]
        if not entity_name or not owner_id:
            flash("Account name and owner are required.", "danger")
        else:
            values = (request.form.get("account_type"), entity_name, request.form.get("entity_category"), request.form.get("area"), request.form.get("lead_source"), owner_id, request.form.get("lead_temperature") if request.form.get("account_type") == "New Lead" else None, request.form.get("next_follow_up_date") or None, request.form.get("notes"))
            if account_id:
                previous = fetch_one("SELECT owner_id FROM accounts WHERE id=%s", (account_id,))
                execute("UPDATE accounts SET account_type=%s,entity_name=%s,entity_category=%s,area=%s,lead_source=%s,owner_id=%s,lead_temperature=%s,next_follow_up_date=%s,notes=%s WHERE id=%s", values + (account_id,))
                if previous and int(previous["owner_id"]) != int(owner_id):
                    execute("INSERT INTO ownership_history (account_id,previous_owner_id,new_owner_id,changed_by_id,reason) VALUES (%s,%s,%s,%s,%s)",
                            (account_id, previous["owner_id"], owner_id, session["user_id"], request.form.get("ownership_reason", "").strip() or "Owner updated from account edit"))
            else:
                account_id = execute("""INSERT INTO accounts (account_type,entity_name,entity_category,area,lead_source,owner_id,lead_temperature,lifecycle_status,next_follow_up_date,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,'Active',%s,%s)""", values)
            for name, designation, mobile in zip(request.form.getlist("contact_name"), request.form.getlist("designation"), request.form.getlist("mobile")):
                if name.strip():
                    execute("INSERT INTO contacts (account_id,full_name,designation,mobile,is_primary) VALUES (%s,%s,%s,%s,%s)",
                            (account_id, name.strip(), designation or None, mobile or "Not supplied", not bool(fetch_all("SELECT id FROM contacts WHERE account_id=%s AND is_archived=0", (account_id,)))))
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            for uploaded in request.files.getlist("account_files"):
                if uploaded and uploaded.filename:
                    original = secure_filename(uploaded.filename)
                    stored = f"{uuid4().hex}_{original}"
                    uploaded.save(UPLOAD_DIR / stored)
                    execute("INSERT INTO files (account_id,original_name,stored_name,caption,uploaded_by_id) VALUES (%s,%s,%s,%s,%s)",
                            (account_id, original, stored, request.form.get("file_caption") or None, session["user_id"]))
            flash("Account saved successfully.", "success")
            return redirect(url_for("account_detail", account_id=account_id))
    account = fetch_one("SELECT * FROM accounts WHERE id=%s", (account_id,)) if account_id else None
    account_contacts = fetch_all("SELECT * FROM contacts WHERE account_id=%s AND is_archived=0 ORDER BY is_primary DESC,id", (account_id,)) if account_id else []
    account_files = fetch_all("SELECT id,original_name,stored_name,caption,uploaded_at FROM files WHERE account_id=%s AND is_archived=0 ORDER BY uploaded_at DESC", (account_id,)) if account_id else []
    return render_template("accounts/form.html", account=account, account_contacts=account_contacts, account_files=account_files)


@app.post("/accounts/<int:account_id>/contacts/<int:contact_id>/update")
def update_contact(account_id, contact_id):
    contact = fetch_one("SELECT id FROM contacts WHERE id=%s AND account_id=%s AND is_archived=0", (contact_id, account_id))
    name = request.form.get("full_name", "").strip()
    mobile = request.form.get("mobile", "").strip()
    if not contact or not name or not mobile:
        flash("Contact name and mobile number are required.", "danger")
    else:
        execute("UPDATE contacts SET full_name=%s, designation=%s, mobile=%s, alternate_mobile=%s, email=%s, is_primary=%s WHERE id=%s",
                (name, request.form.get("designation") or None, mobile, request.form.get("alternate_mobile") or None,
                 request.form.get("email") or None, bool(request.form.get("is_primary")), contact_id))
        if request.form.get("is_primary"):
            execute("UPDATE contacts SET is_primary=0 WHERE account_id=%s AND id<>%s AND is_archived=0", (account_id, contact_id))
        flash("Contact updated.", "success")
    return redirect(url_for("account_form", account_id=account_id))


@app.post("/accounts/<int:account_id>/contacts/<int:contact_id>/archive")
def archive_contact(account_id, contact_id):
    reason = request.form.get("archive_reason", "").strip()
    if not reason:
        flash("Please provide a reason before archiving a contact.", "danger")
    else:
        execute("UPDATE contacts SET is_archived=1, archive_reason=%s, archived_at=NOW() WHERE id=%s AND account_id=%s", (reason, contact_id, account_id))
        flash("Contact archived. It has not been permanently deleted.", "success")
    return redirect(url_for("account_form", account_id=account_id))


@app.post("/accounts/<int:account_id>/files/<int:file_id>/archive")
def archive_file(account_id, file_id):
    reason = request.form.get("archive_reason", "").strip()
    if not reason:
        flash("Please provide a reason before archiving a file.", "danger")
    else:
        execute("UPDATE files SET is_archived=1, archive_reason=%s, archived_at=NOW() WHERE id=%s AND account_id=%s", (reason, file_id, account_id))
        flash("File archived. The original file remains retained for audit.", "success")
    return redirect(url_for("account_form", account_id=account_id))

@app.route("/accounts/archived")
def archived_accounts(): return render_template("accounts/archived.html")

@app.route("/activities")
def activities():
    scheduled_scope, scheduled_params = ("", ()) if has_management_scope() else (
        " AND (t.assigned_to_id=%s OR t.assigned_by_id=%s OR a.owner_id=%s)",
        (session["user_id"], session["user_id"], session["user_id"]),
    )
    activity_scope, activity_params = ("", ()) if has_management_scope() else (
        """ AND (ac.entered_by_id=%s OR a.owner_id=%s OR EXISTS (
            SELECT 1 FROM tasks wt WHERE wt.account_id=a.id AND (wt.assigned_by_id=%s OR wt.assigned_to_id=%s)
        ))""",
        (session["user_id"], session["user_id"], session["user_id"], session["user_id"]),
    )
    scheduled = fetch_all(f"""SELECT t.id,t.title,t.task_type,t.due_at,t.recurrence_type,a.entity_name,u.name AS assignee
        FROM tasks t JOIN accounts a ON a.id=t.account_id JOIN users u ON u.id=t.assigned_to_id
        WHERE t.status='Pending' AND t.task_type LIKE 'Scheduled %%' {scheduled_scope} ORDER BY t.due_at""", scheduled_params)
    activity_rows = fetch_all(f"""SELECT ac.id,ac.activity_type,ac.interaction_at,ac.notes,ac.next_action,
        a.entity_name,u.name AS entered_by FROM activities ac JOIN accounts a ON a.id=ac.account_id
        JOIN users u ON u.id=ac.entered_by_id WHERE ac.is_archived=0 {activity_scope} ORDER BY ac.interaction_at DESC""", activity_params)
    filters = selected_filters()
    query = filters["q"].lower()
    if query:
        activity_rows = [a for a in activity_rows if query in " ".join(str(a.get(k, "")) for k in ("entity_name", "activity_type", "notes", "entered_by")).lower()]
    if filters["owner"]:
        activity_rows = [a for a in activity_rows if a["entered_by"] == filters["owner"]]
    if filters["type"]:
        activity_rows = [a for a in activity_rows if a["activity_type"] == filters["type"]]
    return render_template("activities/list.html", scheduled=scheduled, activity_rows=activity_rows, filters=filters)


@app.route("/activities/<int:activity_id>")
def activity_detail(activity_id):
    activity = fetch_one("""SELECT a.*, ac.entity_name, u.name AS entered_by
        FROM activities a JOIN accounts ac ON ac.id=a.account_id
        JOIN users u ON u.id=a.entered_by_id WHERE a.id=%s""", (activity_id,))
    if not activity:
        flash("Activity not found.", "danger")
        return redirect(url_for("activities"))
    audit_rows = fetch_all("""SELECT l.*,u.name AS performed_by FROM activity_audit_logs l
        JOIN users u ON u.id=l.performed_by_id WHERE l.activity_id=%s ORDER BY l.created_at DESC,l.id DESC""", (activity_id,))
    return render_template("activities/detail.html", activity=activity, audit_rows=prepare_audit_rows(audit_rows))

@app.route("/activities/add", methods=["GET","POST"])
@app.route("/activities/<int:activity_id>/edit", methods=["GET","POST"])
def activity_form(activity_id=None):
    if request.method == "POST":
        account_id = request.form.get("account_id")
        notes = request.form.get("notes", "").strip()
        next_action = request.form.get("next_action")
        creates_task = next_action == "Create follow-up task" and not activity_id
        if account_id and not can_work_on_account(int(account_id)):
            return deny_access()
        if not account_id or not notes:
            flash("Account and meaningful notes are required.", "danger")
        elif creates_task and not request.form.get("task_due_date"):
            flash("Choose a due date for the next-action task.", "danger")
        else:
            when = f"{request.form.get('activity_date')} {request.form.get('activity_time') or '00:00'}"
            if activity_id:
                old_activity = activity_snapshot(activity_id)
                execute("UPDATE activities SET account_id=%s,activity_type=%s,interaction_at=%s,notes=%s,next_action=%s,delayed_entry_reason=%s,no_action_reason=%s,edited_at=NOW() WHERE id=%s",
                    (account_id, request.form.get("activity_type"), when, notes, next_action, request.form.get("delayed_reason") or None, request.form.get("action_reason") or None, activity_id))
                log_activity_audit(activity_id, "Updated", old_activity, activity_snapshot(activity_id))
                flash("Activity updated successfully.", "success")
            else:
                activity_id = execute("INSERT INTO activities (account_id,activity_type,interaction_at,notes,entered_by_id,next_action,delayed_entry_reason,no_action_reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (account_id, request.form.get("activity_type"), when, notes, session["user_id"], next_action, request.form.get("delayed_reason") or None, request.form.get("action_reason") or None))
                log_activity_audit(activity_id, "Created", None, activity_snapshot(activity_id))
                save_attachments(account_id=account_id, activity_id=activity_id)
            if creates_task:
                due_at = f"{request.form.get('task_due_date')} {request.form.get('task_due_time') or '00:00'}"
                created_task_id = execute("INSERT INTO tasks (title,account_id,task_type,details,assigned_by_id,assigned_to_id,due_at,original_due_at,priority,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending')",
                        (request.form.get("task_title", "").strip() or "Follow-up required", account_id, "Follow-up Call",
                         request.form.get("task_details") or notes, session["user_id"], request.form.get("assigned_to_id") or session["user_id"], due_at, due_at, request.form.get("task_priority", "Normal")))
                log_task_audit(created_task_id, "Created", None, task_snapshot(created_task_id))
                flash("Activity saved and next-action task created.", "success")
            elif not activity_id:
                flash("Activity saved successfully.", "success")
            return redirect(url_for("activities"))
    activity = fetch_one("SELECT * FROM activities WHERE id=%s", (activity_id,)) if activity_id else None
    return render_template("activities/form.html", activity_id=activity_id, activity=activity)


@app.route("/activities/schedule", methods=["GET", "POST"])
def schedule_activity():
    if request.method == "POST":
        account_id = request.form.get("account_id")
        scheduled_for = request.form.get("scheduled_for")
        title = request.form.get("title", "").strip()
        recurrence = request.form.get("recurrence_type", "One time")
        if not account_id or not scheduled_for or not title:
            flash("Account, activity title and scheduled date are required.", "danger")
        elif recurrence == "Weekly" and not request.form.get("weekday"):
            flash("Select a weekday for a weekly activity.", "danger")
        elif recurrence == "Monthly" and not request.form.get("month_day"):
            flash("Select a day of month for a monthly activity.", "danger")
        elif recurrence == "Custom days" and not request.form.get("custom_days"):
            flash("Enter the number of days for the custom recurrence.", "danger")
        else:
            recurrence_value = {"Weekly": request.form.get("weekday"), "Monthly": request.form.get("month_day"), "Custom days": request.form.get("custom_days")}.get(recurrence)
            scheduled_date = datetime.strptime(scheduled_for, "%Y-%m-%d").date()
            if recurrence == "Weekly":
                weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                scheduled_date += timedelta(days=(weekdays.index(recurrence_value) - scheduled_date.weekday()) % 7)
            due_at = f"{scheduled_date.isoformat()} {request.form.get('scheduled_time') or '00:00'}"
            task_type = f"Scheduled {request.form.get('activity_type')}"
            scheduled_task_id = execute("INSERT INTO tasks (title,account_id,task_type,details,assigned_by_id,assigned_to_id,due_at,original_due_at,priority,status,recurrence_type,recurrence_value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending',%s,%s)",
                    (title, account_id, task_type, request.form.get("details") or None, session["user_id"], request.form.get("assigned_to_id") or session["user_id"], due_at, due_at, request.form.get("priority", "Normal"), None if recurrence == "One time" else recurrence, recurrence_value))
            log_task_audit(scheduled_task_id, "Created", None, task_snapshot(scheduled_task_id))
            flash("Scheduled activity created as an actionable task. Record the actual activity after it happens.", "success")
            return redirect(url_for("my_tasks"))
    return render_template("activities/schedule.html")


@app.route("/activities/scheduled/<int:task_id>/record", methods=["GET", "POST"])
def record_scheduled_activity(task_id):
    scheduled = fetch_one("""SELECT t.*, a.entity_name, u.name AS assignee_name FROM tasks t JOIN accounts a ON a.id=t.account_id JOIN users u ON u.id=t.assigned_to_id
        WHERE t.id=%s AND t.status='Pending' AND t.task_type LIKE 'Scheduled %%'""", (task_id,))
    if not scheduled:
        flash("Scheduled activity not found.", "danger")
        return redirect(url_for("activities"))
    if request.method == "POST":
        notes = request.form.get("notes", "").strip()
        if not notes:
            flash("Meaningful completion notes are required.", "danger")
        else:
            actual_at = f"{request.form.get('activity_date')} {request.form.get('activity_time') or '00:00'}"
            activity_type = scheduled["task_type"].replace("Scheduled ", "", 1)
            activity_id = execute("INSERT INTO activities (account_id,activity_type,interaction_at,notes,entered_by_id,next_action) VALUES (%s,%s,%s,%s,%s,%s)",
                    (scheduled["account_id"], activity_type, actual_at, notes, session["user_id"], "No further action required"))
            log_activity_audit(activity_id, "Created", None, activity_snapshot(activity_id))
            save_attachments(account_id=scheduled["account_id"], activity_id=activity_id)
            old_task = task_snapshot(task_id)
            execute("UPDATE tasks SET status='Completed', completed_at=NOW(), completion_notes=%s WHERE id=%s", (notes, task_id))
            log_task_audit(task_id, "Completed", old_task, task_snapshot(task_id))
            if scheduled["recurrence_type"]:
                current_due = scheduled["due_at"]
                next_due = None
                if scheduled["recurrence_type"] == "Weekly":
                    next_due = current_due + timedelta(days=7)
                elif scheduled["recurrence_type"] == "Custom days":
                    next_due = current_due + timedelta(days=int(scheduled["recurrence_value"] or 1))
                elif scheduled["recurrence_type"] == "Monthly":
                    month = current_due.month + 1
                    year = current_due.year + (month - 1) // 12
                    month = (month - 1) % 12 + 1
                    day = min(int(scheduled["recurrence_value"] or current_due.day), calendar.monthrange(year, month)[1])
                    next_due = current_due.replace(year=year, month=month, day=day)
                if next_due:
                    recurring_task_id = execute("INSERT INTO tasks (title,account_id,task_type,details,assigned_by_id,assigned_to_id,due_at,original_due_at,priority,status,recurrence_type,recurrence_value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending',%s,%s)",
                            (scheduled["title"], scheduled["account_id"], scheduled["task_type"], scheduled["details"], scheduled["assigned_by_id"], scheduled["assigned_to_id"], next_due, next_due, scheduled["priority"], scheduled["recurrence_type"], scheduled["recurrence_value"]))
                    log_task_audit(recurring_task_id, "Created by recurrence", None, task_snapshot(recurring_task_id))
            flash("Scheduled activity recorded and marked completed." + (" The next recurring occurrence has been created." if scheduled["recurrence_type"] else ""), "success")
            return redirect(url_for("activities"))
    return render_template("activities/record_scheduled.html", scheduled=scheduled)

def render_task_list(scope="my"):
    clause, params = "", []
    if scope == "my":
        clause, params = "WHERE t.assigned_to_id=%s", [session["user_id"]]
    elif scope == "assigned-by-me":
        clause, params = "WHERE t.assigned_by_id=%s", [session["user_id"]]
    elif scope == "assigned-to-tl":
        clause = "WHERE assignee.role='Team Leader'"
    elif scope == "team" and not has_management_scope():
        clause = "WHERE t.assigned_by_id=%s OR t.assigned_to_id=%s"
        params = [session["user_id"], session["user_id"]]
    rows = fetch_all(f"""SELECT t.*,a.entity_name AS account,assignee.name AS assignee,assigner.name AS assigned_by
        FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id JOIN users assignee ON assignee.id=t.assigned_to_id
        JOIN users assigner ON assigner.id=t.assigned_by_id {clause} ORDER BY t.due_at""", tuple(params))
    if not has_management_scope():
        rows = [row for row in rows if session["user_id"] in (row["assigned_by_id"], row["assigned_to_id"])]
    tasks_for_view = []
    for item in rows:
        item["overdue"] = max(0, (TODAY - item["due_at"].date()).days) if item["status"] == "Pending" else 0
        tasks_for_view.append(item)
    filters = selected_filters()
    query = filters["q"].lower()
    if query:
        tasks_for_view = [t for t in tasks_for_view if query in " ".join(str(t.get(k, "")) for k in ("title", "account", "task_type", "assignee", "assigned_by")).lower()]
    if filters["owner"]:
        tasks_for_view = [t for t in tasks_for_view if t["assignee"] == filters["owner"]]
    if filters["status"]:
        tasks_for_view = [t for t in tasks_for_view if t["status"] == filters["status"]]
    if filters["type"]:
        tasks_for_view = [t for t in tasks_for_view if t["task_type"] == filters["type"]]
    return render_template("tasks/list.html", scope=scope, tasks_for_view=tasks_for_view, filters=filters)

@app.route("/tasks")
def my_tasks(): return render_task_list("my")
@app.route("/tasks/team")
def team_tasks(): return render_task_list("team")
@app.route("/tasks/assigned-by-me")
def assigned_by_me_tasks(): return render_task_list("assigned-by-me")
@app.route("/tasks/assigned-to-tl")
def assigned_to_tl_tasks(): return render_task_list("assigned-to-tl")
@app.route("/tasks/<int:task_id>")
def task_detail(task_id):
    if not manages_task(task_id):
        return deny_access()
    task = fetch_one("""SELECT t.*,a.entity_name AS account,assignee.name AS assignee,assigner.name AS assigned_by
        FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id JOIN users assignee ON assignee.id=t.assigned_to_id
        JOIN users assigner ON assigner.id=t.assigned_by_id WHERE t.id=%s""", (task_id,))
    if not task:
        flash("Task not found.", "danger"); return redirect(url_for("my_tasks"))
    audit_rows = fetch_all("""SELECT l.*,u.name AS performed_by FROM task_audit_logs l
        JOIN users u ON u.id=l.performed_by_id WHERE l.task_id=%s ORDER BY l.created_at DESC,l.id DESC""", (task_id,))
    return render_template("tasks/detail.html", task=task, audit_rows=prepare_audit_rows(audit_rows))

@app.route("/tasks/add", methods=["GET","POST"])
@app.route("/tasks/<int:task_id>/edit", methods=["GET","POST"])
def task_form(task_id=None):
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        assigned_to_id = request.form.get("assigned_to_id")
        eligible_assignee_ids = {str(user["id"]) for user in sales_suggestion_users()}
        if not has_management_scope():
            account_id = request.form.get("account_id")
            if account_id and not can_work_on_account(int(account_id)):
                return deny_access()
        due_at = f"{request.form.get('due_date')} {request.form.get('due_time') or '09:00'}"
        if not title or not request.form.get("due_date"):
            flash("Task title and due date are required.", "danger")
        elif assigned_to_id not in eligible_assignee_ids:
            flash("Choose an active Marketing/Sales user for task assignment.", "danger")
        else:
            if task_id:
                existing = fetch_one("SELECT status FROM tasks WHERE id=%s", (task_id,))
                if not existing:
                    flash("Task not found.", "danger"); return redirect(url_for("my_tasks"))
                if existing["status"] != "Pending":
                    flash("Completed or cancelled tasks cannot be edited.", "danger"); return redirect(url_for("task_detail", task_id=task_id))
                old_task = task_snapshot(task_id)
                execute("UPDATE tasks SET title=%s,account_id=%s,task_type=%s,details=%s,assigned_to_id=%s,due_at=%s,revised_due_at=%s,priority=%s WHERE id=%s",
                    (title, request.form.get("account_id") or None, request.form.get("task_type"), request.form.get("details") or None, assigned_to_id, due_at, due_at, request.form.get("priority"), task_id))
                new_task = task_snapshot(task_id)
                action = "Reassigned" if old_task["assigned_to"] != new_task["assigned_to"] else "Updated"
                log_task_audit(task_id, action, old_task, new_task)
                flash("Task updated. The original due date has been retained.", "success")
            else:
                task_id = execute("INSERT INTO tasks (title,account_id,task_type,details,assigned_by_id,assigned_to_id,due_at,original_due_at,priority,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending')",
                    (title, request.form.get("account_id") or None, request.form.get("task_type"), request.form.get("details") or None, session["user_id"], assigned_to_id, due_at, due_at, request.form.get("priority")))
                log_task_audit(task_id, "Created", None, task_snapshot(task_id))
                flash("Task saved successfully.", "success")
            save_attachments(account_id=request.form.get("account_id") or None, task_id=task_id)
            return return_to()
    task = fetch_one("SELECT * FROM tasks WHERE id=%s", (task_id,)) if task_id else None
    if task_id and not task:
        flash("Task not found.", "danger"); return redirect(url_for("my_tasks"))
    return render_template("tasks/form.html", task_id=task_id, task=task)


@app.route("/tasks/<int:task_id>/complete", methods=["GET", "POST"])
def complete_task(task_id):
    task = fetch_one("""SELECT t.*, a.entity_name AS account FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id WHERE t.id=%s""", (task_id,))
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("my_tasks"))
    if request.method == "POST":
        notes = request.form.get("completion_notes", "").strip()
        if not notes:
            flash("Completion notes are required.", "danger")
        elif task["status"] != "Pending":
            flash("Only pending tasks can be completed.", "danger")
        else:
            old_task = task_snapshot(task_id)
            execute("UPDATE tasks SET status='Completed', completed_at=NOW(), completion_notes=%s WHERE id=%s", (notes, task_id))
            log_task_audit(task_id, "Completed", old_task, task_snapshot(task_id))
            flash("Task marked completed.", "success")
            return return_to()
    return render_template("tasks/complete.html", task=task)

@app.post("/tasks/<int:task_id>/cancel")
def cancel_task(task_id):
    reason = request.form.get("cancelled_reason", "").strip()
    if not reason:
        flash("A cancellation reason is required.", "danger")
    else:
        task = fetch_one("SELECT status FROM tasks WHERE id=%s", (task_id,))
        if not task or task["status"] != "Pending":
            flash("Only pending tasks can be cancelled.", "danger")
        else:
            old_task = task_snapshot(task_id)
            execute("UPDATE tasks SET status='Cancelled', cancelled_reason=%s WHERE id=%s", (reason, task_id))
            log_task_audit(task_id, "Cancelled", old_task, task_snapshot(task_id))
            flash("Task cancelled.", "success")
    return return_to()

@app.route("/reports/<report>")
def reports(report="tasks"):
    filters = selected_filters()
    rows = []
    user_id = session["user_id"]
    if report == "tasks":
        scope, params = ("", ()) if has_management_scope() else ("WHERE t.assigned_by_id=%s OR t.assigned_to_id=%s", (user_id, user_id))
        rows = fetch_all(f"""SELECT t.title item, COALESCE(a.entity_name,'Internal task') account, u.name owner, t.status, t.due_at relevant_date FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id JOIN users u ON u.id=t.assigned_to_id {scope} ORDER BY t.due_at""", params)
    elif report == "activities":
        scope, params = ("", ()) if has_management_scope() else ("""AND (ac.entered_by_id=%s OR a.owner_id=%s OR EXISTS (SELECT 1 FROM tasks t WHERE t.account_id=a.id AND (t.assigned_by_id=%s OR t.assigned_to_id=%s)))""", (user_id, user_id, user_id, user_id))
        rows = fetch_all(f"""SELECT ac.activity_type item,a.entity_name account,u.name owner,'Recorded' status,ac.interaction_at relevant_date FROM activities ac JOIN accounts a ON a.id=ac.account_id JOIN users u ON u.id=ac.entered_by_id WHERE ac.is_archived=0 {scope} ORDER BY ac.interaction_at DESC""", params)
    elif report == "visits":
        scope, params = ("", ()) if has_management_scope() else ("AND (t.assigned_by_id=%s OR t.assigned_to_id=%s)", (user_id, user_id))
        rows = fetch_all(f"""SELECT t.title item,COALESCE(a.entity_name,'Internal task') account,u.name owner,t.status,t.due_at relevant_date FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id JOIN users u ON u.id=t.assigned_to_id WHERE t.task_type LIKE '%%Visit%%' {scope} ORDER BY t.due_at""", params)
    elif report == "no-activity":
        scope, params = ("", ()) if has_management_scope() else ("WHERE a.owner_id=%s OR EXISTS (SELECT 1 FROM tasks t WHERE t.account_id=a.id AND (t.assigned_by_id=%s OR t.assigned_to_id=%s))", (user_id, user_id, user_id))
        rows = fetch_all(f"""SELECT a.entity_name item,a.entity_name account,u.name owner,'No activity in 30 days' status,COALESCE(MAX(ac.interaction_at),a.created_at) relevant_date FROM accounts a JOIN users u ON u.id=a.owner_id LEFT JOIN activities ac ON ac.account_id=a.id AND ac.is_archived=0 {scope} GROUP BY a.id,u.name HAVING MAX(ac.interaction_at) IS NULL OR MAX(ac.interaction_at) < DATE_SUB(CURDATE(), INTERVAL 30 DAY) ORDER BY relevant_date""", params)
    else:
        scope, params = ("", ()) if has_management_scope() else ("WHERE a.owner_id=%s OR EXISTS (SELECT 1 FROM tasks t WHERE t.account_id=a.id AND (t.assigned_by_id=%s OR t.assigned_to_id=%s))", (user_id, user_id, user_id))
        rows = fetch_all(f"""SELECT a.entity_name item,a.entity_name account,u.name owner,a.lifecycle_status status,COALESCE(a.next_follow_up_date,a.updated_at) relevant_date FROM accounts a JOIN users u ON u.id=a.owner_id {scope} ORDER BY relevant_date DESC""", params)
    query = filters["q"].lower()
    if query: rows = [r for r in rows if query in " ".join(str(v or "") for v in r.values()).lower()]
    if filters["owner"]: rows = [r for r in rows if r["owner"] == filters["owner"]]
    if filters["status"]: rows = [r for r in rows if r["status"] == filters["status"]]
    if request.args.get("export") == "csv":
        if role() != "Admin":
            flash("Only Admin can export reports.", "danger"); return redirect(url_for("reports", report=report))
        out = StringIO(); writer = csv.DictWriter(out, fieldnames=["item", "account", "owner", "status", "relevant_date"]); writer.writeheader(); writer.writerows(rows)
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={report}-report.csv"})
    return render_template("reports/index.html", report=report, report_rows=rows, filters=filters)

@app.route("/users", methods=["GET"])
@app.route("/users/<action>", methods=["GET", "POST"])
def users_page(action=None):
    if action == "add" and request.method == "POST":
        name = request.form.get("full_name", "").strip()
        dob = request.form.get("dob", "").strip()
        initial_password = dob.replace("/", "")
        selected_role = request.form.get("role", "Executive")
        role_id = {"Admin": 1, "Team Leader": 2, "Executive": 3}.get(selected_role, 3)
        if not (name and len(initial_password) == 8 and initial_password.isdigit()):
            flash("Name and DOB in DD/MM/YYYY format are required.", "danger")
        elif fetch_one("SELECT id FROM users WHERE name=%s", (name,)):
            flash("That user name is already in use.", "danger")
        else:
            execute("""INSERT INTO users (name,contact,departments,role,role_id,status,dob,designation,department_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (name, request.form.get("contact", "").strip(),
                     request.form.get("departments") or None, selected_role, role_id,
                     request.form.get("status", "Active"), dob, request.form.get("designation") or None,
                     request.form.get("department_id") or None))
            flash("User created successfully.", "success")
            return redirect(url_for("users_page"))
    return render_template("admin/users.html", action=action)

@app.route("/profile", methods=["GET","POST"])
def profile():
    user = fetch_one("SELECT id,name,contact,dob FROM users WHERE id=%s", (session["user_id"],))
    if request.method == "POST":
        name, mobile = request.form.get("full_name", "").strip(), request.form.get("mobile", "").strip()
        if not name:
            flash("Name is required.", "danger")
        else:
            execute("UPDATE users SET name=%s,contact=%s WHERE id=%s", (name, mobile, session["user_id"]))
            session["user_name"] = name
            flash("Profile saved successfully.", "success")
            return redirect(url_for("profile"))
    return render_template("auth/profile.html", profile_user=user)

if __name__ == "__main__":
    # Deliberately keep the prototype server simple and reloader-free for Windows use.
    cert_dir = Path(app.root_path) / "certs"
    app.run(debug=False, host="0.0.0.0", port=3020,
            ssl_context=(str(cert_dir / "fullchain.pem"), str(cert_dir / "privkey.pem")))
