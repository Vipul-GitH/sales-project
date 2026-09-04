import unittest
from uuid import uuid4

from app import app
from database import fetch_all


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def login(self, user_id="Dr Vipul Bhasin", password="21031991"):
        return self.client.post("/login", data={"login_id": user_id, "password": password}, follow_redirects=False)

    def test_protected_routes_require_session(self):
        for url in ("/dashboard", "/accounts", "/activities", "/tasks", "/visits", "/reports/tasks", "/users", "/users/add"):
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response.headers["Location"], "/login", url)

    def test_both_admins_can_login(self):
        for user_id, password in (("Dr Vipul Bhasin", "21031991"), ("Dr Vishu Bhasin", "24031985")):
            with app.test_client() as client:
                response = client.post("/login", data={"login_id": user_id, "password": password}, follow_redirects=False)
                self.assertEqual(response.headers["Location"], "/dashboard")

    def test_login_has_no_password_reset_link_and_lists_active_users(self):
        page = self.client.get("/login").get_data(as_text=True)
        self.assertNotIn("Forgot password", page)
        self.assertIn("Dr Vipul Bhasin", page)
        self.assertIn("Dr Vishu Bhasin", page)

    def test_logout_clears_session(self):
        self.login()
        self.client.get("/logout")
        response = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(response.headers["Location"], "/login")

    def test_user_creation_persists_and_duplicate_is_rejected(self):
        self.login()
        user_id = f"qa-user-{uuid4().hex[:8]}"
        response = self.client.post("/users/add", data={"full_name": user_id, "dob": "01/01/2000", "contact": "9999999999", "role": "Executive"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(fetch_all("SELECT id FROM users WHERE name=%s", (user_id,)))
        response = self.client.post("/users/add", data={"full_name": user_id, "dob": "01/01/2000", "contact": "9999999999", "role": "Executive"}, follow_redirects=True)
        self.assertIn("already in use", response.get_data(as_text=True))

    def test_account_creation_persists_with_contact(self):
        self.login()
        response = self.client.post("/accounts/add", data={
            "account_type": "New Lead", "entity_name": "QA Clinic", "entity_category": "Clinic",
            "area": "Saket", "lead_source": "QA", "owner_id": "1", "lead_temperature": "Hot",
            "next_follow_up_date": "2026-08-10", "notes": "QA record", "contact_name": "QA Contact",
            "designation": "Manager", "mobile": "9999999999",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        account = fetch_all("SELECT id FROM accounts WHERE entity_name=%s", ("QA Clinic",))[0]
        self.assertTrue(fetch_all("SELECT id FROM contacts WHERE account_id=%s AND full_name=%s", (account["id"], "QA Contact")))

    def test_account_activity_task_chain_persists(self):
        self.login()
        account_name = f"QA Flow Clinic {uuid4().hex[:8]}"
        self.client.post("/accounts/add", data={"account_type":"New Lead","entity_name":account_name,"entity_category":"Clinic","area":"Saket","owner_id":"1","lead_temperature":"Warm"})
        account_id = fetch_all("SELECT id FROM accounts WHERE entity_name=%s", (account_name,))[0]["id"]
        activity = self.client.post("/activities/add", data={"account_id":account_id,"activity_type":"Visit","activity_date":"2026-08-05","activity_time":"10:00","notes":"QA activity","next_action":"Create follow-up task","task_due_date":"2026-08-10"}, follow_redirects=False)
        self.assertEqual(activity.status_code, 302)
        self.assertTrue(fetch_all("SELECT id FROM activities WHERE account_id=%s AND notes=%s", (account_id,"QA activity")))
        task = self.client.post("/tasks/add", data={"title":"QA follow-up","account_id":account_id,"task_type":"Follow-up Call","assigned_to_id":"1","due_date":"2026-08-10","due_time":"09:00","priority":"Normal"}, follow_redirects=False)
        self.assertEqual(task.status_code, 302)
        self.assertTrue(fetch_all("SELECT id FROM tasks WHERE account_id=%s AND title=%s", (account_id,"QA follow-up")))

    def test_task_completion_returns_to_my_tasks_and_cancel_persists_reason(self):
        self.login()
        task_id = fetch_all("SELECT id FROM tasks WHERE status='Pending' ORDER BY id DESC LIMIT 1")[0]["id"]
        complete = self.client.post(f"/tasks/{task_id}/complete", data={"completion_notes": "Verified completion", "next": "/tasks"}, follow_redirects=False)
        self.assertEqual(complete.headers["Location"], "/tasks")
        self.assertEqual(fetch_all("SELECT status FROM tasks WHERE id=%s", (task_id,))[0]["status"], "Completed")
        new_task = self.client.post("/tasks/add", data={"title":"Cancel verification","task_type":"Other","assigned_to_id":"1","due_date":"2026-08-20","priority":"Low"}, follow_redirects=False)
        self.assertEqual(new_task.status_code, 302)
        cancel_id = fetch_all("SELECT id FROM tasks WHERE title=%s ORDER BY id DESC", ("Cancel verification",))[0]["id"]
        self.client.post(f"/tasks/{cancel_id}/cancel", data={"cancelled_reason":"No longer needed", "next":"/tasks"})
        cancelled = fetch_all("SELECT status,cancelled_reason FROM tasks WHERE id=%s", (cancel_id,))[0]
        self.assertEqual((cancelled["status"], cancelled["cancelled_reason"]), ("Cancelled", "No longer needed"))

    def test_profile_and_reports_are_data_backed(self):
        self.login()
        profile = self.client.post("/profile", data={"full_name":"Dr Vipul Bhasin", "mobile":"9999900000"}, follow_redirects=True)
        self.assertIn("Profile saved successfully", profile.get_data(as_text=True))
        self.assertEqual(fetch_all("SELECT contact FROM users WHERE name=%s", ("Dr Vipul Bhasin",))[0]["contact"], "9999900000")
        report = self.client.get("/reports/tasks")
        self.assertIn("Export filtered CSV", report.get_data(as_text=True))
        export = self.client.get("/reports/tasks?export=csv")
        self.assertEqual(export.mimetype, "text/csv")
        self.assertIn("item,account,owner,status,relevant_date", export.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
