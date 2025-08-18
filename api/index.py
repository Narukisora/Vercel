from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client
from datetime import datetime, timedelta
import uuid, os

# ✅ Fix: use __name__ not name
app = Flask(__name__, template_folder="templates")

# ✅ Supabase config (your key already included)
SUPABASE_URL = "https://hzjqmssccnxddsbqliaq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh6anFtc3NjY254ZGRzYnFsaWFxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQxOTYzNjMsImV4cCI6MjA2OTc3MjM2M30.pzdW7pPHjCPqO9VJLF_kYoXcRVONO1YP2RVHkRyzOEk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

COOLDOWN_SECONDS = 120  # 2 minutes

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def format_time_ago(upload_time):
    """Convert timestamp to human-readable 'time ago' format"""
    if not upload_time:
        return "Unknown"
    try:
        if isinstance(upload_time, str):
            if upload_time.endswith('Z'):
                upload_time = upload_time[:-1] + '+00:00'
            upload_dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
        else:
            upload_dt = upload_time

        now = datetime.utcnow()
        diff = now - upload_dt.replace(tzinfo=None)
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        elif seconds < 2592000:
            days = seconds // 86400
            return f"{days}d ago"
        else:
            months = seconds // 2592000
            return f"{months}mo ago"
    except:
        return "Unknown"

@app.route('/')
def index():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "all").strip()

    query = supabase.table("listings").select("*")

    # ✅ Search filter
    if search:
        query = query.or_(f"name.ilike.%{search}%,description.ilike.%{search}%")

    # ✅ Category filter
    if category == "verified":
        query = query.eq("verified", True)
    elif category == "recent":
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        query = query.gte("inserted_at", seven_days_ago)

    # ✅ Order by verified first then newest
    query = query.order("verified", desc=True).order("inserted_at", desc=True)
    result = query.execute()

    # ✅ Add human-readable "time ago"
    for listing in result.data:
        listing['time_ago'] = format_time_ago(listing.get('inserted_at'))

    # ✅ Stats
    total_count = supabase.table("listings").select("id", count="exact").execute()
    total_files = total_count.count

    verified_count = supabase.table("listings").select("id", count="exact").eq("verified", True).execute()
    verified_files = verified_count.count

    return render_template("index.html",
                           listings=result.data,
                           search=search,
                           category=category,
                           total_files=total_files,
                           verified_files=verified_files)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    ip = get_client_ip()
    now = datetime.utcnow()

    # ✅ Cooldown check
    result = supabase.table("upload_cooldowns").select("last_upload_at").eq("ip_address", ip).execute()
    if result.data:
        last_upload_at_str = result.data[0]["last_upload_at"]
        last_upload_at = datetime.fromisoformat(last_upload_at_str.replace("Z", "+00:00"))
        if now - last_upload_at < timedelta(seconds=COOLDOWN_SECONDS):
            remaining = int(COOLDOWN_SECONDS - (now - last_upload_at).total_seconds())
            return f"<script>alert('Please wait {remaining} seconds before uploading again.'); window.location='/upload'</script>"

    if request.method == 'POST':
        file_link = request.form["file_link"]

        # ✅ Allowed domains check
        allowed_domains = ["discord.com", "discord.gg", "mediafire.com", "drive.google.com", "youtube.com", "youtu.be"]
        if not any(domain in file_link for domain in allowed_domains):
            return "<script>alert('Only Discord, Mediafire, Google Drive, or YouTube links are allowed!'); window.location='/upload'</script>"

        # ✅ Insert into Supabase
        data = {
            "id": str(uuid.uuid4()),
            "name": request.form["name"],
            "description": request.form["description"],
            "file_link": file_link,
            "verified": False,
            "inserted_at": now.isoformat()
        }
        supabase.table("listings").insert(data).execute()

        supabase.table("upload_cooldowns").upsert({
            "ip_address": ip,
            "last_upload_at": now.isoformat()
        }).execute()

        return redirect(url_for("index"))

    return render_template("upload.html")

@app.route('/download/<string:listing_id>')
def download(listing_id):
    listing = supabase.table("listings").select("*").eq("id", listing_id).single().execute().data
    if listing["file_link"] and listing["file_link"].startswith("http"):
        return redirect(listing["file_link"])
    return "<script>alert('Does not have any downloadable files!'); window.location='/'</script>"
