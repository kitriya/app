import os
import re
import uuid
from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from markupsafe import Markup, escape

from models import (
    Base, engine, get_db, User, Post, Like, Comment, CommentLike,
    Save, Message, Notification, Report, Draft,
)
from auth import hash_password, verify_password

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lufrica")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "change-this-secret-key"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")


def extract_hashtags(text):
    if not text:
        return set()
    return {t.lower() for t in HASHTAG_RE.findall(text)}


def extract_mentions(text):
    if not text:
        return set()
    return set(MENTION_RE.findall(text))


def linkify_caption(text):
    if not text:
        return ""
    escaped = str(escape(text))
    escaped = HASHTAG_RE.sub(r'<a href="/hashtag/\1" style="color:#3E8E8A;">#\1</a>', escaped)
    escaped = MENTION_RE.sub(r'<a href="/profile/\1" style="color:#3E8E8A;">@\1</a>', escaped)
    return Markup(escaped)


templates.env.filters["linkify"] = linkify_caption


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def render(request, name, db, active_tab=None, **kwargs):
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(name, {
        "request": request,
        "current_user": current_user,
        "active_tab": active_tab,
        **kwargs,
    })


@app.get("/")
def root(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/feed")
    return RedirectResponse("/login")


# ============ AUTH ============

@app.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "login.html", db)


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return render(request, "login.html", db, error="Wrong email or password.")
    request.session["user_id"] = user.id
    return RedirectResponse("/feed", status_code=303)


@app.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "register.html", db)


@app.post("/register")
def register_submit(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    exists = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if exists:
        return render(request, "register.html", db, error="Username or email taken.")
    user = User(username=username, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/feed", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ============ FEED ============

@app.get("/feed")
def feed(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    following_ids = [u.id for u in current_user.following]
    muted_ids = {u.id for u in current_user.muted_users}

    candidates = db.query(Post).filter(
        or_(Post.user_id.in_(following_ids), Post.user_id == current_user.id),
        Post.archived == False,
    ).order_by(desc(Post.created_at)).limit(120).all()

    close_friend_cache = {}
    posts = []
    for post in candidates:
        if post.user_id in muted_ids:
            continue
        if post.user_id != current_user.id and post.visibility == "close_friends":
            if post.user_id not in close_friend_cache:
                close_friend_cache[post.user_id] = {u.id for u in post.author.close_friends}
            if current_user.id not in close_friend_cache[post.user_id]:
                continue
        posts.append(post)
        if len(posts) >= 50:
            break

    liked_ids = {like.post_id for like in current_user.likes}
    saved_ids = {save.post_id for save in current_user.saves}

    return render(request, "feed.html", db, active_tab="feed", posts=posts, liked_ids=liked_ids, saved_ids=saved_ids)


# ============ EXPLORE, SEARCH, HASHTAGS ============

@app.get("/explore")
def explore(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    recent_posts = db.query(Post).filter(Post.archived == False).order_by(desc(Post.created_at)).limit(200).all()
    tag_counter = Counter()
    for p in recent_posts:
        tag_counter.update(extract_hashtags(p.caption))
    trending_tags = tag_counter.most_common(8)

    trending = db.query(Post).filter(Post.archived == False).order_by(desc(Post.likes_count)).limit(21).all()
    suggested = db.query(User).filter(~User.followers.any(id=current_user.id), User.id != current_user.id).limit(6).all()

    return render(request, "explore.html", db, active_tab="explore", trending=trending, suggested=suggested, trending_tags=trending_tags)


@app.get("/search")
def search(request: Request, q: str = "", db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    users = db.query(User).filter(User.username.ilike(f"%{q}%")).limit(20).all() if q else []
    posts = db.query(Post).filter(Post.caption.ilike(f"%{q}%")).limit(20).all() if q else []

    return render(request, "search.html", db, active_tab="explore", query=q, users=users, posts=posts)


@app.get("/hashtag/{tag}")
def hashtag_page(tag: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    tag = tag.lower()
    candidates = db.query(Post).filter(Post.archived == False).order_by(desc(Post.created_at)).limit(300).all()
    posts = [p for p in candidates if tag in extract_hashtags(p.caption)]

    return render(request, "hashtag.html", db, active_tab="explore", tag=tag, posts=posts)


# ============ POST DETAIL ============

@app.get("/post/{post_id}")
def post_detail(post_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        return render(request, "error.html", db, error="Post not found.")

    liked_ids = {like.post_id for like in current_user.likes}
    saved_ids = {save.post_id for save in current_user.saves}
    comment_liked_ids = {cl.comment_id for cl in current_user.comment_likes}

    return render(request, "post_detail.html", db, active_tab="feed", post=post,
                 liked_ids=liked_ids, saved_ids=saved_ids, comment_liked_ids=comment_liked_ids)


# ============ CREATE ============

@app.get("/create")
def create_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    drafts = db.query(Draft).filter(Draft.user_id == current_user.id).all()
    return render(request, "create.html", db, active_tab="create", drafts=drafts)


@app.post("/create")
async def create_submit(
    request: Request, media_type: str = Form(...), caption: str = Form(""), location: str = Form(""),
    visibility: str = Form("public"), filter_name: str = Form("none"), alt_text: str = Form(""),
    media: list[UploadFile] = File(default=[]), draft_id: Optional[int] = Form(None), db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_count = db.query(Post).filter(Post.user_id == current_user.id, Post.created_at >= one_hour_ago).count()
    if recent_count >= 20:
        drafts = db.query(Draft).filter(Draft.user_id == current_user.id).all()
        return render(request, "create.html", db, active_tab="create", drafts=drafts, error="You're posting quickly — try again in a bit.")

    media_paths = []
    for file in media:
        if file.filename:
            ext = os.path.splitext(file.filename)[1] or (".mp4" if media_type == "reel" else ".jpg")
            filename = f"{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / filename
            with open(dest, "wb") as f:
                f.write(await file.read())
            media_paths.append(f"/static/uploads/{filename}")

    if draft_id:
        db.query(Draft).filter(Draft.id == draft_id).delete()

    post = Post(
        user_id=current_user.id, media_type=media_type, media_paths=media_paths, caption=caption,
        location=location, visibility=visibility, filter_name=filter_name, alt_text=alt_text,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    for username in extract_mentions(caption):
        mentioned = db.query(User).filter(User.username == username).first()
        if mentioned and mentioned.id != current_user.id:
            db.add(Notification(user_id=mentioned.id, actor_id=current_user.id, notification_type="mention", post_id=post.id, body=f"{current_user.username} mentioned you in a post"))
    db.commit()

    return RedirectResponse("/feed", status_code=303)


@app.post("/draft")
async def save_draft(request: Request, caption: str = Form(""), media: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    media_paths = []
    for file in media:
        if file.filename:
            ext = os.path.splitext(file.filename)[1] or ".jpg"
            filename = f"{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / filename
            with open(dest, "wb") as f:
                f.write(await file.read())
            media_paths.append(f"/static/uploads/{filename}")

    db.add(Draft(user_id=current_user.id, media_paths=media_paths, caption=caption))
    db.commit()

    return RedirectResponse("/create", status_code=303)


# ============ REELS ============

@app.get("/reels")
def reels(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    posts = db.query(Post).filter(Post.media_type == "reel", Post.archived == False).order_by(desc(Post.created_at)).limit(50).all()
    liked_ids = {like.post_id for like in current_user.likes}

    return render(request, "reels.html", db, active_tab="reels", posts=posts, liked_ids=liked_ids)


# ============ INTERACTIONS ============

@app.post("/like/{post_id}")
def like_post(post_id: int, request: Request, reaction: str = Form("heart"), next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    existing = db.query(Like).filter(Like.user_id == current_user.id, Like.post_id == post_id).first()
    post = db.query(Post).filter(Post.id == post_id).first()

    if existing:
        db.delete(existing)
        if post:
            post.likes_count = max(0, post.likes_count - 1)
    else:
        db.add(Like(user_id=current_user.id, post_id=post_id, reaction=reaction))
        if post:
            post.likes_count += 1
            if post.user_id != current_user.id:
                db.add(Notification(user_id=post.user_id, actor_id=current_user.id, notification_type="like", post_id=post_id, body=f"{current_user.username} liked your post"))

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/comment/{post_id}")
def comment_post(post_id: int, request: Request, body: str = Form(...), next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    if body.strip():
        comment = Comment(post_id=post_id, user_id=current_user.id, body=body.strip())
        db.add(comment)

        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.comments_count += 1
            if post.user_id != current_user.id:
                db.add(Notification(user_id=post.user_id, actor_id=current_user.id, notification_type="comment", post_id=post_id, body=f"{current_user.username} commented: {body[:50]}"))

        for username in extract_mentions(body):
            mentioned = db.query(User).filter(User.username == username).first()
            if mentioned and mentioned.id != current_user.id:
                db.add(Notification(user_id=mentioned.id, actor_id=current_user.id, notification_type="mention", post_id=post_id, body=f"{current_user.username} mentioned you in a comment"))

        db.commit()

    return RedirectResponse(next, status_code=303)


@app.post("/comment-like/{comment_id}")
def comment_like(comment_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    existing = db.query(CommentLike).filter(CommentLike.user_id == current_user.id, CommentLike.comment_id == comment_id).first()

    if existing:
        db.delete(existing)
        if comment:
            comment.likes_count = max(0, comment.likes_count - 1)
    else:
        db.add(CommentLike(user_id=current_user.id, comment_id=comment_id))
        if comment:
            comment.likes_count += 1

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/save/{post_id}")
def save_post(post_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    existing = db.query(Save).filter(Save.user_id == current_user.id, Save.post_id == post_id).first()
    if existing:
        db.delete(existing)
    else:
        db.add(Save(user_id=current_user.id, post_id=post_id))

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/repost/{post_id}")
def repost(post_id: int, request: Request, caption: str = Form(""), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    original = db.query(Post).filter(Post.id == post_id).first()
    if not original:
        return RedirectResponse("/feed", status_code=303)

    new_post = Post(user_id=current_user.id, media_type=original.media_type, media_paths=[], caption=caption, shared_from_id=original.id)
    db.add(new_post)
    db.commit()

    if original.user_id != current_user.id:
        db.add(Notification(user_id=original.user_id, actor_id=current_user.id, notification_type="repost", post_id=original.id, body=f"{current_user.username} reposted your post"))
        db.commit()

    return RedirectResponse("/feed", status_code=303)


@app.post("/pin/{post_id}")
def pin_post(post_id: int, request: Request, next: str = Form("/profile"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    post = db.query(Post).filter(Post.id == post_id, Post.user_id == current_user.id).first()
    if post:
        if post.pinned:
            post.pinned = False
        else:
            db.query(Post).filter(Post.user_id == current_user.id, Post.pinned == True).update({"pinned": False})
            post.pinned = True
        db.commit()

    return RedirectResponse(next, status_code=303)


@app.post("/archive/{post_id}")
def archive_post(post_id: int, request: Request, next: str = Form("/profile"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    post = db.query(Post).filter(Post.id == post_id, Post.user_id == current_user.id).first()
    if post:
        post.archived = not post.archived
        db.commit()

    return RedirectResponse(next, status_code=303)


@app.post("/delete-post/{post_id}")
def delete_post(post_id: int, request: Request, next: str = Form("/profile"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    post = db.query(Post).filter(Post.id == post_id, Post.user_id == current_user.id).first()
    if post:
        db.delete(post)
        db.commit()

    return RedirectResponse(next, status_code=303)


# ============ FOLLOW / BLOCK / MUTE / CLOSE FRIENDS ============

@app.post("/follow/{user_id}")
def follow_user(user_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.id == user_id:
        return RedirectResponse("/login")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(next, status_code=303)

    if target in current_user.following:
        current_user.following.remove(target)
    else:
        current_user.following.append(target)
        db.add(Notification(user_id=target.id, actor_id=current_user.id, notification_type="follow", body=f"{current_user.username} followed you"))

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/block/{user_id}")
def block_user(user_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.id == user_id:
        return RedirectResponse("/login")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(next, status_code=303)

    if target in current_user.blocked_users:
        current_user.blocked_users.remove(target)
    else:
        current_user.blocked_users.append(target)

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/mute/{user_id}")
def mute_user(user_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.id == user_id:
        return RedirectResponse("/login")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(next, status_code=303)

    if target in current_user.muted_users:
        current_user.muted_users.remove(target)
    else:
        current_user.muted_users.append(target)

    db.commit()
    return RedirectResponse(next, status_code=303)


@app.post("/close-friend/{user_id}")
def toggle_close_friend(user_id: int, request: Request, next: str = Form("/feed"), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.id == user_id:
        return RedirectResponse("/login")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(next, status_code=303)

    if target in current_user.close_friends:
        current_user.close_friends.remove(target)
    else:
        current_user.close_friends.append(target)

    db.commit()
    return RedirectResponse(next, status_code=303)


# ============ PROFILE ============

@app.get("/profile/{username}")
def profile(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return render(request, "error.html", db, error="User not found.")

    is_owner = user.id == current_user.id
    can_view = is_owner or not user.is_private or user in current_user.following

    posts = []
    if can_view:
        all_posts = db.query(Post).filter(Post.user_id == user.id, Post.archived == False).order_by(desc(Post.created_at)).all()
        posts = [p for p in all_posts if p.pinned] + [p for p in all_posts if not p.pinned]

    return render(
        request, "profile.html", db, active_tab="profile", profile_user=user, posts=posts,
        is_owner=is_owner, is_following=user in current_user.following,
        is_muted=user in current_user.muted_users, is_close_friend=user in current_user.close_friends,
        followers_count=len(user.followers), following_count=len(user.following),
    )


@app.get("/profile")
def my_profile(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    return RedirectResponse(f"/profile/{current_user.username}")


@app.get("/profile/{username}/followers")
def followers_list(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return render(request, "error.html", db, error="User not found.")
    return render(request, "followlist.html", db, active_tab="profile", title="Followers", people=user.followers, profile_user=user)


@app.get("/profile/{username}/following")
def following_list(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return render(request, "error.html", db, error="User not found.")
    return render(request, "followlist.html", db, active_tab="profile", title="Following", people=user.following, profile_user=user)


@app.get("/edit-profile")
def edit_profile_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    return render(request, "edit-profile.html", db, active_tab="profile")


@app.post("/edit-profile")
async def edit_profile_submit(
    request: Request, bio: str = Form(""), website: str = Form(""), is_private: bool = Form(False),
    theme_color: str = Form("#D4A017"), profile_pic: UploadFile = File(None), banner: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    current_user.bio = bio
    current_user.website = website
    current_user.is_private = is_private
    current_user.theme_color = theme_color

    if profile_pic and profile_pic.filename:
        filename = f"pfp_{uuid.uuid4().hex}.jpg"
        dest = UPLOAD_DIR / filename
        with open(dest, "wb") as f:
            f.write(await profile_pic.read())
        current_user.profile_pic = f"/static/uploads/{filename}"

    if banner and banner.filename:
        filename = f"banner_{uuid.uuid4().hex}.jpg"
        dest = UPLOAD_DIR / filename
        with open(dest, "wb") as f:
            f.write(await banner.read())
        current_user.banner = f"/static/uploads/{filename}"

    db.commit()
    return RedirectResponse(f"/profile/{current_user.username}", status_code=303)


# ============ ACCOUNT SETTINGS ============

@app.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")
    return render(request, "settings.html", db, active_tab="profile")


@app.post("/settings/password")
def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    if not verify_password(current_password, current_user.password_hash):
        return render(request, "settings.html", db, active_tab="profile", error="Current password is wrong.")

    current_user.password_hash = hash_password(new_password)
    db.commit()
    return render(request, "settings.html", db, active_tab="profile", success="Password updated.")


@app.post("/settings/delete-account")
def delete_account(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    if not verify_password(password, current_user.password_hash):
        return render(request, "settings.html", db, active_tab="profile", error="Wrong password — account not deleted.")

    db.delete(current_user)
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ============ MESSAGES ============

@app.get("/messages")
def messages(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    conversations = db.query(User).join(
        Message, or_(Message.sender_id == current_user.id, Message.recipient_id == current_user.id)
    ).filter(User.id != current_user.id).distinct().all()

    unread = db.query(Message).filter(Message.recipient_id == current_user.id, Message.is_read == False).count()

    return render(request, "messages.html", db, active_tab="messages", conversations=conversations, unread_count=unread)


@app.get("/dm/{username}")
def dm(username: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    other_user = db.query(User).filter(User.username == username).first()
    if not other_user:
        return render(request, "error.html", db, error="User not found.")

    db.query(Message).filter(Message.recipient_id == current_user.id, Message.sender_id == other_user.id).update({"is_read": True})

    msgs = db.query(Message).filter(
        or_(
            (Message.sender_id == current_user.id) & (Message.recipient_id == other_user.id),
            (Message.sender_id == other_user.id) & (Message.recipient_id == current_user.id),
        )
    ).order_by(Message.created_at).limit(50).all()

    db.commit()
    return render(request, "dm.html", db, active_tab="messages", other_user=other_user, messages=msgs)


@app.post("/send-message/{user_id}")
def send_message(user_id: int, request: Request, body: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    recipient = db.query(User).filter(User.id == user_id).first()
    if not recipient:
        return RedirectResponse("/messages")

    if body.strip():
        db.add(Message(sender_id=current_user.id, recipient_id=user_id, body=body.strip()))
        db.commit()

    return RedirectResponse(f"/dm/{recipient.username}", status_code=303)


# ============ NOTIFICATIONS ============

@app.get("/notifications")
def notifications(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    notifs = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(desc(Notification.created_at)).limit(50).all()
    db.query(Notification).filter(Notification.user_id == current_user.id).update({"is_read": True})
    db.commit()

    return render(request, "notifications.html", db, active_tab="notifications", notifications=notifs)


# ============ BOOKMARKS ============

@app.get("/bookmarks")
def bookmarks(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    saved_posts = db.query(Post).join(Save).filter(Save.user_id == current_user.id).order_by(desc(Save.created_at)).all()
    liked_ids = {like.post_id for like in current_user.likes}
    saved_ids = {save.post_id for save in current_user.saves}

    return render(request, "bookmarks.html", db, active_tab="bookmarks", posts=saved_posts, liked_ids=liked_ids, saved_ids=saved_ids)


# ============ REPORTS ============

@app.post("/report/{post_id}")
def report_post(post_id: int, request: Request, reason: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    post = db.query(Post).filter(Post.id == post_id).first()
    if post:
        db.add(Report(reporter_id=current_user.id, post_id=post_id, reason=reason))
        db.commit()

    return RedirectResponse("/feed", status_code=303)


@app.post("/report-user/{user_id}")
def report_user(user_id: int, request: Request, reason: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse("/login")

    target = db.query(User).filter(User.id == user_id).first()
    if target:
        db.add(Report(reporter_id=current_user.id, reported_user_id=user_id, reason=reason))
        db.commit()

    return RedirectResponse(f"/profile/{target.username}" if target else "/feed", status_code=303)
