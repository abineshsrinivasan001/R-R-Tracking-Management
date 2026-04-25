from django import forms
from .models import ServerHealthEntry, AlertCheckEntry, PipelineEntry, DeploymentEntry, TaskLog


class TaskLogForm(forms.ModelForm):
    class Meta:
        model = TaskLog
        fields = ['task_id', 'task_text', 'category', 'status', 'notes']
        widgets = {
            'task_id': forms.HiddenInput(),
            'task_text': forms.HiddenInput(),
            'category': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'tw-form-select'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'tw-form-textarea', 'placeholder': 'Any details, blockers, or observations...'}),
        }


class ServerHealthForm(forms.ModelForm):
    class Meta:
        model = ServerHealthEntry
        exclude = ['developer', 'created_at']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-field'}),
            'server_name': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. prod-server-1'}),
            'cpu_usage': forms.NumberInput(attrs={'class': 'form-field', 'placeholder': '0–100', 'step': '0.01', 'min': '0', 'max': '100'}),
            'memory_usage': forms.NumberInput(attrs={'class': 'form-field', 'placeholder': '0–100', 'step': '0.01', 'min': '0', 'max': '100'}),
            'disk_usage': forms.NumberInput(attrs={'class': 'form-field', 'placeholder': '0–100', 'step': '0.01', 'min': '0', 'max': '100'}),
            'network_utilization': forms.NumberInput(attrs={'class': 'form-field', 'placeholder': '0–100', 'step': '0.01', 'min': '0', 'max': '100'}),
            'status': forms.Select(attrs={'class': 'form-field'}),
            'issue_found': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'action_taken': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Actions taken to resolve...'}),
            'remarks': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Additional notes or observations...'}),
        }


class AlertCheckForm(forms.ModelForm):
    class Meta:
        model = AlertCheckEntry
        exclude = ['developer', 'created_at']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-field'}),
            'tool_name': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. Prometheus, CloudWatch, Grafana'}),
            'total_alerts': forms.NumberInput(attrs={'class': 'form-field', 'min': '0'}),
            'critical_alerts': forms.NumberInput(attrs={'class': 'form-field', 'min': '0'}),
            'warning_alerts': forms.NumberInput(attrs={'class': 'form-field', 'min': '0'}),
            'alert_description': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Describe the alerts...'}),
            'status': forms.Select(attrs={'class': 'form-field'}),
            'action_taken': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'What was done to resolve...'}),
        }


class PipelineForm(forms.ModelForm):
    class Meta:
        model = PipelineEntry
        exclude = ['developer', 'created_at']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-field'}),
            'pipeline_name': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. user-service-deploy'}),
            'build_number': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. #145'}),
            'build_status': forms.Select(attrs={'class': 'form-field'}),
            'failed_stage': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. Unit Testing (leave blank if success)'}),
            'error_message': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Error details if build failed...'}),
            'fix_applied': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'What fix was applied...'}),
            'final_status': forms.Select(attrs={'class': 'form-field'}),
        }


class DeploymentForm(forms.ModelForm):
    class Meta:
        model = DeploymentEntry
        exclude = ['developer', 'created_at']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-field'}),
            'application_name': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. Payment Service'}),
            'version_deployed': forms.TextInput(attrs={'class': 'form-field', 'placeholder': 'e.g. v2.3.1'}),
            'deployment_status': forms.Select(attrs={'class': 'form-field'}),
            'environment': forms.Select(attrs={'class': 'form-field'}),
            'errors_found': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Describe errors if any (leave blank if none)...'}),
            'rollback_done': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'verification_status': forms.Select(attrs={'class': 'form-field'}),
            'remarks': forms.Textarea(attrs={'class': 'form-field', 'rows': 3, 'placeholder': 'Additional remarks...'}),
        }
