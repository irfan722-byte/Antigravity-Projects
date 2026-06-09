import os
import json
import logging
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models, auth, grader, seed

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TASK_SEQUENCE = [
    # Beginner (5 tasks)
    "daily_showroom_footfall",
    "weekly_sales_volume",
    "showroom_csat_score",
    "spare_parts_orders",
    "test_drive_conversion",
    # Intermediate (7 tasks)
    "monthly_sales_commission",
    "camry_fleet_lease",
    "sales_agent_performance",
    "spare_parts_valuation",
    "opex_allocation",
    "loan_eligibility",
    "revenue_share_audit",
    # Advanced (10 tasks)
    "dealership_profitability",
    "holding_cost_aging",
    "capital_project_eval",
    "dynamic_commission",
    "trade_in_depreciation",
    "working_capital_aging",
    "fleet_procurement",
    "showroom_feasibility",
    "parts_forecasting",
    "service_capacity"
]

app = FastAPI(
    title="Finance Excel Training Platform API",
    description="Backend API for auto-grading Excel financial models and tracking training progress.",
    version="1.0.0"
)

# CORS Setup for cross-origin cloud deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Set to False to allow '*' with Authorization headers (no cookies used)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Programmatic seeding on startup
@app.on_event("startup")
def startup_event():
    logger.info("Initializing database schema...")
    models.Base.metadata.create_all(bind=engine)
    logger.info("Seeding initial training data and generating Excel templates...")
    db = SessionLocal = seed.SessionLocal()
    try:
        seed.seed_database(db)
        seed.generate_excel_templates()
        logger.info("Startup seed verification successfully completed!")
    except Exception as e:
        logger.error(f"Error seeding database on startup: {str(e)}")
    finally:
        db.close()

@app.post("/api/auth/signup")
def signup(firebase_token: str = Form(...), full_name: str = Form(...), db: Session = Depends(get_db)):
    """Registers a new standard user or links a pre-populated profile using their Firebase Auth details."""
    payload = auth.verify_firebase_token(firebase_token)
    firebase_uid = payload.get("sub")
    email = payload.get("email")
    
    if not firebase_uid or not email:
        raise HTTPException(status_code=400, detail="Invalid Firebase authentication details")
        
    email_clean = email.strip().lower()
    
    # Check if this user is already linked
    user = db.query(models.User).filter(models.User.firebase_uid == firebase_uid).first()
    if user:
        return {"status": "success", "message": "Account already registered and active", "user_id": user.id}
        
    # Check if a pre-populated account exists with this email
    user = db.query(models.User).filter(models.User.email == email_clean).first()
    if user:
        # Link Firebase UID to existing pre-seeded profile!
        user.firebase_uid = firebase_uid
        user.full_name = full_name.strip()
        db.commit()
        return {"status": "success", "message": "Pre-populated profile linked successfully", "user_id": user.id}
        
    # Create brand new user profile
    username = email_clean.split("@")[0]
    # Handle username clashes
    import time
    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        username = f"{username}_{int(time.time())}"
        
    new_user = models.User(
        username=username,
        full_name=full_name.strip(),
        email=email_clean,
        firebase_uid=firebase_uid,
        role="user"
    )
    db.add(new_user)
    db.flush()
    
    # Initialize Progress & Scores
    progress = models.UserProgress(
        user_id=new_user.id,
        current_active_task_id="daily_showroom_footfall",
        beginner_unlocked=True,
        intermediate_unlocked=False,
        advanced_unlocked=False
    )
    db.add(progress)
    
    score = models.Score(
        user_id=new_user.id,
        total_points=0,
        failed_attempts_count=0
    )
    db.add(score)
    db.commit()
    
    return {"status": "success", "message": "New profile created successfully", "user_id": new_user.id}

@app.post("/api/auth/login")
def login(firebase_token: str = Form(...), db: Session = Depends(get_db)):
    """Verifies Firebase token, checks user database records, and returns workspace data."""
    payload = auth.verify_firebase_token(firebase_token)
    firebase_uid = payload.get("sub")
    email = payload.get("email")
    
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    # Look up user
    user = db.query(models.User).filter(models.User.firebase_uid == firebase_uid).first()
    
    if not user and email:
        # Fallback linking for pre-populated users
        user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
        if user:
            user.firebase_uid = firebase_uid
            db.commit()
            db.refresh(user)
            
    if not user:
        # Check if the logging in user is our seeded admin!
        if email and email.strip().lower() == "admin@training.com":
            # Auto register admin since we don't have signup page for admin
            user = db.query(models.User).filter(models.User.role == "admin").first()
            if user:
                user.firebase_uid = firebase_uid
                user.email = "admin@training.com"
                db.commit()
                db.refresh(user)
                
    if not user and email:
        # Auto-create user if they are successfully authenticated via Firebase
        # but missing in the SQL database (e.g. after database migration or reset)
        email_clean = email.strip().lower()
        username = email_clean.split("@")[0]
        # Handle username clashes
        import time
        existing = db.query(models.User).filter(models.User.username == username).first()
        if existing:
            username = f"{username}_{int(time.time())}"
            
        full_name = payload.get("name", username.capitalize())
        
        user = models.User(
            username=username,
            full_name=full_name,
            email=email_clean,
            firebase_uid=firebase_uid,
            role="user"
        )
        db.add(user)
        db.flush()
        
        # Initialize Progress & Scores
        progress = models.UserProgress(
            user_id=user.id,
            current_active_task_id="daily_showroom_footfall",
            beginner_unlocked=True,
            intermediate_unlocked=False,
            advanced_unlocked=False
        )
        db.add(progress)
        
        score = models.Score(
            user_id=user.id,
            total_points=0,
            failed_attempts_count=0
        )
        db.add(score)
        db.commit()
        db.refresh(user)
        
    if not user:
        raise HTTPException(
            status_code=403,
            detail="Your email is not registered. Please complete the sign-up form first."
        )
        
    # Resolve redirect task
    redirect_task = "daily_showroom_footfall"
    if user.role == "user" and user.progress:
        redirect_task = user.progress.current_active_task_id or "completed"
        
    return {
        "access_token": firebase_token, # Send firebase token back as the token!
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "active_task_id": redirect_task
        }
    }

@app.get("/api/users/me")
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    """Fetches user details and current active progress state."""
    progress_data = None
    points = 0
    
    if current_user.role == "user":
        if current_user.progress:
            progress_data = {
                "last_completed_task_id": current_user.progress.last_completed_task_id,
                "current_active_task_id": current_user.progress.current_active_task_id or "completed",
                "beginner_unlocked": current_user.progress.beginner_unlocked,
                "intermediate_unlocked": current_user.progress.intermediate_unlocked,
                "advanced_unlocked": current_user.progress.advanced_unlocked
            }
        if current_user.score:
            points = current_user.score.total_points
            
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "progress": progress_data,
        "total_points": points
    }

# ==============================================================================
# PROGRESS & CURRICULUM ENDPOINTS
# ==============================================================================

@app.get("/api/tasks/active")
def get_active_task(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Resolves detailed active task data for standard users."""
    if current_user.role != "user":
        raise HTTPException(status_code=400, detail="Only standard users have training tasks.")
        
    active_id = current_user.progress.current_active_task_id
    if not active_id or active_id == "completed":
        return {"status": "completed", "message": "Congratulations! You have completed the entire training curriculum."}
        
    task = db.query(models.Task).filter(models.Task.id == active_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Active task not found in database.")
        
    # Get previous attempts
    attempts = db.query(models.Attempt).filter(
        models.Attempt.user_id == current_user.id,
        models.Attempt.task_id == active_id
    ).order_index = models.Attempt.created_at.desc()
    
    attempt_count = db.query(models.Attempt).filter(
        models.Attempt.user_id == current_user.id,
        models.Attempt.task_id == active_id
    ).count()
    
    return {
        "status": "active",
        "task_id": task.id,
        "stage": task.stage,
        "title": task.title,
        "scenario_text": task.scenario_text,
        "download_template_name": task.download_template_name,
        "attempt_count": attempt_count,
        "required_functions_list": list(set([v.required_function for v in task.validations if v.required_function]))
    }

@app.get("/api/tasks/{task_id}/download")
def download_task_template(task_id: str, db: Session = Depends(get_db)):
    """Streams the raw Excel workbook source file."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Build filepath
    app_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(os.path.dirname(app_dir), "media", "templates", task.download_template_name)
    
    if not os.path.exists(file_path):
        # Programmatically re-generate if accidentally deleted
        seed.generate_excel_templates()
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Excel template file was not found on local disk")
            
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return FileResponse(
        path=file_path,
        filename=task.download_template_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )

@app.post("/api/tasks/{task_id}/submit")
async def submit_task_solution(
    task_id: str, 
    file: UploadFile = File(...), 
    current_user: models.User = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    """Handles Excel file upload, auto-grades, updates scoring & persistent locks."""
    if current_user.role != "user":
        raise HTTPException(status_code=400, detail="Only standard users can submit exercise solutions.")
        
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Security: Verify that user is actually unlocked for this task
    progress = current_user.progress
    if task.stage == "intermediate" and not progress.intermediate_unlocked:
        raise HTTPException(status_code=403, detail="Intermediate Stage is locked.")
    elif task.stage == "advanced" and not progress.advanced_unlocked:
        raise HTTPException(status_code=403, detail="Advanced Stage is locked.")
        
    # Read file bytes
    file_bytes = await file.read()
    
    # Grade workbook
    is_success, grader_errors = grader.grade_excel_file(file_bytes, task.validations)
    
    # Load attempt metrics
    failed_attempts_on_task = db.query(models.Attempt).filter(
        models.Attempt.user_id == current_user.id,
        models.Attempt.task_id == task_id,
        models.Attempt.status == "failed"
    ).count()
    
    attempt_num = failed_attempts_on_task + 1
    
    if not is_success:
        # 1. FAIL LOGIC
        # Save Attempt Record
        attempt = models.Attempt(
            user_id=current_user.id,
            task_id=task_id,
            attempt_number=attempt_num,
            status="failed",
            errors_json=json.dumps(grader_errors)
        )
        db.add(attempt)
        
        # Increment failed count in cache
        score_cache = current_user.score
        score_cache.failed_attempts_count += 1
        db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "failed",
                "message": "Calculations failed. Let's fix the cells highlighted in red below and try again!",
                "attempt_number": attempt_num,
                "errors": grader_errors
            }
        )
    else:
        # 2. SUCCESS LOGIC
        # Verify if they had already passed earlier (no double points!)
        already_passed = db.query(models.Attempt).filter(
            models.Attempt.user_id == current_user.id,
            models.Attempt.task_id == task_id,
            models.Attempt.status == "passed"
        ).count() > 0
        
        points_awarded = 0
        is_first_try = (failed_attempts_on_task == 0)
        
        if not already_passed:
            points_awarded = 100
            if is_first_try:
                points_awarded += 25  # First try bonus!
                
            # Update points inside scores cache
            score_cache = current_user.score
            score_cache.total_points += points_awarded
            
        # Log successful attempt
        attempt = models.Attempt(
            user_id=current_user.id,
            task_id=task_id,
            attempt_number=attempt_num,
            status="passed"
        )
        db.add(attempt)
        
        # Unlock next tasks
        next_active_task_id = "completed"
        progress.last_completed_task_id = task_id
        
        if task_id in TASK_SEQUENCE:
            idx = TASK_SEQUENCE.index(task_id)
            if idx + 1 < len(TASK_SEQUENCE):
                next_active_task_id = TASK_SEQUENCE[idx + 1]
                progress.current_active_task_id = next_active_task_id
                
                # Check if we should unlock stage transitions automatically
                if next_active_task_id == "monthly_sales_commission":
                    progress.intermediate_unlocked = True
                elif next_active_task_id == "dealership_profitability":
                    progress.advanced_unlocked = True
            else:
                progress.current_active_task_id = "completed"
                next_active_task_id = "completed"
        else:
            progress.current_active_task_id = "completed"
            next_active_task_id = "completed"
            
        db.commit()
        
        return {
            "status": "passed",
            "message": "Perfect! Your financial model calculated 100% correct values using required formulas.",
            "points_awarded": points_awarded,
            "is_first_try": is_first_try,
            "next_task_id": next_active_task_id
        }

# ==============================================================================
# LEADERBOARD & ANNOUNCEMENTS
# ==============================================================================

@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """Fetches high-score dashboard list. Standard users ranked strictly by score then fail-attempts."""
    # Rank users strictly by total points.
    # In event of a tie, rank user with fewer total failed attempts HIGHER.
    results = db.query(models.User, models.Score).join(
        models.Score, models.User.id == models.Score.user_id
    ).filter(models.User.role == "user").all()
    
    # Sort in python for precise tied criteria:
    # Points DESC (primary), FailedAttempts ASC (secondary)
    sorted_results = sorted(
        results,
        key=lambda x: (-x[1].total_points, x[1].failed_attempts_count)
    )
    
    leaderboard = []
    for idx, (user, score) in enumerate(sorted_results, 1):
        # Security: Do not display failure counts on public leaderboard
        leaderboard.append({
            "rank": idx,
            "user_id": user.id,
            "full_name": user.full_name,
            "total_points": score.total_points,
            # Implicit sort handles ties. No fails count sent in public endpoint!
        })
        
    return leaderboard

@app.get("/api/announcements")
def get_announcements(db: Session = Depends(get_db)):
    """Fetches active training announcements."""
    announcement = db.query(models.Announcement).order_by(models.Announcement.created_at.desc()).first()
    if announcement:
        return {"content": announcement.content, "created_at": announcement.created_at}
    return {"content": None}

# ==============================================================================
# ADMINISTRATIVE CONTROL PANELS
# ==============================================================================

@app.get("/api/admin/metrics")
def get_admin_metrics(current_admin: models.User = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    """Calculates administrative high-level stats."""
    total_users = db.query(models.User).filter(models.User.role == "user").count()
    total_attempts = db.query(models.Attempt).count()
    passed_attempts = db.query(models.Attempt).filter(models.Attempt.status == "passed").count()
    
    pass_rate = 0.0
    if total_attempts > 0:
        pass_rate = round((passed_attempts / total_attempts) * 100, 1)
        
    return {
        "total_users": total_users,
        "total_attempts": total_attempts,
        "pass_rate": pass_rate
    }

@app.get("/api/admin/users-progress")
def get_admin_users_progress(current_admin: models.User = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    """List of all student progress cards and attempts log ledger for administration."""
    users = db.query(models.User).filter(models.User.role == "user").all()
    
    progress_list = []
    for user in users:
        # Collect attempts stats per task
        attempts_summary = {}
        for task_id in ["daily_showroom_footfall", "monthly_sales_commission", "dealership_profitability"]:
            fails = db.query(models.Attempt).filter(
                models.Attempt.user_id == user.id,
                models.Attempt.task_id == task_id,
                models.Attempt.status == "failed"
            ).count()
            passed = db.query(models.Attempt).filter(
                models.Attempt.user_id == user.id,
                models.Attempt.task_id == task_id,
                models.Attempt.status == "passed"
            ).count() > 0
            
            attempts_summary[task_id] = {
                "failed_attempts": fails,
                "passed": passed
            }
            
        progress_list.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "total_points": user.score.total_points if user.score else 0,
            "current_active_task": user.progress.current_active_task_id if user.progress else "daily_showroom_footfall",
            "attempts_summary": attempts_summary
        })
        
    return progress_list

@app.post("/api/admin/announcement")
def post_admin_announcement(
    content: str = Form(...),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Allows administrators to post global training notifications."""
    content_str = content.strip()
    if not content_str:
        raise HTTPException(status_code=400, detail="Announcement content cannot be empty.")
        
    ann = models.Announcement(content=content_str)
    db.add(ann)
    db.commit()
    
    return {"message": "Announcement posted successfully!", "content": content_str}

@app.post("/api/admin/upload-task")
async def admin_upload_task(
    id: str = Form(...),
    stage: str = Form(...),
    title: str = Form(...),
    scenario_text: str = Form(...),
    validations_json: str = Form(...), # JSON Array containing cell reference, expected val, func check
    file: Optional[UploadFile] = File(None),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    """Allows administrators to upload or update standard tasks."""
    task_id = id.strip().lower()
    
    # Save file if provided
    filename = f"{task_id}.xlsx"
    if file:
        filename = file.filename
        app_dir = os.path.dirname(os.path.abspath(__file__))
        media_dir = os.path.join(os.path.dirname(app_dir), "media", "templates")
        os.makedirs(media_dir, exist_ok=True)
        file_path = os.path.join(media_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
    # Check if task already exists
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        task = models.Task(
            id=task_id,
            stage=stage.strip(),
            title=title.strip(),
            scenario_text=scenario_text.strip(),
            download_template_name=filename
        )
        db.add(task)
        db.flush()
    else:
        # Update existing
        task.stage = stage.strip()
        task.title = title.strip()
        task.scenario_text = scenario_text.strip()
        task.download_template_name = filename
        
    # Delete old validations
    db.query(models.TaskValidation).filter(models.TaskValidation.task_id == task_id).delete()
    
    # Add new validations
    vals = json.loads(validations_json)
    for v in vals:
        val = models.TaskValidation(
            task_id=task_id,
            cell_reference=v["cell_reference"].strip(),
            expected_value=str(v["expected_value"]).strip(),
            required_function=v.get("required_function", "").strip(),
            is_financial=bool(v.get("is_financial", False)),
            is_date=bool(v.get("is_date", False)),
            correct_formula_hint=v.get("correct_formula_hint", "").strip()
        )
        db.add(val)
        
    db.commit()
    return {"message": f"Task '{task.title}' updated successfully!"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "finance-excel-training-api"}

@app.get("/api/db-status")
def db_status():
    import os
    from .database import DATABASE_URL
    db_type = "postgresql" if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres") else "sqlite"
    return {
        "database_type": db_type,
        "is_postgres": db_type == "postgresql",
        "url_configured": bool(os.getenv("DATABASE_URL"))
    }

# ==============================================================================
# STATIC FILES SERVING & MOUNTING
# ==============================================================================
app_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(os.path.dirname(app_dir), "static")

# Proactively check and mount static files if directory exists
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    @app.get("/")
    def index():
        return {
            "message": "Welcome to the Finance Excel Training API. React frontend static assets are not built yet.",
            "status": "running"
        }
