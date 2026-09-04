"""Create the compact schema and load non-sensitive fictional demonstration data."""
import json
from pathlib import Path
from database import connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def run_schema(conn):
    statements = [
        statement.strip()
        for statement in SCHEMA_PATH.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)


def seed(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM users")
        if cur.fetchone()["count"]:
            return
        people = [
            ("Dr Vipul Bhasin", "9810030372", "Admin", 1, "Active", "21/03/1991", "Admin"),
            ("Dr Vishu Bhasin", "9810637037", "Admin", 1, "Active", "24/03/1985", "Admin"),
            ("Neha Kapoor", "", "Executive", 3, "Active", "01/01/1990", "Sales Executive"),
            ("Arjun Sethi", "", "Executive", 3, "Active", "01/01/1990", "Sales Executive"),
            ("Pooja Khanna", "", "Executive", 3, "Active", "01/01/1990", "Sales Executive"),
            ("Vikram Arora", "", "Executive", 3, "Inactive", "01/01/1990", "Sales Executive"),
        ]
        cur.executemany("INSERT INTO users (name,contact,role,role_id,status,dob,designation) VALUES (%s,%s,%s,%s,%s,%s,%s)", people)
        accounts=[("New Lead","Dr. Rhea Malhotra Clinic","Doctor","Greater Kailash II","Field visit",3,"Hot","Active",None,"2026-08-05","Rate sheet requested"),
        ("Existing Client","Saket Family Hospital","Hospital","Saket","Existing relationship",2,None,"Active",None,None,"Monthly relationship visit"),
        ("New Lead","Vasant Diagnostic Centre","Diagnostic Centre/Laboratory","Vasant Kunj","Referral",4,"Warm","On Hold","Awaiting internal decision","2026-08-08",None),
        ("New Lead","Dr. Kabir Bedi","Doctor","Defence Colony","Field visit",5,"Hot","Active",None,"2026-08-05",None),
        ("Existing Client","Green Park Women’s Clinic","Clinic","Green Park","Existing relationship",3,None,"Active",None,None,None),
        ("New Lead","Hauz Khas Polyclinic","Clinic","Hauz Khas","Field visit",2,"Cold","Lost","Already contracted elsewhere",None,None),
        ("Existing Client","Lajpat Nagar Imaging Lab","Diagnostic Centre/Laboratory","Lajpat Nagar","Referral",4,None,"Active",None,None,None),
        ("New Lead","Dr. Ishita Roy","Doctor","Kalkaji","Field visit",5,"Warm","Converted","Converted after quotation",None,None),
        ("Existing Client","South Delhi Ortho Centre","Clinic","Malviya Nagar","Existing relationship",3,None,"Inactive","No longer accepting referrals",None,None),
        ("New Lead","Mehra Nursing Home","Hospital","Chittaranjan Park","Referral",4,"Hot","Active",None,"2026-08-07",None)]
        cur.executemany("INSERT INTO accounts (account_type,entity_name,entity_category,area,lead_source,owner_id,lead_temperature,lifecycle_status,status_reason,next_follow_up_date,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", accounts)
        cur.executemany("INSERT INTO contacts (account_id,full_name,designation,mobile,is_primary) VALUES (%s,%s,%s,%s,%s)", [(1,"Dr. Rhea Malhotra","Consultant Physician","9876543210",1),(1,"Sonal Gupta","Clinic Manager","9811122334",0),(2,"Prateek Nanda","Administrator","9898989898",1),(4,"Dr. Kabir Bedi","Orthopaedic Surgeon","9876501234",1)])
        tasks=[("Call Dr. Rhea about rate request",1,"Follow-up Call",2,3,"2026-08-05 11:30:00","High","Pending",None,None),
        ("Send thyroid profile quotation",10,"Prepare/Send Quotation",4,4,"2026-08-02 16:00:00","High","Pending",None,None),
        ("Monthly relationship visit",2,"Client Visit",2,2,"2026-08-05 14:00:00","Normal","Pending","Monthly","day 5"),
        ("Confirm referral decision",4,"Collect Client Decision",5,5,"2026-08-05 10:00:00","High","Pending",None,None),
        ("Share home collection leaflet",12 if False else 2,"Send Requested Information/Documents",3,2,"2026-08-06 10:00:00","Normal","Pending",None,None)]
        cur.executemany("INSERT INTO tasks (title,account_id,task_type,assigned_by_id,assigned_to_id,due_at,original_due_at,priority,status,recurrence_type,recurrence_value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", [(a,b,c,d,e,f,f,g,h,i,j) for a,b,c,d,e,f,g,h,i,j in tasks])
        cur.execute("INSERT INTO activities (account_id,activity_type,interaction_at,notes,contact_id,entered_by_id,delayed_entry_reason,next_action) VALUES (1,'Visit','2026-08-04 10:15:00','Discussed the requested rate sheet and turnaround expectations.',1,3,'Entered after the field visit','Create quotation/rates task')")


def backfill_audit(conn):
    """Give pre-audit records an honest baseline without inventing edit history."""
    with conn.cursor() as cur:
        cur.execute("""SELECT t.id,t.assigned_by_id,t.created_at,t.title,COALESCE(a.entity_name,'Internal task') account,
            t.task_type,t.details,assignee.name assigned_to,assigner.name assigned_by,t.due_at,t.original_due_at,
            t.revised_due_at,t.priority,t.status,t.completed_at,t.completion_notes,t.cancelled_reason
            FROM tasks t LEFT JOIN accounts a ON a.id=t.account_id
            JOIN users assignee ON assignee.id=t.assigned_to_id JOIN users assigner ON assigner.id=t.assigned_by_id
            WHERE NOT EXISTS (SELECT 1 FROM task_audit_logs l WHERE l.task_id=t.id)""")
        task_rows = cur.fetchall()
        for row in task_rows:
            task_id, user_id, created_at = row.pop("id"), row.pop("assigned_by_id"), row.pop("created_at")
            cur.execute("INSERT INTO task_audit_logs (task_id,action,performed_by_id,new_values,created_at) VALUES (%s,%s,%s,%s,%s)",
                        (task_id, "Existing record baseline", user_id, json.dumps(row, default=str, ensure_ascii=False), created_at))

        cur.execute("""SELECT a.id,a.entered_by_id,a.entered_at,a.activity_type,ac.entity_name account,a.interaction_at,
            a.notes,u.name entered_by,a.next_action,a.delayed_entry_reason,a.no_action_reason,a.edited_at
            FROM activities a JOIN accounts ac ON ac.id=a.account_id JOIN users u ON u.id=a.entered_by_id
            WHERE NOT EXISTS (SELECT 1 FROM activity_audit_logs l WHERE l.activity_id=a.id)""")
        activity_rows = cur.fetchall()
        for row in activity_rows:
            activity_id, user_id, entered_at = row.pop("id"), row.pop("entered_by_id"), row.pop("entered_at")
            row["entered_at"] = entered_at
            cur.execute("INSERT INTO activity_audit_logs (activity_id,action,performed_by_id,new_values,created_at) VALUES (%s,%s,%s,%s,%s)",
                        (activity_id, "Existing record baseline", user_id, json.dumps(row, default=str, ensure_ascii=False), entered_at))


if __name__ == "__main__":
    with connection() as conn:
        run_schema(conn); seed(conn); backfill_audit(conn)
    print("Referral Sales MySQL schema is ready.")
