CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  contact VARCHAR(20) NOT NULL,
  departments VARCHAR(50) NULL,
  role ENUM('Executive','Team Leader','Admin') NOT NULL,
  role_id BIGINT NOT NULL DEFAULT 3,
  status ENUM('Active','Inactive') NOT NULL DEFAULT 'Active',
  last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  dob VARCHAR(10) NULL,
  designation VARCHAR(100) NULL,
  department_id INT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  account_type ENUM('New Lead','Existing Client') NOT NULL,
  entity_name VARCHAR(180) NOT NULL,
  entity_category ENUM('Doctor','Clinic','Hospital','Diagnostic Centre/Laboratory','Other') NOT NULL,
  area VARCHAR(120) NOT NULL,
  lead_source VARCHAR(100) NULL,
  owner_id INT NOT NULL,
  lead_temperature ENUM('Hot','Warm','Cold') NULL,
  lifecycle_status ENUM('Active','Converted','Lost','On Hold','Inactive','Archived') NOT NULL DEFAULT 'Active',
  status_reason VARCHAR(500) NULL,
  next_follow_up_date DATE NULL,
  notes TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_accounts_owner FOREIGN KEY (owner_id) REFERENCES users(id),
  INDEX ix_accounts_owner (owner_id), INDEX ix_accounts_status (lifecycle_status)
);

CREATE TABLE IF NOT EXISTS contacts (
  id INT AUTO_INCREMENT PRIMARY KEY, account_id INT NOT NULL,
  full_name VARCHAR(120) NOT NULL, designation VARCHAR(120) NULL,
  mobile VARCHAR(30) NOT NULL, alternate_mobile VARCHAR(30) NULL, email VARCHAR(160) NULL,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  is_archived BOOLEAN NOT NULL DEFAULT FALSE, archive_reason VARCHAR(500) NULL, archived_at DATETIME NULL,
  CONSTRAINT fk_contacts_account FOREIGN KEY (account_id) REFERENCES accounts(id), INDEX ix_contacts_mobile (mobile)
);

CREATE TABLE IF NOT EXISTS activities (
  id INT AUTO_INCREMENT PRIMARY KEY, account_id INT NOT NULL, activity_type VARCHAR(60) NOT NULL,
  interaction_at DATETIME NOT NULL, notes TEXT NOT NULL, contact_id INT NULL,
  entered_by_id INT NOT NULL, entered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  delayed_entry_reason VARCHAR(500) NULL, next_action VARCHAR(80) NOT NULL,
  no_action_reason VARCHAR(500) NULL, is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  archive_reason VARCHAR(500) NULL, edited_at DATETIME NULL,
  CONSTRAINT fk_activities_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT fk_activities_contact FOREIGN KEY (contact_id) REFERENCES contacts(id),
  CONSTRAINT fk_activities_user FOREIGN KEY (entered_by_id) REFERENCES users(id), INDEX ix_activities_account (account_id)
);

CREATE TABLE IF NOT EXISTS tasks (
  id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, account_id INT NULL,
  task_type VARCHAR(80) NOT NULL, details TEXT NULL, assigned_by_id INT NOT NULL, assigned_to_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, due_at DATETIME NOT NULL,
  original_due_at DATETIME NOT NULL, revised_due_at DATETIME NULL,
  priority ENUM('High','Normal','Low') NOT NULL DEFAULT 'Normal',
  status ENUM('Pending','Completed','Cancelled') NOT NULL DEFAULT 'Pending',
  completed_at DATETIME NULL, completion_notes TEXT NULL, cancelled_reason VARCHAR(500) NULL,
  recurrence_type VARCHAR(40) NULL, recurrence_value VARCHAR(40) NULL,
  CONSTRAINT fk_tasks_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT fk_tasks_by FOREIGN KEY (assigned_by_id) REFERENCES users(id),
  CONSTRAINT fk_tasks_to FOREIGN KEY (assigned_to_id) REFERENCES users(id), INDEX ix_tasks_due (due_at), INDEX ix_tasks_to (assigned_to_id)
);

CREATE TABLE IF NOT EXISTS task_audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id INT NOT NULL,
  action VARCHAR(40) NOT NULL,
  performed_by_id INT NOT NULL,
  old_values LONGTEXT NULL,
  new_values LONGTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_task_audit_task FOREIGN KEY (task_id) REFERENCES tasks(id),
  CONSTRAINT fk_task_audit_user FOREIGN KEY (performed_by_id) REFERENCES users(id),
  INDEX ix_task_audit_task_time (task_id, created_at)
);

CREATE TABLE IF NOT EXISTS activity_audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  activity_id INT NOT NULL,
  action VARCHAR(40) NOT NULL,
  performed_by_id INT NOT NULL,
  old_values LONGTEXT NULL,
  new_values LONGTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_activity_audit_activity FOREIGN KEY (activity_id) REFERENCES activities(id),
  CONSTRAINT fk_activity_audit_user FOREIGN KEY (performed_by_id) REFERENCES users(id),
  INDEX ix_activity_audit_time (activity_id, created_at)
);

CREATE TABLE IF NOT EXISTS files (
  id INT AUTO_INCREMENT PRIMARY KEY, account_id INT NULL, activity_id INT NULL, task_id INT NULL,
  original_name VARCHAR(255) NOT NULL, stored_name VARCHAR(255) NOT NULL, caption VARCHAR(255) NULL,
  uploaded_by_id INT NOT NULL, uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_archived BOOLEAN NOT NULL DEFAULT FALSE, archive_reason VARCHAR(500) NULL, archived_at DATETIME NULL,
  CONSTRAINT fk_files_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT fk_files_activity FOREIGN KEY (activity_id) REFERENCES activities(id),
  CONSTRAINT fk_files_task FOREIGN KEY (task_id) REFERENCES tasks(id),
  CONSTRAINT fk_files_user FOREIGN KEY (uploaded_by_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS ownership_history (
  id INT AUTO_INCREMENT PRIMARY KEY, account_id INT NOT NULL, previous_owner_id INT NOT NULL,
  new_owner_id INT NOT NULL, changed_by_id INT NOT NULL, reason VARCHAR(500) NOT NULL,
  changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ownership_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT fk_ownership_previous FOREIGN KEY (previous_owner_id) REFERENCES users(id),
  CONSTRAINT fk_ownership_new FOREIGN KEY (new_owner_id) REFERENCES users(id),
  CONSTRAINT fk_ownership_by FOREIGN KEY (changed_by_id) REFERENCES users(id)
);
