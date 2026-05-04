import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from tracker.models import Server, TaskDefinition, TaskLog, GeneralTaskEntry, Developer, ServerHealthEntry

class Command(BaseCommand):
    help = 'Seed production-level testing data with realistic field values'

    def handle(self, *args, **options):
        # 1. Get or Create Developer
        user, _ = User.objects.get_or_create(username='admin', defaults={'is_superuser': True, 'is_staff': True})
        if not hasattr(user, 'developer'):
            Developer.objects.create(user=user, role='manager', job_title='Lead DevOps Engineer')
        
        # 2. Get or Create Server
        server, _ = Server.objects.get_or_create(
            name='PROD-WEB-01', 
            defaults={'ip_address': '10.0.0.45', 'status': 'up', 'owner': user}
        )

        # 3. Get Task Definitions
        daily_tasks = list(TaskDefinition.objects.filter(category='d'))
        weekly_tasks = list(TaskDefinition.objects.filter(category='w'))
        monthly_tasks = list(TaskDefinition.objects.filter(category='m'))

        if not daily_tasks:
            self.stdout.write(self.style.ERROR('No task definitions found. Run seed_tasks first.'))
            return

        today = timezone.now().date()
        
        # April Data (Last Month)
        self.stdout.write('Seeding April data...')
        start_april = today.replace(month=4, day=1)
        if start_april > today: # Handle edge case if today is early in the year
            start_april = start_april.replace(year=today.year - 1)
        
        for i in range(30):
            d = start_april + timedelta(days=i)
            self.seed_daily(server, user, d, daily_tasks)
            # Seed 2 weekly tasks per week in April
            if d.weekday() == 0:
                self.seed_custom(server, user, d, weekly_tasks[:2])
            # Seed 3 monthly tasks for April
            if d.day == 15:
                self.seed_custom(server, user, d, monthly_tasks[:3])

        # May Data (Till Now)
        self.stdout.write('Seeding May data...')
        start_may = today.replace(day=1)
        for i in range((today - start_may).days + 1):
            d = start_may + timedelta(days=i)
            self.seed_daily(server, user, d, daily_tasks)

        # 8 Weekly Tasks for this week
        self.stdout.write('Seeding 8 Weekly tasks for this week...')
        for t in weekly_tasks[:8]:
            self.seed_single_task(server, user, today, t)

        # 3 Monthly Tasks for this month
        self.stdout.write('Seeding 3 Monthly tasks for this month...')
        for t in monthly_tasks[:3]:
            self.seed_single_task(server, user, today, t)

        self.stdout.write(self.style.SUCCESS('Successfully seeded production testing data!'))

    def seed_daily(self, server, user, date, tasks):
        # Fill ALL daily tasks every day to get 100% compliance
        for t in tasks:
            self.seed_single_task(server, user, date, t)
        
        # Also seed ServerHealthEntry for the graphs
        dt = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
        ServerHealthEntry.objects.create(
            developer=user,
            date=date,
            server_name=server.name,
            cpu_usage=random.randint(15, 85),
            memory_usage=random.randint(30, 90),
            disk_usage=random.randint(40, 75),
            network_utilization=random.randint(5, 40),
            status='normal',
            created_at=dt
        )

    def seed_custom(self, server, user, date, tasks):
        for t in tasks:
            self.seed_single_task(server, user, date, t)

    def seed_single_task(self, server, user, date, task_def):
        # Generate realistic data based on field names
        data = {}
        for field in task_def.fields_schema:
            field_name = field.split('|')[0]
            if 'cpu' in field_name: data[field_name] = random.randint(15, 85)
            elif 'memory' in field_name: data[field_name] = random.randint(30, 90)
            elif 'disk' in field_name: data[field_name] = random.randint(40, 75)
            elif 'uptime' in field_name: data[field_name] = random.randint(1, 365)
            elif 'status' in field_name or 'result' in field_name:
                if '|' in field: data[field_name] = field.split('|')[1].split(',')[0]
                else: data[field_name] = 'Success'
            elif 'alerts' in field_name: data[field_name] = random.randint(0, 5)
            elif 'version' in field_name: data[field_name] = f'v1.{random.randint(0,9)}.{random.randint(10,99)}'
            elif 'count' in field_name: data[field_name] = random.randint(1, 100)
            elif 'date' in field_name: data[field_name] = str(date)
            else: data[field_name] = 'N/A'
        
        # Add a remark
        remarks = [
            "All metrics within threshold.",
            "Normal operating parameters observed.",
            "Verified and confirmed.",
            "Minor latency detected but resolved.",
            "No issues found during routine check."
        ]
        
        # Create TaskLog
        dt = timezone.make_aware(timezone.datetime.combine(date, timezone.datetime.min.time()))
        TaskLog.objects.create(
            developer=user,
            server=server,
            task_id=task_def.task_id,
            task_text=task_def.text,
            category=task_def.category,
            status='done',
            notes=random.choice(remarks),
            logged_at=dt
        )
        
        # Create GeneralTaskEntry
        GeneralTaskEntry.objects.create(
            developer=user,
            server=server,
            date=date,
            task_id=task_def.task_id,
            task_text=task_def.text,
            status='done',
            fields_data=data,
            remarks=random.choice(remarks),
            created_at=dt
        )
