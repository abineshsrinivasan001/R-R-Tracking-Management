# 🚀 OpsTrack — DevOps R&R Tracker (Django + Tailwind + PostgreSQL)

A professional Django-based DevOps Roles & Responsibilities Tracker with PostgreSQL backend, Tailwind CSS UI, and detailed task entry forms for developers.

---

## 📁 Project Structure

```
devops_tracker/
├── devops_tracker/          # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── tracker/                 # Main app
│   ├── models.py            # All DB models
│   ├── views.py             # Views & API endpoints
│   ├── forms.py             # Django forms
│   ├── urls.py              # App URL routing
│   ├── admin.py             # Admin panel config
│   ├── templatetags/
│   │   └── tracker_tags.py  # Custom template filters
│   ├── migrations/
│   │   └── 0001_initial.py
│   └── templates/tracker/
│       ├── base.html        # Base layout with sidebar
│       ├── login.html
│       ├── dashboard.html   # Main dashboard
│       └── entries/
│           ├── server_health.html
│           ├── alert_check.html
│           ├── pipeline.html
│           └── deployment.html
├── manage.py
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup Instructions

### 1. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. PostgreSQL Setup
```sql
-- In psql:
CREATE DATABASE devops_tracker_db;
CREATE USER devops_user WITH PASSWORD 'your_password_here';
GRANT ALL PRIVILEGES ON DATABASE devops_tracker_db TO devops_user;
```

### 4. Update Database Settings
Edit `devops_tracker/settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'devops_tracker_db',
        'USER': 'devops_user',
        'PASSWORD': 'your_password_here',  # ← Change this
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 5. Run Migrations
```bash
python manage.py migrate
```

### 6. Create Superuser
```bash
python manage.py createsuperuser
```

### 7. Run Development Server
```bash
python manage.py runserver
```

Visit: http://127.0.0.1:8000

---

## 🔑 Key URLs

| URL | Description |
|-----|-------------|
| `/` | Main Dashboard |
| `/login/` | Login Page |
| `/admin/` | Django Admin Panel |
| `/entries/server-health/` | Server Health Logs |
| `/entries/alerts/` | Alert Check Logs |
| `/entries/pipeline/` | CI/CD Pipeline Logs |
| `/entries/deployment/` | Deployment Validation Logs |

---

## 📊 Database Models

### `TaskLog`
Tracks which R&R tasks are marked done/wip/blocked per developer per day.

### `ServerHealthEntry`
- Date, Server Name
- CPU Usage %, Memory Usage %, Disk Usage %, Network Utilization %
- Status (Normal / Warning / Critical)
- Issue Found (Yes/No), Action Taken, Remarks

### `AlertCheckEntry`
- Date, Tool Name (Prometheus / CloudWatch / etc.)
- Total Alerts, Critical Alerts, Warning Alerts
- Alert Description, Status (Resolved/Pending), Action Taken

### `PipelineEntry`
- Date, Pipeline Name, Build Number
- Build Status, Failed Stage, Error Message
- Fix Applied, Final Status

### `DeploymentEntry`
- Date, Application Name, Version Deployed
- Deployment Status, Environment (Dev/QA/Prod)
- Errors Found, Rollback Done, Verification Status, Remarks

---

## 🎨 UI Features

- **Dark navy sidebar** with smooth active states
- **Hero banner** showing today's completion percentage
- **Stat cards** for Daily / Weekly / Monthly task progress
- **Quick Log modal** — mark any task done/wip/blocked in 2 clicks
- **"Log Details" buttons** on tasks d01–d04 open the relevant entry form
- **Color-coded tables** — red for high values, amber for medium, green for OK
- **Entry modals** — clean slide-up forms with field validation
- **Auto task marking** — submitting an entry auto-marks its parent daily task as done

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2 |
| Database | PostgreSQL |
| Frontend | Tailwind CSS (CDN) |
| Icons | Font Awesome 6 |
| Fonts | Plus Jakarta Sans + Bricolage Grotesque |
| Auth | Django built-in auth |

---

## 📝 Adding More Developers

```bash
python manage.py createsuperuser
# Or via Django Admin: /admin/ → Users → Add User
```

Each user gets their own dashboard, task logs, and entry records.
