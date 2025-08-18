from flask import Flask, render_template_string, request, redirect, url_for
from supabase import create_client
from datetime import datetime, timedelta
import uuid, os

app = Flask(__name__)

# Hardcode Supabase credentials
SUPABASE_URL = "https://hzjqmssccnxddsbqliaq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh6anFtc3NjY254ZGRzYnFsaWFxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQxOTYzNjMsImV4cCI6MjA2OTc3MjM2M30.pzdW7pPHjCPqO9VJLF_kYoXcRVONO1YP2RVHkRyzOEk"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
COOLDOWN_SECONDS = 120  # 2 minutes

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def time_ago(dt_str):
    """Convert datetime string to time ago format"""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    now = datetime.utcnow().replace(tzinfo=dt.tzinfo)
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "Just now"

@app.route('/')
def index():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "all").strip()
    
    query = supabase.table("listings").select("*")
    
    # Apply category filter
    if category == "verified":
        query = query.eq("verified", True)
    elif category == "recent":
        # Get files from last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        query = query.gte("inserted_at", week_ago.isoformat())
    
    # Apply search filter
    if search:
        query = query.or_(f"name.ilike.%{search}%,description.ilike.%{search}%")
    
    query = query.order("inserted_at", desc=True)
    result = query.execute()
    
    # Add time_ago to each listing
    for listing in result.data:
        listing['time_ago'] = time_ago(listing['inserted_at'])
    
    # Get total count of all files in database
    total_count = supabase.table("listings").select("id", count="exact").execute()
    total_files = total_count.count
    
    # Get verified files count
    verified_count = supabase.table("listings").select("id", count="exact").eq("verified", True).execute()
    verified_files = verified_count.count
    
    return render_template_string(INDEX_TEMPLATE, 
                                listings=result.data, 
                                search=search, 
                                category=category,
                                total_files=total_files,
                                verified_files=verified_files,
                                url_for=url_for)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    ip = get_client_ip()
    now = datetime.utcnow()
    
    # Check cooldown
    result = supabase.table("upload_cooldowns").select("last_upload_at").eq("ip_address", ip).execute()
    if result.data:
        last_upload_at_str = result.data[0]["last_upload_at"]
        last_upload_at = datetime.fromisoformat(last_upload_at_str.replace("Z", "+00:00"))
        if now - last_upload_at < timedelta(seconds=COOLDOWN_SECONDS):
            remaining = int(COOLDOWN_SECONDS - (now - last_upload_at).total_seconds())
            return f"<script>alert('Please wait {remaining} seconds before uploading again.'); window.location='/upload'</script>"
    
    if request.method == 'POST':
        file_link = request.form["file_link"]
        allowed_domains = ["discord.com", "discord.gg", "mediafire.com", "drive.google.com", "youtube.com", "youtu.be"]
        if not any(domain in file_link for domain in allowed_domains):
            return "<script>alert('Only Discord, Mediafire, Google Drive, or YouTube links are allowed!'); window.location='/upload'</script>"
        
        # Add verified = False by default
        data = {
            "id": str(uuid.uuid4()),
            "name": request.form["name"],
            "description": request.form["description"],
            "file_link": file_link,
            "verified": False,   # default false
            "inserted_at": now.isoformat()
        }
        
        supabase.table("listings").insert(data).execute()
        supabase.table("upload_cooldowns").upsert({
            "ip_address": ip,
            "last_upload_at": now.isoformat()
        }).execute()
        
        return redirect(url_for("index"))
    
    return render_template_string(UPLOAD_TEMPLATE, url_for=url_for)

@app.route('/download/<string:listing_id>')
def download(listing_id):
    try:
        listing = supabase.table("listings").select("*").eq("id", listing_id).single().execute().data
        if listing["file_link"] and listing["file_link"].startswith("http"):
            return redirect(listing["file_link"])
        return "<script>alert('Does not have any downloadable files!'); window.location='/'</script>"
    except:
        return "<script>alert('File not found!'); window.location='/'</script>"
