from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import Base, engine, get_db
from .models import Comment, Issue, User, utc_now
from .schemas import (
    CommentCreate,
    CommentRead,
    IssueCreate,
    IssueRead,
    IssueUpdate,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
)


ALLOWED_STATUSES = {"open", "in_progress", "testing", "resolved"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="BugTrack Pro API",
    description="A portfolio-ready issue tracking platform built with Python and FastAPI.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "bugtrack-pro"}


@app.post("/api/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(name=payload.name.strip(), email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=UserSummary.model_validate(user))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id), user=UserSummary.model_validate(user))


@app.get("/api/me", response_model=UserSummary)
def me(current_user: User = Depends(get_current_user)) -> UserSummary:
    return UserSummary.model_validate(current_user)


@app.get("/api/users", response_model=list[UserSummary])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.name)).all())


def issue_query():
    return select(Issue).options(
        joinedload(Issue.reporter),
        joinedload(Issue.assignee),
        joinedload(Issue.comments).joinedload(Comment.author),
    )


@app.get("/api/issues", response_model=list[IssueRead])
def list_issues(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Issue]:
    query = issue_query().order_by(Issue.updated_at.desc())
    if status_filter:
        query = query.where(Issue.status == status_filter)
    if priority:
        query = query.where(Issue.priority == priority)
    if q:
        search = f"%{q.strip()}%"
        query = query.where(or_(Issue.title.ilike(search), Issue.description.ilike(search)))
    return list(db.scalars(query).unique().all())


@app.post("/api/issues", response_model=IssueRead, status_code=status.HTTP_201_CREATED)
def create_issue(
    payload: IssueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Issue:
    validate_priority(payload.priority)
    assignee = get_assignee(payload.assignee_id, db)
    issue = Issue(
        title=payload.title.strip(),
        description=payload.description.strip(),
        priority=payload.priority,
        reporter_id=current_user.id,
        assignee=assignee,
    )
    db.add(issue)
    db.commit()
    return load_issue(issue.id, db)


@app.get("/api/issues/{issue_id}", response_model=IssueRead)
def get_issue(issue_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Issue:
    return load_issue(issue_id, db)


@app.patch("/api/issues/{issue_id}", response_model=IssueRead)
def update_issue(
    issue_id: int,
    payload: IssueUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Issue:
    issue = load_issue(issue_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        validate_status(changes["status"])
    if "priority" in changes:
        validate_priority(changes["priority"])
    if "assignee_id" in changes:
        issue.assignee = get_assignee(changes.pop("assignee_id"), db)
    for field, value in changes.items():
        setattr(issue, field, value.strip() if isinstance(value, str) else value)
    issue.updated_at = utc_now()
    db.commit()
    return load_issue(issue.id, db)


@app.delete("/api/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(issue_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> None:
    issue = load_issue(issue_id, db)
    db.delete(issue)
    db.commit()


@app.post("/api/issues/{issue_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
def add_comment(
    issue_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Comment:
    issue = load_issue(issue_id, db)
    comment = Comment(body=payload.body.strip(), issue_id=issue.id, author_id=current_user.id)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return db.scalar(
        select(Comment).options(joinedload(Comment.author)).where(Comment.id == comment.id)
    )


def validate_status(value: str) -> None:
    if value not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")


def validate_priority(value: str) -> None:
    if value not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Priority must be one of: {', '.join(sorted(ALLOWED_PRIORITIES))}")


def get_assignee(assignee_id: int | None, db: Session) -> User | None:
    if assignee_id is None:
        return None
    assignee = db.get(User, assignee_id)
    if assignee is None:
        raise HTTPException(status_code=422, detail="Assignee does not exist")
    return assignee


def load_issue(issue_id: int, db: Session) -> Issue:
    issue = db.execute(issue_query().where(Issue.id == issue_id)).unique().scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue

