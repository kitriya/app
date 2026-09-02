import os
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Boolean,
    UniqueConstraint, create_engine, Table, JSON
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://lufrica_user:password@localhost/lufrica",
)

# Railway's MySQL plugin (and most hosts) hand you a plain "mysql://..." URL.
# SQLAlchemy needs the driver named explicitly, so normalize it here —
# this way whatever DATABASE_URL Railway injects just works.
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def fk(target, nullable=True):
    return Column(Integer, ForeignKey(target, ondelete="CASCADE"), nullable=nullable)


# Association tables (all cascade at the DB level so account deletion is clean)
follows = Table(
    "follows", Base.metadata,
    Column("follower_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("following_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

blocks = Table(
    "blocks", Base.metadata,
    Column("blocker_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("blocked_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

mutes = Table(
    "mutes", Base.metadata,
    Column("muter_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("muted_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

close_friends = Table(
    "close_friends", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("friend_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    bio = Column(String(500), default="")
    profile_pic = Column(String(255), default="")
    banner = Column(String(255), default="")
    website = Column(String(255), default="")
    verified = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)
    theme_color = Column(String(7), default="#D4A017")
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan", foreign_keys="Post.user_id")
    likes = relationship("Like", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    comment_likes = relationship("CommentLike", back_populates="user", cascade="all, delete-orphan")
    saves = relationship("Save", back_populates="user", cascade="all, delete-orphan")
    messages_sent = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id", cascade="all, delete-orphan")
    messages_received = relationship("Message", back_populates="recipient", foreign_keys="Message.recipient_id", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id", cascade="all, delete-orphan")

    following = relationship("User", secondary=follows, primaryjoin=id == follows.c.follower_id, secondaryjoin=id == follows.c.following_id, overlaps="followers")
    followers = relationship("User", secondary=follows, primaryjoin=id == follows.c.following_id, secondaryjoin=id == follows.c.follower_id, overlaps="following")
    blocked_users = relationship("User", secondary=blocks, primaryjoin=id == blocks.c.blocker_id, secondaryjoin=id == blocks.c.blocked_id)
    muted_users = relationship("User", secondary=mutes, primaryjoin=id == mutes.c.muter_id, secondaryjoin=id == mutes.c.muted_id)
    close_friends = relationship("User", secondary=close_friends, primaryjoin=id == close_friends.c.user_id, secondaryjoin=id == close_friends.c.friend_id)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    media_type = Column(String(10), nullable=False)  # photo, reel, carousel
    media_paths = Column(JSON, default=[])
    caption = Column(Text, default="")
    alt_text = Column(String(255), default="")
    location = Column(String(255), default="")
    filter_name = Column(String(20), default="none")  # none, noir, warm, fade, vivid
    visibility = Column(String(14), default="public")  # public, followers, close_friends
    pinned = Column(Boolean, default=False)
    archived = Column(Boolean, default=False)
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shared_from_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    edited_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    author = relationship("User", back_populates="posts", foreign_keys=[user_id])
    shared_from = relationship("Post", remote_side=[id])
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    saves = relationship("Save", back_populates="post", cascade="all, delete-orphan")


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_user_post_like"),)

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    post_id = fk("posts.id", nullable=False)
    reaction = Column(String(8), default="heart")  # heart, laugh, wow, sad, fire
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    post_id = fk("posts.id", nullable=False)
    user_id = fk("users.id", nullable=False)
    body = Column(String(500), nullable=False)
    likes_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")
    comment_likes = relationship("CommentLike", back_populates="comment", cascade="all, delete-orphan")


class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (UniqueConstraint("user_id", "comment_id", name="uq_user_comment_like"),)

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    comment_id = fk("comments.id", nullable=False)

    user = relationship("User", back_populates="comment_likes")
    comment = relationship("Comment", back_populates="comment_likes")


class Save(Base):
    __tablename__ = "saves"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_user_post_save"),)

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    post_id = fk("posts.id", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="saves")
    post = relationship("Post", back_populates="saves")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_id = fk("users.id", nullable=False)
    recipient_id = fk("users.id", nullable=False)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    sender = relationship("User", back_populates="messages_sent", foreign_keys=[sender_id])
    recipient = relationship("User", back_populates="messages_received", foreign_keys=[recipient_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    actor_id = fk("users.id", nullable=True)
    notification_type = Column(String(20), nullable=False)  # like, comment, follow, mention, repost
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    body = Column(String(255), nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
    actor = relationship("User", foreign_keys=[actor_id])


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    reporter_id = fk("users.id", nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    reported_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(String(255), nullable=False)
    status = Column(String(20), default="open")
    created_at = Column(DateTime, default=datetime.utcnow)


class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True)
    user_id = fk("users.id", nullable=False)
    media_paths = Column(JSON, default=[])
    caption = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
