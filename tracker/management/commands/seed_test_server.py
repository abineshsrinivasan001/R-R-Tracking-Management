import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from tracker.models import Server, TaskDefinition, TaskLog, GeneralTaskEntry, Developer, ServerHealthEntry

class Command(BaseCommand):
    help = 'Seed testing data from July to today for test server'

    def handle(self, *args, **options):
        # 1. Get or Create Developer
        user, _ = User.objects.get_or_create(username='admin', defaults={'is_superuser': True, 'is_staff': True})
        if not hasattr(user, 'developer'):
            Developer.objects.create(user=user, role='manager', job_title='Lead DevOps Engineer')
        
        # 2. Get the Server
        server = Server.objects.filter(name__icontains='test server').first()
        if not server:
            self.stdout.write(self.style.ERROR('Server "test server" not found. Please create it first.'))
            return
            
        # Clear existing logs for this server to avoid duplicates
        TaskLog.objects.filter(server=server).delete()
        GeneralTaskEntry.objects.filter(server=server).delete()
        ServerHealthEntry.objects.filter(server_name=server.name).delete()

        # 3. Get Task Definitions
        daily_tasks = list(TaskDefinition.objects.filter(category='d', is_active=True))
        weekly_tasks = list(TaskDefinition.objects.filter(category='w', is_active=True))
        monthly_tasks = list(TaskDefinition.objects.filter(category='m', is_active=True))

        if not daily_tasks:
            self.stdout.write(self.style.ERROR('No task definitions found.'))
            return

        today = timezone.now().date()
        
        # Seed from July 1st to Today
        start_date = today.replace(month=7, day=1)
        if start_date > today:
            start_date = start_date.replace(year=today.year - 1)

        self.stdout.write(f'Seeding data from {start_date} to {today} for {server.name}...')
        
        for i in range((today - start_date).days + 1):
            d = start_date + timedelta(days=i)
            
            # Daily Tasks
            self.seed_daily(server, user, d, daily_tasks)
            
            # Weekly tasks (distribute randomly across the week)
            if d.weekday() == 0:  # Monday
                self.seed_custom(server, user, d, weekly_tasks[:len(weekly_tasks)//2])
            elif d.weekday() == 3:  # Thursday
                self.seed_custom(server, user, d, weekly_tasks[len(weekly_tasks)//2:])
                
            # Monthly tasks
            if d.day == 15:
                self.seed_custom(server, user, d, monthly_tasks)

        self.stdout.write(self.style.SUCCESS('Successfully seeded production testing data!'))

    def seed_daily(self, server, user, date, tasks):
        # 80-100% completion rate for daily tasks to make it realistic
        num_tasks_to_do = random.randint(int(len(tasks)*0.8), len(tasks))
        tasks_to_do = random.sample(tasks, num_tasks_to_do)
        
        for t in tasks_to_do:
            self.seed_single_task(server, user, date, t)
        
        # Seed ServerHealthEntry for the graphs
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
        
        remarks = [
            "All metrics within threshold.",
            "Normal operating parameters observed.",
            "Verified and confirmed.",
            "Minor latency detected but resolved.",
            "No issues found during routine check."
        ]
        
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
