from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    reported_issues: Mapped[list["Issue"]] = relationship(
        back_populates="reporter", foreign_keys="Issue.reporter_id"
    )
    assigned_issues: Mapped[list["Issue"]] = relationship(
        back_populates="assignee", foreign_keys="Issue.assignee_id"
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium", index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    reporter: Mapped[User] = relationship(
        back_populates="reported_issues", foreign_keys=[reporter_id]
    )
    assignee: Mapped[User | None] = relationship(
        back_populates="assigned_issues", foreign_keys=[assignee_id]
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="Comment.created_at"
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    issue: Mapped[Issue] = relationship(back_populates="comments")
    author: Mapped[User] = relationship(back_populates="comments")
