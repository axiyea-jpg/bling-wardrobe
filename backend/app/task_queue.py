import json

from .settings import settings


def dispatch(path: str, payload: dict) -> bool:
    """Send durable processing to Cloud Tasks when production queue settings exist."""
    required = [settings.cloud_tasks_project, settings.cloud_tasks_location, settings.cloud_tasks_queue, settings.cloud_run_service_url]
    if not all(required):
        return False
    from google.cloud import tasks_v2
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(settings.cloud_tasks_project, settings.cloud_tasks_location, settings.cloud_tasks_queue)
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": settings.cloud_run_service_url.rstrip("/") + path,
            "headers": {"Content-Type":"application/json", "X-Task-Secret":settings.cloud_tasks_secret},
            "body": json.dumps(payload, ensure_ascii=False).encode(),
        }
    }
    client.create_task(parent=parent, task=task)
    return True
