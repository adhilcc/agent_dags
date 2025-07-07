from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from datetime import datetime, timedelta
from airflow.models import Variable
import os

# Default arguments
default_args = {
    'owner': 'lowtouch.ai_developers',
    'depends_on_past': False,
    'start_date': datetime(2024, 2, 28),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define DBT project path and executable
dbt_project_dir = "/appz/home/airflow/dags/agent_dags/dbt/webshop"
dbt_executable_path = "/dbt_venv/bin/dbt"
dbt_venv_path = "/dbt_venv/bin/activate"

# Get Airflow variables for database credentials
postgres_user = Variable.get("WEBSHOP_POSTGRES_USER")
postgres_password = Variable.get("WEBSHOP_POSTGRES_PASSWORD")

# Define dbt commands
dbt_seed_commands = [
    "address", "articles", "colors", "customer", "labels", 
    "order_positions", "order_seed", "products", "stock", "sizes"
]

dbt_run_commands = ["order"]

# Convert 8 AM IST to UTC (Airflow uses UTC)
daily_schedule_utc = "30 2 * * *"

with DAG(
    'webshop_reset_data',
    default_args=default_args,
    schedule_interval=daily_schedule_utc,
    catchup=False,
    tags=["reset", "webshop", "data"]
) as dag:

    # TaskGroup for dbt seed
    with TaskGroup("dbt_seed") as dbt_seed_group:
        for seed in dbt_seed_commands:
            BashOperator(
                task_id=f"dbt_seed_{seed}",
                bash_command=(
                    f"source {dbt_venv_path} && "
                    f"cd {dbt_project_dir} && "
                    f"{dbt_executable_path} seed --select {seed} "
                    f"--vars '{{\"orchestrator\": \"airflow\", \"job_name\": \"webshop_reset_data\", "
                    f"\"job_id\": \"{{{{ ti.dag_id }}}}\", \"job_run_id\": \"{{{{ ti.run_id }}}}\"}}'"
                ),
                env={
                    "WEBSHOP_POSTGRES_USER": postgres_user,
                    "WEBSHOP_POSTGRES_PASSWORD": postgres_password,
                    "DBT_PROFILES_DIR": dbt_project_dir,
                }
            )

    # TaskGroup for dbt run
    with TaskGroup("dbt_run") as dbt_run_group:
        for run in dbt_run_commands:
            BashOperator(
                task_id=f"dbt_run_{run}",
                bash_command=(
                    f"source {dbt_venv_path} && "
                    f"cd {dbt_project_dir} && "
                    f"{dbt_executable_path} run --select {run} "
                    f"--vars '{{\"orchestrator\": \"airflow\", \"job_name\": \"webshop_reset_data\", "
                    f"\"job_id\": \"{{{{ ti.dag_id }}}}\", \"job_run_id\": \"{{{{ ti.run_id }}}}\"}}'"
                ),
                env={
                    "WEBSHOP_POSTGRES_USER": postgres_user,
                    "WEBSHOP_POSTGRES_PASSWORD": postgres_password,
                    "DBT_PROFILES_DIR": dbt_project_dir,
                }
            )

    # Elementary report generation
    elementary_report_task = BashOperator(
        task_id="generate_elementary_report",
        bash_command=(
            f"mkdir -p {dbt_project_dir}/edr_target && "
            f"source {dbt_venv_path} && "
            f"/dbt_venv/bin/edr report "
            f"--project-dir {dbt_project_dir} "
            f"--profiles-dir {dbt_project_dir} "
            f"--profile-target elementary "
            f"--vars '{{\"orchestrator\": \"airflow\", \"job_name\": \"webshop_reset_data\", "
            f"\"job_id\": \"{{{{ ti.dag_id }}}}\", \"job_run_id\": \"{{{{ ti.run_id }}}}\"}}'"
        ),
        env={
            "WEBSHOP_POSTGRES_USER": postgres_user,
            "WEBSHOP_POSTGRES_PASSWORD": postgres_password,
            "DBT_PROFILES_DIR": dbt_project_dir,
        }
    )

    # DAG Dependencies
    dbt_seed_group >> dbt_run_group >> elementary_report_task
