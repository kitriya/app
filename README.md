# Lufrica

A Python (FastAPI) social app backed by MySQL/MariaDB.

## Features

**Core**
- Login / register / logout with hashed passwords
- Feed showing posts from people you follow
- Photo posts, carousels (swipeable multi-photo), and reels (video)
- Likes, comments, comment likes, saves/bookmarks
- Post detail page with full comment thread

**Discovery**
- Hashtags — clickable, with a trending list on Explore
- @mentions in captions and comments (notify the mentioned user)
- Explore page: trending posts + suggested accounts
- Search for users and posts

**Social graph**
- Follow / unfollow, block, mute (mute hides posts without unfollowing)
- Close friends list + a "close friends only" post visibility option
- Followers / following list pages
- Direct messages between users
- Notifications for likes, comments, follows, mentions, and reposts

**Posts**
- Per-post visibility: public / followers only / close friends
- Photo filters (Noir, Warm, Fade, Vivid) with live preview before posting
- Alt text field for accessibility
- Pin one post to the top of your profile
- Archive a post (hides it without deleting)
- Repost / share a post to your own profile with an optional caption
- Drafts, delete your own posts
- Basic rate limiting (max 20 posts/hour) to slow down spam

**Profile**
- Profile photo, banner image, bio, website, custom accent color
- Animated gradient banner when no banner image is set
- Glowing avatar ring, animated count-up follower/following stats
- Public and private accounts

**Interaction polish**
- Double-tap / double-click a photo to like it, with a heart-burst animation
- Likes update instantly (no page reload) via a small JS fetch layer;
  every like button still works with JS off too, since it's a real form underneath

**Account & safety**
- Account settings: change password, delete account
- Report a post or report a user

## Setup

1. Install dependencies:

   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

2. Create the database:

   CREATE DATABASE lufrica CHARACTER SET utf8mb4;
   CREATE USER 'lufrica_user'@'localhost' IDENTIFIED BY 'yourpassword';
   GRANT ALL PRIVILEGES ON lufrica.* TO 'lufrica_user'@'localhost';

3. Set environment variables:

   export DATABASE_URL="mysql+pymysql://lufrica_user:yourpassword@localhost/lufrica"
   export SECRET_KEY="something-long-and-random"

4. Run it:

   uvicorn main:app --reload --host 0.0.0.0 --port 8000

Tables are created automatically on first run.

## Structure

- main.py — all routes
- models.py — database models and the DB connection (foreign keys use
  ON DELETE CASCADE so deleting an account cleans up cleanly)
- auth.py — password hashing
- templates/ — all pages (Jinja2)
- static/ — CSS, JS, and uploaded media

## What's not in here (yet)

- Stories were removed at your request — no expiring 24h posts.
- No real-time layer: DMs and notifications are page-reload based,
  not WebSocket-pushed. python-socketio would be the natural add-on.
- No threaded comment replies — comments are flat.
- Filters apply to photos, not reels.
- No admin dashboard for reviewing reports yet — they just accumulate
  in the `reports` table.
