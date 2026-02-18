
import asyncio
import os
import random
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from backbone.core.models import User, LogEntry, TaskLog, Session
from backbone.utils import PasswordManager

async def generate_data():
    # Database Connection
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["backbone_app"]
    
    # Initialize Beanie
    await init_beanie(database=db, document_models=[User, LogEntry, TaskLog, Session])
    
    print("🚀 Starting Dummy Data Generation...")

    # 1. Create Users
    print("👤 Creating Users...")
    users = []
    for i in range(5):
        email = f"user{i}@example.com"
        existing = await User.find_one(User.email == email)
        if not existing:
            user = User(
                username=f"user{i}",
                email=email,
                full_name=f"User {i}",
                hashed_password=PasswordManager.hash_password("password"),
                is_active=True,
                is_staff=i % 2 == 0, # Some staff
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
            )
            await user.insert()
            users.append(user)
            print(f"   - Created {user.username}")
        else:
            users.append(existing)

    # 2. Create Logs
    print("📝 Creating Logs...")
    levels = ["INFO", "WARNING", "ERROR", "DEBUG"]
    modules = ["auth", "core", "tasks", "api"]
    
    for i in range(20):
        log = LogEntry(
            level=random.choice(levels),
            message=f"Log entry #{i} - Sample message",
            module=f"backbone.{random.choice(modules)}",
            function="sample_function",
            line=random.randint(10, 200),
            created_at=datetime.utcnow() - timedelta(hours=random.randint(0, 48))
        )
        await log.insert()
    print(f"   - Created 20 log entries")

    # 3. Create Task Logs (Simulated)
    print("⚙️ Creating Task Logs...")
    tasks = [
        "backbone.tasks.send_email",
        "backbone.core.tasks.index_data",
        "backbone.auth.tasks.cleanup_sessions",
        "main.process_new_note_task"
    ]
    
    for i in range(15):
        status = random.choice(["queued", "processing", "completed", "failed"])
        started = datetime.utcnow() - timedelta(minutes=random.randint(10, 100))
        completed = started + timedelta(seconds=random.randint(1, 30)) if status in ["completed", "failed"] else None
        
        task_log = TaskLog(
            task_id=f"task-{i}-{random.randint(1000,9999)}",
            function_name=random.choice(tasks),
            args=["arg1", i],
            kwargs={"priority": "high" if i % 2 == 0 else "low"},
            status=status,
            queued_at=started - timedelta(seconds=1),
            started_at=started if status != "queued" else None,
            completed_at=completed,
            execution_time_s=None if not completed else round((completed - started).total_seconds(), 2),
            error_message="Simulation Error" if status == "failed" else None
        )
        await task_log.insert()
    print(f"   - Created 15 task logs")
    
    print("✅ Dummy Data Generation Complete!")

if __name__ == "__main__":
    asyncio.run(generate_data())
