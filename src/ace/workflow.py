from ace.pipeline import run as pipeline_run


def run(project_path):
    print("ACE Workflow")
    print("-" * 30)

    pipeline_run(project_path)
