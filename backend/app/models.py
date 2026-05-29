import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    role = Column(String, default="user")  # 'admin' or 'user'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    progress = relationship("UserProgress", back_populates="user", uselist=False)
    score = relationship("Score", back_populates="user", uselist=False)
    attempts = relationship("Attempt", back_populates="user")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)  # e.g., 'daily_showroom_footfall'
    stage = Column(String, nullable=False)  # 'beginner', 'intermediate', 'advanced'
    title = Column(String, nullable=False)
    scenario_text = Column(Text, nullable=False)
    download_template_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    validations = relationship("TaskValidation", back_populates="task", cascade="all, delete-orphan")
    attempts = relationship("Attempt", back_populates="task")

class TaskValidation(Base):
    __tablename__ = "task_validations"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    cell_reference = Column(String, nullable=False)  # e.g., 'B11'
    expected_value = Column(String, nullable=False)  # e.g., '185' or '4.57'
    required_function = Column(String, nullable=True)  # e.g., 'SUM', 'VLOOKUP'
    is_financial = Column(Boolean, default=False)
    is_date = Column(Boolean, default=False)
    correct_formula_hint = Column(String, nullable=True)  # e.g., '=SUM(B4:B10)'

    task = relationship("Task", back_populates="validations")

class UserProgress(Base):
    __tablename__ = "user_progress"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    last_completed_task_id = Column(String, ForeignKey("tasks.id"), nullable=True)
    current_active_task_id = Column(String, ForeignKey("tasks.id"), nullable=True)
    beginner_unlocked = Column(Boolean, default=True)
    intermediate_unlocked = Column(Boolean, default=False)
    advanced_unlocked = Column(Boolean, default=False)

    user = relationship("User", back_populates="progress")

class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # 'failed', 'passed'
    errors_json = Column(Text, nullable=True)  # JSON string of failed validations
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="attempts")
    task = relationship("Task", back_populates="attempts")

class Score(Base):
    __tablename__ = "scores"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    total_points = Column(Integer, default=0)
    failed_attempts_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="score")

class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
