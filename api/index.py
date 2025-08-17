from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client
from datetime import datetime, timedelta
import uuid, os

# Tell Flask where to find templates
app = Flask(__name__, template_folder="../templates")

# Hardcode Supabase credentials (replace with your actual values)
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your-supabase-key"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

COOLDOWN_SECONDS = 120  # 2 minutes

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

@app.route('/')
def index():
    search = request.args.get("search", "").strip()
    query = supabase.table("listings").select("*").order("inserted_at", desc=True)

    if search:
        query = query.or_(f"name.ilike.%{search}%,description.ilike.%{search}%")

    result = query.execute()
    return render_template("index.html", listings=result.data, search=search)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    ip = get_client_ip()
    now = datetime.utcnow()

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

        data = {
            "id": str(uuid.uuid4()),
            "name": request.form["name"],
            "description": request.form["description"],
            "file_link": file_link
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
